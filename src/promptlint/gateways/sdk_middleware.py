"""SDK middleware — httpx transports that intercept LLM API requests for analysis."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import TYPE_CHECKING

import httpx

from promptlint import PromptAnalyzer
from promptlint.gateways import (
    ConcurrencyConfig,
    GatewayCapability,
    GatewayInfo,
    PromptLintBlockedError,
    PromptLintOverloadError,
    VendorDetectionError,
)
from promptlint.gateways.normalizer import normalize
from promptlint.gateways.proxy import analysis_headers

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult

logger = logging.getLogger("promptlint.gateways.sdk_middleware")

SEVERITY_ORDER: dict[str, int] = {"ok": 0, "warning": 1, "critical": 2}


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
        except (VendorDetectionError, Exception):
            logger.debug("Skipping analysis: could not normalize request")
            return None
        return self._run_analysis(normalized)

    def _run_analysis(self, normalized: object) -> AnalysisResult | None:
        if self._semaphore is not None and not self._semaphore.acquire(blocking=False):
            raise PromptLintOverloadError("Analysis pipeline at capacity")
        try:
            from promptlint.gateways.normalizer import NormalizedRequest

            if not isinstance(normalized, NormalizedRequest):
                return None
            return self._analyzer.analyze(
                system_prompt=normalized.system_prompt,
                tools=normalized.tools if normalized.tools else None,
            )
        except PromptLintOverloadError:
            raise
        except Exception:
            logger.exception("Pipeline error, skipping analysis")
            return None
        finally:
            if self._semaphore is not None:
                self._semaphore.release()


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
        except (VendorDetectionError, Exception):
            logger.debug("Skipping analysis: could not normalize request")
            return None
        return await asyncio.to_thread(self._run_analysis, normalized)

    def _run_analysis(self, normalized: object) -> AnalysisResult | None:
        if self._semaphore is not None and not self._semaphore.acquire(blocking=False):
            raise PromptLintOverloadError("Analysis pipeline at capacity")
        try:
            from promptlint.gateways.normalizer import NormalizedRequest

            if not isinstance(normalized, NormalizedRequest):
                return None
            return self._analyzer.analyze(
                system_prompt=normalized.system_prompt,
                tools=normalized.tools if normalized.tools else None,
            )
        except PromptLintOverloadError:
            raise
        except Exception:
            logger.exception("Pipeline error, skipping analysis")
            return None
        finally:
            if self._semaphore is not None:
                self._semaphore.release()
