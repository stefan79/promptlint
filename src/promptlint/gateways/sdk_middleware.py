"""SDK middleware — httpx transports that intercept LLM API requests for analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from typing import TYPE_CHECKING

import httpx

from promptlint import PromptAnalyzer
from promptlint.gateways import (
    SEVERITY_ORDER,
    ConcurrencyConfig,
    GatewayCapability,
    GatewayInfo,
    PromptLintBlockedError,
    PromptLintOverloadError,
    VendorDetectionError,
)
from promptlint.gateways.normalizer import NormalizedRequest, normalize
from promptlint.gateways.proxy import analysis_headers

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult

logger = logging.getLogger("promptlint.gateways.sdk_middleware")


def _run_analysis(
    normalized: NormalizedRequest,
    analyzer: PromptAnalyzer,
    semaphore: threading.Semaphore | None,
    info: GatewayInfo,
) -> AnalysisResult:
    """Shared analysis helper for both sync and async transports."""
    if semaphore is not None and not semaphore.acquire(blocking=False):
        raise PromptLintOverloadError("Analysis pipeline at capacity")
    try:
        result = analyzer.analyze(
            system_prompt=normalized.system_prompt,
            tools=normalized.tools if normalized.tools else None,
        )
        result.gateway = info
        return result
    finally:
        if semaphore is not None:
            semaphore.release()


class PromptLintTransport(httpx.BaseTransport):
    """Synchronous httpx transport that runs promptlint analysis before forwarding."""

    def __init__(
        self,
        target: httpx.BaseTransport,
        analyzer: PromptAnalyzer | None = None,
        block_on: str | None = None,
        vendor_override: str | None = None,
        inject_headers: bool = True,
        concurrency: ConcurrencyConfig | None = None,
        gateway_id: str | None = None,
        **analyzer_kwargs: object,
    ) -> None:
        self._target = target
        self._analyzer = analyzer or PromptAnalyzer(**analyzer_kwargs)
        self._block_on = block_on
        self._vendor_override = vendor_override
        self._inject_headers = inject_headers
        self._info = GatewayInfo(type="sdk-middleware", id=gateway_id or uuid.uuid4().hex[:12])

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

    def should_block(self, result: AnalysisResult) -> bool:
        if self._block_on is None:
            return False
        return SEVERITY_ORDER.get(result.severity, 0) >= SEVERITY_ORDER.get(self._block_on, 2)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        result = self._analyze_request(request)
        if result is not None and self._inject_headers:
            for key, value in analysis_headers(result).items():
                request.headers[key] = value
        if result is not None and self.should_block(result):
            raise PromptLintBlockedError(severity=result.severity, result=result)
        return self._target.handle_request(request)

    def _analyze_request(self, request: httpx.Request) -> AnalysisResult | None:
        body_bytes = request.content
        if not body_bytes:
            return None
        try:
            normalized = normalize(body_bytes, vendor_override=self._vendor_override)
        except VendorDetectionError:
            logger.debug("Skipping analysis: vendor detection failed")
            return None
        except (json.JSONDecodeError, ValueError):
            logger.debug("Skipping analysis: malformed request body")
            return None
        try:
            return _run_analysis(normalized, self._analyzer, self._semaphore, self._info)
        except PromptLintOverloadError:
            raise
        except Exception:
            logger.exception("Pipeline error, skipping analysis")
            return None


class PromptLintAsyncTransport(httpx.AsyncBaseTransport):
    """Async httpx transport that runs promptlint analysis via asyncio.to_thread."""

    def __init__(
        self,
        target: httpx.AsyncBaseTransport,
        analyzer: PromptAnalyzer | None = None,
        block_on: str | None = None,
        vendor_override: str | None = None,
        inject_headers: bool = True,
        concurrency: ConcurrencyConfig | None = None,
        gateway_id: str | None = None,
        **analyzer_kwargs: object,
    ) -> None:
        self._target = target
        self._analyzer = analyzer or PromptAnalyzer(**analyzer_kwargs)
        self._block_on = block_on
        self._vendor_override = vendor_override
        self._inject_headers = inject_headers
        self._info = GatewayInfo(type="sdk-middleware", id=gateway_id or uuid.uuid4().hex[:12])

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

    def should_block(self, result: AnalysisResult) -> bool:
        if self._block_on is None:
            return False
        return SEVERITY_ORDER.get(result.severity, 0) >= SEVERITY_ORDER.get(self._block_on, 2)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        result = await self._analyze_request_async(request)
        if result is not None and self._inject_headers:
            for key, value in analysis_headers(result).items():
                request.headers[key] = value
        if result is not None and self.should_block(result):
            raise PromptLintBlockedError(severity=result.severity, result=result)
        return await self._target.handle_async_request(request)

    async def _analyze_request_async(self, request: httpx.Request) -> AnalysisResult | None:
        body_bytes = request.content
        if not body_bytes:
            return None
        try:
            normalized = normalize(body_bytes, vendor_override=self._vendor_override)
        except VendorDetectionError:
            logger.debug("Skipping analysis: vendor detection failed")
            return None
        except (json.JSONDecodeError, ValueError):
            logger.debug("Skipping analysis: malformed request body")
            return None
        try:
            return await asyncio.to_thread(_run_analysis, normalized, self._analyzer, self._semaphore, self._info)
        except PromptLintOverloadError:
            raise
        except Exception:
            logger.exception("Pipeline error, skipping analysis")
            return None
