"""Deprecated: use promptlint.gateways.proxy instead.

This module is a thin re-export shim for backwards compatibility.
It will be removed in v2.
"""

from __future__ import annotations

import warnings

from promptlint.gateways.proxy import create_app

warnings.warn(
    "promptlint.proxy is deprecated. Use promptlint.gateways.proxy instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["create_app"]
