from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
backend_root_str = str(BACKEND_ROOT)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires real OpenAI API key")
