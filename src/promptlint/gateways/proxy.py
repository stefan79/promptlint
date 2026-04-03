"""Built-in FastAPI reverse proxy with promptlint analysis middleware."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from promptlint import PromptAnalyzer
from promptlint.gateways import (
    SEVERITY_ORDER,
    ConcurrencyConfig,
    GatewayCapability,
    GatewayInfo,
    PromptLintOverloadError,
    VendorDetectionError,
)
from promptlint.gateways.normalizer import NormalizedRequest, normalize

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from promptlint.models import AnalysisResult

logger = logging.getLogger("promptlint.gateways.proxy")


class BuiltinProxy:
    """FastAPI-based reverse proxy with promptlint analysis."""

    def __init__(
        self,
        target: str = "https://api.anthropic.com",
        block_on: str | None = None,
        vendor_override: str | None = None,
        concurrency: ConcurrencyConfig | None = None,
        gateway_id: str | None = None,
        timeout: float = 300.0,
        **analyzer_kwargs: object,
    ) -> None:
        self._target = target
        self._block_on = block_on
        self._vendor_override = vendor_override
        self._timeout = timeout
        self._info = GatewayInfo(type="builtin-proxy", id=gateway_id or uuid.uuid4().hex[:12])
        self._analyzer = PromptAnalyzer(**analyzer_kwargs)

        concurrency = concurrency or ConcurrencyConfig()
        self._semaphore: threading.Semaphore | None = (
            threading.Semaphore(concurrency.max_concurrent) if concurrency.max_concurrent > 0 else None
        )

    @property
    def capabilities(self) -> GatewayCapability:
        return GatewayCapability.LOG_ONLY | GatewayCapability.ANNOTATE | GatewayCapability.BLOCK

    @property
    def info(self) -> GatewayInfo:
        return self._info

    def extract_request(self, raw_body: bytes) -> NormalizedRequest:
        return normalize(raw_body, vendor_override=self._vendor_override)

    def should_block(self, result: AnalysisResult) -> bool:
        if self._block_on is None:
            return False
        return SEVERITY_ORDER.get(result.severity, 0) >= SEVERITY_ORDER.get(self._block_on, 2)

    def _run_analysis(self, normalized: NormalizedRequest) -> AnalysisResult:
        """Run pipeline synchronously, respecting semaphore."""
        import time

        if self._semaphore is not None and not self._semaphore.acquire(blocking=False):
            raise PromptLintOverloadError("Analysis pipeline at capacity")
        try:
            t0 = time.monotonic()
            result = self._analyzer.analyze(
                system_prompt=normalized.system_prompt,
                tools=normalized.tools if normalized.tools else None,
                skip_contradictions=True,  # TODO(spec-14): remove when incremental cache lands
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            result.gateway = self._info
            logger.info("Analysis completed in %.0fms", elapsed_ms)
            return result
        finally:
            if self._semaphore is not None:
                self._semaphore.release()

    def create_app(self) -> FastAPI:
        """Build and return the FastAPI application."""
        app = FastAPI(title="promptlint proxy")
        proxy = self
        background_tasks: set[asyncio.Task[None]] = set()

        @app.api_route(
            "/{path:path}",
            methods=["POST"],
            response_model=None,
        )
        async def proxy_post_route(request: Request, path: str) -> JSONResponse | StreamingResponse:
            body_bytes = await request.body()

            # Fire-and-forget: forward immediately, analyze in background
            async def _bg_analyze() -> None:
                try:
                    normalized = proxy.extract_request(body_bytes)
                    result = await asyncio.to_thread(proxy._run_analysis, normalized)
                    _log_result(result, path)
                except VendorDetectionError:
                    logger.debug("Vendor detection failed for /%s, skipping analysis", path)
                except PromptLintOverloadError:
                    logger.warning("Analysis pipeline at capacity, skipping /%s", path)
                except Exception:
                    logger.exception("Pipeline error for /%s", path)

            task = asyncio.create_task(_bg_analyze())
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)

            # Forward to target immediately (no waiting for analysis)
            return await _forward_request(request, body_bytes, path, proxy._target, proxy._timeout, None)

        @app.api_route(
            "/{path:path}",
            methods=["GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
            response_model=None,
        )
        async def proxy_passthrough_route(request: Request, path: str) -> Response:
            """Forward non-POST methods without analysis."""
            body_bytes = await request.body()
            headers = dict(request.headers)
            headers.pop("host", None)
            async with httpx.AsyncClient(timeout=httpx.Timeout(proxy._timeout)) as client:
                response = await client.request(
                    method=request.method,
                    url=f"{proxy._target}/{path}",
                    headers=headers,
                    content=body_bytes,
                )
            return Response(
                status_code=response.status_code,
                content=response.content,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

        return app


def _log_result(result: AnalysisResult, path: str) -> None:
    logger.info("--- New request: POST /%s ---", path)
    logger.info("  Severity:        %s", result.severity.upper())
    logger.info("  Instructions:    %d total, %d unique", result.instruction_count, result.unique_instruction_count)
    logger.info("  Density:         %.1f instructions/1K tokens", result.density)
    redundant = result.instruction_count - result.unique_instruction_count
    logger.info(
        "  Redundancy:      %d redundant (%.1f%%), %d groups",
        redundant,
        result.redundancy_ratio * 100,
        len(result.redundant_groups),
    )
    logger.info("  Contradictions:  %d (skipped in proxy mode)", len(result.contradictions))
    if result.section_distribution:
        logger.info("  Sections:")
        for section, count in sorted(result.section_distribution.items(), key=lambda x: -x[1]):
            pct = (count / result.instruction_count * 100) if result.instruction_count else 0
            logger.info("    %-20s %3d instructions (%4.1f%%)", section, count, pct)

    # Write detailed report to file
    _write_report(result, path)


_REPORT_DIR = Path("promptlint-reports")


def _write_report(result: AnalysisResult, path: str) -> None:
    """Write a detailed labeled instruction report to disk."""
    _REPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = path.replace("/", "_")
    report_path = _REPORT_DIR / f"{ts}_{slug}.md"

    lines: list[str] = []
    lines.append(f"# promptlint report — POST /{path}")
    lines.append("")
    lines.append(f"**Severity:** {result.severity.upper()}")
    lines.append(f"**Instructions:** {result.instruction_count} total, {result.unique_instruction_count} unique")
    lines.append(f"**Density:** {result.density:.1f} instructions/1K tokens")
    lines.append(f"**Redundancy:** {result.redundancy_ratio:.1%}")
    lines.append("")

    # Instructions by section
    lines.append("## Instructions")
    lines.append("")
    by_section: dict[str, list[tuple[str, float]]] = {}
    for inst in result.instructions:
        section = inst.source_section or "(unknown)"
        by_section.setdefault(section, []).append((inst.text, inst.confidence))

    for section in sorted(by_section):
        lines.append(f"### {section}")
        lines.append("")
        for text, confidence in by_section[section]:
            lines.append(f"- [{confidence:.2f}] {text}")
        lines.append("")

    # Non-instructions (for comparison)
    if result.non_instructions:
        lines.append("## Non-instructions (not counted)")
        lines.append("")
        for chunk in result.non_instructions:
            section = chunk.source_section or "(unknown)"
            lines.append(f"- [{chunk.confidence:.2f}] `{section}` {chunk.text[:120]}")
        lines.append("")

    # Redundancy groups
    if result.redundant_groups:
        lines.append("## Redundancy groups")
        lines.append("")
        for i, group in enumerate(result.redundant_groups, 1):
            lines.append(f"### Group {i} (similarity: {group.similarity:.2f})")
            lines.append(f"- **Canonical:** {group.canonical.text}")
            for dup in group.duplicates:
                lines.append(f"- Duplicate: {dup.text}")
            lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("  Report written to %s", report_path)


def _blocked_response(result: AnalysisResult) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "promptlint_blocked",
            "severity": result.severity,
            "instruction_count": result.instruction_count,
            "unique_instruction_count": result.unique_instruction_count,
            "density": result.density,
            "contradictions": len(result.contradictions),
            "warnings": result.warnings,
            "report": result.to_json(),
        },
        headers=analysis_headers(result),
    )


async def _forward_request(
    request: Request,
    body_bytes: bytes,
    path: str,
    target: str,
    timeout: float,
    result: AnalysisResult | None,
) -> JSONResponse | StreamingResponse:
    headers = dict(request.headers)
    headers.pop("host", None)
    # Remove encoding headers — httpx handles decompression transparently,
    # but we stream raw bytes back so the client would get compressed data
    # with no Content-Encoding header, causing decompression errors.
    headers.pop("accept-encoding", None)
    headers.pop("content-length", None)
    if result is not None:
        headers.update(analysis_headers(result))

    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError):
        body = {}
    is_streaming = body.get("stream", False) if isinstance(body, dict) else False

    if is_streaming:
        # For streaming, the client must stay open until streaming completes.
        # We create the client outside `async with` and close it in the stream generator.
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        req = client.build_request("POST", f"{target}/{path}", headers=headers, content=body_bytes)
        response = await client.send(req, stream=True)

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        resp_headers = dict(response.headers)
        resp_headers.pop("content-encoding", None)
        resp_headers.pop("content-length", None)
        if result is not None:
            resp_headers.update(analysis_headers(result))
        return StreamingResponse(
            stream(),
            status_code=response.status_code,
            headers=resp_headers,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        response = await client.post(f"{target}/{path}", headers=headers, content=body_bytes)
        resp_headers = dict(response.headers)
        resp_headers.pop("content-encoding", None)
        resp_headers.pop("content-length", None)
        if result is not None:
            resp_headers.update(analysis_headers(result))
        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if _is_json(response) else {"raw": response.text},
            headers=resp_headers,
        )


def _is_json(response: httpx.Response) -> bool:
    ct: str = response.headers.get("content-type", "")
    return ct.startswith("application/json")


def analysis_headers(result: AnalysisResult) -> dict[str, str]:
    """Build X-Promptlint-* headers from an analysis result."""
    return {
        "X-Promptlint-Instructions": str(result.instruction_count),
        "X-Promptlint-Unique": str(result.unique_instruction_count),
        "X-Promptlint-Density": f"{result.density:.1f}",
        "X-Promptlint-Severity": result.severity,
        "X-Promptlint-Contradictions": str(len(result.contradictions)),
    }


def create_app(
    target: str = "https://api.anthropic.com",
    block_on: str | None = None,
    vendor_override: str | None = None,
    **analyzer_kwargs: Any,
) -> FastAPI:
    """Convenience factory matching the old proxy.create_app signature."""
    # Handle deprecated `fail_on` kwarg
    if "fail_on" in analyzer_kwargs:
        block_on = block_on or str(analyzer_kwargs.pop("fail_on"))
    proxy = BuiltinProxy(target=target, block_on=block_on, vendor_override=vendor_override, **analyzer_kwargs)
    return proxy.create_app()
