"""Shared test configuration."""

import pytest


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False, help="Run slow tests requiring model downloads")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (requires model downloads)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="needs --slow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
