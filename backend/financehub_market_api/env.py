from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def iter_env_file_candidates() -> list[Path]:
    """Return env files from broad to local scope so later files override earlier ones."""
    roots = [REPOSITORY_ROOT, BACKEND_ROOT, Path.cwd()]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for filename in (".env", ".env.local"):
            candidate = root / filename
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(candidate)
    return candidates


def parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = raw_value.strip().strip("\"'")
    return values


def build_env_values(
    *,
    environ: Mapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for env_file in env_files if env_files is not None else iter_env_file_candidates():
        values.update(parse_env_file(env_file))
    values.update(dict(os.environ if environ is None else environ))
    return values


def load_backend_env_files(
    *,
    environ: MutableMapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    target = os.environ if environ is None else environ
    values: dict[str, str] = {}
    for env_file in env_files if env_files is not None else iter_env_file_candidates():
        values.update(parse_env_file(env_file))
    for key, value in values.items():
        target.setdefault(key, value)
    return values


def read_env(env: Mapping[str, str], key: str) -> str | None:
    raw_value = env.get(key)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value if value else None
