"""Gateway listeners for promptlint — abstractions for intercepting LLM API traffic."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from promptlint.gateways.normalizer import NormalizedRequest
    from promptlint.models import AnalysisResult


class GatewayCapability(Flag):
    LOG_ONLY = auto()
    ANNOTATE = auto()
    BLOCK = auto()


@dataclass
class GatewayInfo:
    type: str  # "builtin-proxy", "sdk-middleware"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ConcurrencyConfig:
    max_concurrent: int = 10


class GatewayListener(Protocol):
    """Protocol that all gateway implementations must satisfy."""

    @property
    def capabilities(self) -> GatewayCapability: ...

    @property
    def info(self) -> GatewayInfo: ...

    def extract_request(self, raw_request: bytes) -> NormalizedRequest: ...

    def inject_headers(self, response: Any, result: AnalysisResult) -> None: ...

    def should_block(self, result: AnalysisResult) -> bool: ...


class VendorDetectionError(Exception):
    """Raised when the vendor cannot be determined from the request body."""


class PromptLintBlockedError(Exception):
    """Raised when analysis severity exceeds the configured block threshold."""

    def __init__(self, severity: str, result: AnalysisResult) -> None:
        self.severity = severity
        self.result = result
        super().__init__(f"Request blocked: severity {severity}")


class PromptLintOverloadError(Exception):
    """Raised when the concurrency semaphore is full."""
