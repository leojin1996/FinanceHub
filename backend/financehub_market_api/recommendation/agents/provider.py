from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx


ProviderKind = Literal["anthropic"]

ANTHROPIC_PROVIDER_NAME = "anthropic"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
ANTHROPIC_MAX_TOKENS = 100000
ANTHROPIC_MAX_ATTEMPTS = 2
ANTHROPIC_RETRY_BACKOFF_SECONDS = 1.0
AGENT_MODEL_ROUTE_ENV_NAMES = {
    "user_profile": "USER_PROFILE",
    "market_intelligence": "MARKET_INTELLIGENCE",
    "fund_selection": "FUND_SELECTION",
    "wealth_selection": "WEALTH_SELECTION",
    "stock_selection": "STOCK_SELECTION",
    "explanation": "EXPLANATION",
}


class LLMProviderError(RuntimeError):
    pass


class LLMInvalidResponseError(LLMProviderError):
    pass


def _iter_env_file_candidates() -> list[Path]:
    search_roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[4],
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        for filename in (".env.local", ".env"):
            candidate = root / filename
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip("\"'")
    return values


def _build_env_values(
    environ: Mapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for env_file in env_files if env_files is not None else _iter_env_file_candidates():
        values.update(_parse_env_file(env_file))
    values.update(dict(os.environ if environ is None else environ))
    return values


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _default_anthropic_model(env_values: Mapping[str, str]) -> str:
    return (
        _clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_ANTHROPIC_MODEL_DEFAULT"))
        or ANTHROPIC_DEFAULT_MODEL
    )


def _parse_request_timeout_seconds(env_values: Mapping[str, str]) -> float:
    raw_value = _clean_env_value(env_values.get("FINANCEHUB_LLM_TIMEOUT_SECONDS"))
    if raw_value is None:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        timeout_seconds = float(raw_value)
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    if timeout_seconds <= 0:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    return timeout_seconds


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    kind: ProviderKind
    api_key: str
    base_url: str


@dataclass(frozen=True)
class AgentModelRoute:
    provider_name: str
    model_name: str


DEFAULT_AGENT_MODEL_ROUTES = {
    agent_name: AgentModelRoute(
        provider_name=ANTHROPIC_PROVIDER_NAME,
        model_name=ANTHROPIC_DEFAULT_MODEL,
    )
    for agent_name in AGENT_MODEL_ROUTE_ENV_NAMES
}


@dataclass(frozen=True)
class AgentRuntimeConfig:
    providers: dict[str, ProviderConfig]
    agent_routes: dict[str, AgentModelRoute]
    request_timeout_seconds: float

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        env_files: Sequence[Path] | None = None,
    ) -> AgentRuntimeConfig:
        env_values = _build_env_values(environ=environ, env_files=env_files)
        return cls(
            providers=_load_provider_registry(env_values),
            agent_routes=_load_agent_model_routes(env_values),
            request_timeout_seconds=_parse_request_timeout_seconds(env_values),
        )


def _load_provider_registry(env_values: Mapping[str, str]) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}

    anthropic_api_key = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY")
        or env_values.get("ANTHROPIC_AUTH_TOKEN")
        or env_values.get("ANTHROPIC_API_KEY")
    )
    anthropic_base_url = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL")
        or env_values.get("ANTHROPIC_BASE_URL")
    )
    if anthropic_api_key and anthropic_base_url:
        providers[ANTHROPIC_PROVIDER_NAME] = ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key=anthropic_api_key,
            base_url=_normalize_base_url(anthropic_base_url),
        )

    return providers


