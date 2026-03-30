"""Deprecated: use promptlint.gateways.proxy instead.

This module is a thin re-export shim for backwards compatibility.
It will be removed in v2.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_app(**kwargs: Any) -> FastAPI:
    """Deprecated wrapper — delegates to promptlint.gateways.proxy.create_app."""
    warnings.warn(
        "promptlint.proxy is deprecated. Use promptlint.gateways.proxy instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from promptlint.gateways.proxy import create_app as _create_app

    return _create_app(**kwargs)


__all__ = ["create_app"]
