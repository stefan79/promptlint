"""Shared test configuration."""

import pytest

from promptlint.models import ClassifiedChunk


@pytest.fixture
def make_instruction():
    """Factory fixture for creating ClassifiedChunk test instructions."""

    def _make(text: str, section: str = "test", confidence: float = 0.9) -> ClassifiedChunk:
        return ClassifiedChunk(
            text=text,
            source_section=section,
            start_offset=0,
            end_offset=len(text),
            structural_type="bullet",
            label="instruction",
            confidence=confidence,
        )

    return _make


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
