from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_path():
    """Return a function that resolves fixture file paths."""
    def _get(name: str) -> Path:
        return FIXTURES_DIR / name
    return _get


@pytest.fixture
def fixture_html():
    """Return a function that reads fixture HTML files."""
    def _get(name: str) -> str:
        return (FIXTURES_DIR / name).read_text()
    return _get


@pytest.fixture
def fixture_json():
    """Return a function that reads fixture JSON files."""
    import json
    def _get(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())
    return _get
