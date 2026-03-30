"""Built-in FastAPI reverse proxy with promptlint analysis middleware."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
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
        if self._semaphore is not None and not self._semaphore.acquire(blocking=False):
            raise PromptLintOverloadError
        try:
            result = self._analyzer.analyze(
                system_prompt=normalized.system_prompt,
                tools=normalized.tools if normalized.tools else None,
            )
            result.gateway = self._info
            return result
        finally:
            if self._semaphore is not None:
                self._semaphore.release()

    def create_app(self) -> FastAPI:
        """Build and return the FastAPI application."""
        app = FastAPI(title="promptlint proxy")
        proxy = self

        @app.api_route(
            "/{path:path}",
            methods=["POST"],
            response_model=None,
        )
        async def proxy_post_route(request: Request, path: str) -> JSONResponse | StreamingResponse:
            body_bytes = await request.body()

            # Try to normalize and analyze
            result: AnalysisResult | None = None
            try:
                normalized = proxy.extract_request(body_bytes)
                result = await asyncio.to_thread(proxy._run_analysis, normalized)
            except VendorDetectionError:
                logger.debug("Vendor detection failed for /%s, passing through", path)
            except PromptLintOverloadError:
                return JSONResponse(
                    status_code=429,
                    content={"error": "promptlint_overload", "message": "Analysis pipeline at capacity"},
                    headers={"Retry-After": "1"},
                )
            except Exception:
                logger.exception("Pipeline error for /%s, passing through", path)

            if result is not None:
                _log_result(result, path)
                if proxy.should_block(result):
                    return _blocked_response(result)

            # Forward to target
            return await _forward_request(request, body_bytes, path, proxy._target, proxy._timeout, result)

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
    logger.warning(
        "POST /%s -> %d instructions (%d unique), density %.1f, severity %s, %d contradictions",
        path,
        result.instruction_count,
        result.unique_instruction_count,
        result.density,
        result.severity.upper(),
        len(result.contradictions),
    )


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
    if result is not None:
        headers.update(analysis_headers(result))

    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError):
        body = {}
    is_streaming = body.get("stream", False) if isinstance(body, dict) else False

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        if is_streaming:
            return await _stream_response(client, target, path, headers, body_bytes, result)
        response = await client.post(f"{target}/{path}", headers=headers, content=body_bytes)
        resp_headers = dict(response.headers)
        if result is not None:
            resp_headers.update(analysis_headers(result))
        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if _is_json(response) else {"raw": response.text},
            headers=resp_headers,
        )


async def _stream_response(
    client: httpx.AsyncClient,
    target: str,
    path: str,
    headers: dict[str, str],
    body_bytes: bytes,
    result: AnalysisResult | None,
) -> StreamingResponse:
    req = client.build_request("POST", f"{target}/{path}", headers=headers, content=body_bytes)
    response = await client.send(req, stream=True)

    async def stream() -> AsyncIterator[bytes]:
        async for chunk in response.aiter_bytes():
            yield chunk
        await response.aclose()

    resp_headers = dict(response.headers)
    if result is not None:
        resp_headers.update(analysis_headers(result))
    return StreamingResponse(
        stream(),
        status_code=response.status_code,
        headers=resp_headers,
        media_type=response.headers.get("content-type", "text/event-stream"),
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
