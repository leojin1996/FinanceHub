from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
backend_root_str = str(BACKEND_ROOT)
tests_dir_str = str(TESTS_DIR)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)
if tests_dir_str not in sys.path:
    sys.path.insert(0, tests_dir_str)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        values[key] = raw_value.strip().strip("\"'")
    return values


def _load_backend_env_files() -> None:
    """Merge ``.env`` then ``.env.local``; only set keys missing from the process environment."""
    merged: dict[str, str] = {}
    for name in (".env", ".env.local"):
        merged.update(_parse_env_file(BACKEND_ROOT / name))
    for key, value in merged.items():
        if key not in os.environ:
            os.environ[key] = value


def _apply_integration_chat_recall_defaults() -> None:
    """If integration tests are on but chat-recall Qdrant is unset, reuse product-knowledge Qdrant."""
    raw = os.environ.get("FINANCEHUB_INTEGRATION_TESTS", "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return
    if not os.environ.get("FINANCEHUB_CHAT_RECALL_QDRANT_URL", "").strip():
        base = os.environ.get("FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL", "").strip()
        if base:
            os.environ.setdefault("FINANCEHUB_CHAT_RECALL_QDRANT_URL", base)
    if not os.environ.get("FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY", "").strip():
        key = os.environ.get("FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_API_KEY", "").strip()
        if key:
            os.environ.setdefault("FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY", key)


_load_backend_env_files()
_apply_integration_chat_recall_defaults()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires real OpenAI API key")
    config.addinivalue_line(
        "markers",
        "integration: real Redis, MySQL, Qdrant, OpenAI (set FINANCEHUB_INTEGRATION_TESTS=1)",
    )