def _load_agent_model_routes(env_values: Mapping[str, str]) -> dict[str, AgentModelRoute]:
    default_model = _default_anthropic_model(env_values)
    routes = {
        agent_name: AgentModelRoute(
            provider_name=ANTHROPIC_PROVIDER_NAME,
            model_name=default_model,
        )
        for agent_name in DEFAULT_AGENT_MODEL_ROUTES
    }

    for agent_name, env_name in AGENT_MODEL_ROUTE_ENV_NAMES.items():
        model_name = _clean_env_value(env_values.get(f"FINANCEHUB_LLM_AGENT_{env_name}_MODEL"))
        routes[agent_name] = AgentModelRoute(
            provider_name=ANTHROPIC_PROVIDER_NAME,
            model_name=model_name or default_model,
        )

    return routes


def _parse_json_content(content: str) -> dict[str, object]:
    normalized_content = content.strip()
    candidates = [normalized_content]

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", normalized_content, re.DOTALL)
    if fenced_match is not None:
        candidates.append(fenced_match.group(1).strip())

    last_error: json.JSONDecodeError | None = None
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
        else:
            if not isinstance(parsed, dict):
                raise LLMInvalidResponseError("provider JSON content must be an object")
            return parsed

        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate, idx=match.start())
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if not isinstance(parsed, dict):
                continue
            return parsed

    raise LLMInvalidResponseError("provider returned invalid JSON content") from last_error


def _is_retryable_anthropic_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return False


class AnthropicChatProvider:
    def __init__(
        self,
        config: ProviderConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._http_client = http_client or httpx.Client()

    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        system_prompts = [
            message["content"]
            for message in messages
            if message.get("role") == "system" and isinstance(message.get("content"), str)
        ]
        anthropic_messages = [
            {
                "role": message["role"],
                "content": message["content"],
            }
            for message in messages
            if message.get("role") != "system"
        ]
        payload: dict[str, object] = {
            "model": model_name,
            "max_tokens": ANTHROPIC_MAX_TOKENS,
            "messages": anthropic_messages,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        structured_payload = dict(payload)
        structured_payload["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": response_schema,
            }
        }

        try:
            return self._parse_response_body(
                self._post_messages(structured_payload, timeout_seconds=timeout_seconds)
            )
        except LLMInvalidResponseError as structured_exc:
            fallback_payload = dict(payload)
            try:
                return self._parse_response_body(
                    self._post_messages(fallback_payload, timeout_seconds=timeout_seconds)
                )
            except LLMInvalidResponseError as fallback_exc:
                raise fallback_exc from structured_exc

    def _post_messages(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> object:
        for attempt in range(ANTHROPIC_MAX_ATTEMPTS):
            try:
                response = self._http_client.post(
                    f"{self._config.base_url}/messages",
                    headers={
                        "x-api-key": self._config.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                if attempt + 1 >= ANTHROPIC_MAX_ATTEMPTS or not _is_retryable_anthropic_error(exc):
                    raise LLMProviderError(f"Anthropic provider request failed: {exc}") from exc
                time.sleep(ANTHROPIC_RETRY_BACKOFF_SECONDS * (attempt + 1))
            except ValueError as exc:
                raise LLMInvalidResponseError("provider response is not valid JSON") from exc

        raise AssertionError("anthropic request retry loop exited unexpectedly")

    def _parse_response_body(self, body: object) -> dict[str, object]:
        try:
            content_blocks = body["content"]
        except (KeyError, TypeError) as exc:
            raise LLMInvalidResponseError("provider response has no content blocks") from exc

        if not isinstance(content_blocks, list):
            raise LLMInvalidResponseError("provider content blocks must be a list")

        for block in content_blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                raise LLMInvalidResponseError("provider text block must contain a string")
            return _parse_json_content(text)

        raise LLMInvalidResponseError("provider response has no text content block")


def build_provider(
    config: ProviderConfig,
    *,
    http_client: httpx.Client | None = None,
) -> AnthropicChatProvider:
    if config.kind != "anthropic":
        raise ValueError(f"unsupported provider kind: {config.kind}")
    return AnthropicChatProvider(config, http_client=http_client)


LLMProviderConfig = ProviderConfig
