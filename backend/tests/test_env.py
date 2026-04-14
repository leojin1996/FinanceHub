from __future__ import annotations

from pathlib import Path

from financehub_market_api.env import build_env_values, load_backend_env_files


def test_build_env_values_loads_env_local_after_env_and_keeps_process_precedence(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_local_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_MYSQL_URL=mysql+pymysql://env.example/financehub",
                "FINANCEHUB_MARKET_CACHE_REDIS_URL=redis://env.example:6379/0",
            ]
        ),
        encoding="utf-8",
    )
    env_local_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_MYSQL_URL=mysql+pymysql://local.example/financehub",
                "FINANCEHUB_LLM_PROVIDER_OPENAI_MODEL_DEFAULT=gpt-5.4-mini",
            ]
        ),
        encoding="utf-8",
    )

    values = build_env_values(
        environ={"FINANCEHUB_MYSQL_URL": "mysql+pymysql://process.example/financehub"},
        env_files=[env_file, env_local_file],
    )

    assert values["FINANCEHUB_MYSQL_URL"] == "mysql+pymysql://process.example/financehub"
    assert values["FINANCEHUB_MARKET_CACHE_REDIS_URL"] == "redis://env.example:6379/0"
    assert values["FINANCEHUB_LLM_PROVIDER_OPENAI_MODEL_DEFAULT"] == "gpt-5.4-mini"


def test_load_backend_env_files_sets_missing_keys_without_overriding_process_values(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_local_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_MARKET_CACHE_REDIS_URL=redis://env.example:6379/0",
                "FINANCEHUB_JWT_EXPIRE_HOURS=12",
            ]
        ),
        encoding="utf-8",
    )
    env_local_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_MARKET_CACHE_REDIS_URL=redis://local.example:6379/0",
                "FINANCEHUB_JWT_SECRET_KEY=local-secret",
            ]
        ),
        encoding="utf-8",
    )
    environ = {"FINANCEHUB_MARKET_CACHE_REDIS_URL": "redis://process.example:6379/0"}

    loaded_values = load_backend_env_files(
        environ=environ,
        env_files=[env_file, env_local_file],
    )

    assert loaded_values["FINANCEHUB_MARKET_CACHE_REDIS_URL"] == "redis://local.example:6379/0"
    assert environ["FINANCEHUB_MARKET_CACHE_REDIS_URL"] == "redis://process.example:6379/0"
    assert environ["FINANCEHUB_JWT_EXPIRE_HOURS"] == "12"
    assert environ["FINANCEHUB_JWT_SECRET_KEY"] == "local-secret"
