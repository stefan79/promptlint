"""FastAPI reverse proxy with promptlint analysis middleware."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from promptlint import PromptAnalyzer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from promptlint.models import AnalysisResult

logger = logging.getLogger("promptlint.proxy")


def create_app(
    target: str = "https://api.anthropic.com",
    fail_on: str | None = None,
    **analyzer_kwargs: object,
) -> FastAPI:
    app = FastAPI(title="promptlint proxy")
    analyzer = PromptAnalyzer(**analyzer_kwargs)
    severity_order = {"ok": 0, "warning": 1, "critical": 2}

    @app.api_route("/v1/messages", methods=["POST"])
    async def proxy_messages(request: Request) -> JSONResponse | StreamingResponse:
        body_bytes = await request.body()
        body = json.loads(body_bytes)

        # Extract prompt components from the Anthropic API request
        system_prompt = _extract_system(body)
        tools = body.get("tools", [])
        messages = body.get("messages", [])

        # Build text for analysis (system + tool descriptions + user messages)
        analysis_parts = []
        if system_prompt:
            analysis_parts.append(system_prompt)
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                analysis_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        analysis_parts.append(block["text"])

        # Run analysis
        t0 = time.monotonic()
        result = analyzer.analyze(
            system_prompt=system_prompt,
            tools=tools if tools else None,
        )
        analysis_ms = (time.monotonic() - t0) * 1000

        # Log
        logger.warning(
            "POST /v1/messages → %d instructions (%d unique), density %.1f, severity %s, %d contradictions [%.0fms]",
            result.instruction_count,
            result.unique_instruction_count,
            result.density,
            result.severity.upper(),
            len(result.contradictions),
            analysis_ms,
        )

        # Block if severity exceeds threshold
        if fail_on and severity_order.get(result.severity, 0) >= severity_order.get(fail_on, 2):
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
                headers=_analysis_headers(result),
            )

        # Forward to target API
        headers = dict(request.headers)
        # Remove host header (will be set by httpx)
        headers.pop("host", None)
        # Add analysis headers
        headers.update(_analysis_headers(result))

        is_streaming = body.get("stream", False)

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            if is_streaming:
                req = client.build_request(
                    "POST",
                    f"{target}/v1/messages",
                    headers=headers,
                    content=body_bytes,
                )
                response = await client.send(req, stream=True)

                async def stream_response() -> AsyncIterator[bytes]:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                    await response.aclose()

                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type", "text/event-stream"),
                )
            response = await client.post(
                f"{target}/v1/messages",
                headers=headers,
                content=body_bytes,
            )
            return JSONResponse(
                status_code=response.status_code,
                content=response.json(),
                headers=_analysis_headers(result),
            )

    # Pass through all other routes
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_passthrough(request: Request, path: str) -> JSONResponse:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            response = await client.request(
                request.method,
                f"{target}/{path}",
                headers=headers,
                content=body,
            )
            return JSONResponse(
                status_code=response.status_code,
                content=response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {"raw": response.text},
            )

    return app


def _extract_system(body: dict[str, object]) -> str | None:
    """Extract system prompt from Anthropic API request body."""
    system = body.get("system")
    if system is None:
        return None
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        # System can be a list of content blocks
        parts = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n\n".join(parts) if parts else None
    return None


def _analysis_headers(result: AnalysisResult) -> dict[str, str]:
    return {
        "X-Promptlint-Instructions": str(result.instruction_count),
        "X-Promptlint-Unique": str(result.unique_instruction_count),
        "X-Promptlint-Density": f"{result.density:.1f}",
        "X-Promptlint-Severity": result.severity,
        "X-Promptlint-Contradictions": str(len(result.contradictions)),
    }
