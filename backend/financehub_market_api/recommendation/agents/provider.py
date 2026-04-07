from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx


ProviderKind = Literal["openai_compatible", "anthropic"]

OPENAI_PROVIDER_NAME = "openai"
ANTHROPIC_PROVIDER_NAME = "anthropic"
OPENAI_DEFAULT_MODEL = "gpt-5.4"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-4-6"
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


def _default_model_for_provider(
    provider_name: str,
    env_values: Mapping[str, str],
) -> str:
    if provider_name == OPENAI_PROVIDER_NAME:
        return (
            _clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_MODEL_DEFAULT"))
            or _clean_env_value(env_values.get("FINANCEHUB_LLM_MODEL_DEFAULT"))
            or OPENAI_DEFAULT_MODEL
        )
    if provider_name == ANTHROPIC_PROVIDER_NAME:
        return (
            _clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_ANTHROPIC_MODEL_DEFAULT"))
            or ANTHROPIC_DEFAULT_MODEL
        )
    return OPENAI_DEFAULT_MODEL


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
    "user_profile": AgentModelRoute(
        provider_name=OPENAI_PROVIDER_NAME,
        model_name=OPENAI_DEFAULT_MODEL,
    ),
    "market_intelligence": AgentModelRoute(
        provider_name=ANTHROPIC_PROVIDER_NAME,
        model_name=ANTHROPIC_DEFAULT_MODEL,
    ),
    "fund_selection": AgentModelRoute(
        provider_name=OPENAI_PROVIDER_NAME,
        model_name=OPENAI_DEFAULT_MODEL,
    ),
    "wealth_selection": AgentModelRoute(
        provider_name=OPENAI_PROVIDER_NAME,
        model_name=OPENAI_DEFAULT_MODEL,
    ),
    "stock_selection": AgentModelRoute(
        provider_name=OPENAI_PROVIDER_NAME,
        model_name=OPENAI_DEFAULT_MODEL,
    ),
    "explanation": AgentModelRoute(
        provider_name=ANTHROPIC_PROVIDER_NAME,
        model_name=ANTHROPIC_DEFAULT_MODEL,
    ),
}


@dataclass(frozen=True)
class AgentRuntimeConfig:
    providers: dict[str, ProviderConfig]
    agent_routes: dict[str, AgentModelRoute]

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
        )


def _load_provider_registry(env_values: Mapping[str, str]) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}

    openai_api_key = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")
        or env_values.get("FINANCEHUB_LLM_API_KEY")
    )
    openai_base_url = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL")
        or env_values.get("FINANCEHUB_LLM_BASE_URL")
    )
    if openai_api_key and openai_base_url:
        providers[OPENAI_PROVIDER_NAME] = ProviderConfig(
            name=OPENAI_PROVIDER_NAME,
            kind=_clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_KIND"))
            or "openai_compatible",
            api_key=openai_api_key,
            base_url=_normalize_base_url(openai_base_url),
        )

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
            kind=_clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_ANTHROPIC_KIND"))
            or "anthropic",
            api_key=anthropic_api_key,
            base_url=_normalize_base_url(anthropic_base_url),
        )

    return providers


def _load_agent_model_routes(env_values: Mapping[str, str]) -> dict[str, AgentModelRoute]:
    routes = {
        agent_name: AgentModelRoute(
            provider_name=route.provider_name,
            model_name=_default_model_for_provider(route.provider_name, env_values),
        )
        for agent_name, route in DEFAULT_AGENT_MODEL_ROUTES.items()
    }

    for agent_name, env_name in AGENT_MODEL_ROUTE_ENV_NAMES.items():
        current_route = routes[agent_name]
        provider_name = _clean_env_value(
            env_values.get(f"FINANCEHUB_LLM_AGENT_{env_name}_PROVIDER")
        ) or current_route.provider_name
        model_name = _clean_env_value(env_values.get(f"FINANCEHUB_LLM_AGENT_{env_name}_MODEL"))
        routes[agent_name] = AgentModelRoute(
            provider_name=provider_name,
            model_name=model_name or _default_model_for_provider(provider_name, env_values),
        )

    return routes


def _parse_json_content(content: str) -> dict[str, object]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMInvalidResponseError("provider returned invalid JSON content") from exc

    if not isinstance(parsed, dict):
        raise LLMInvalidResponseError("provider JSON content must be an object")
    return parsed


class OpenAICompatibleChatProvider:
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
        payload = {
            "model": model_name,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "recommendation_agent_response",
                    "schema": response_schema,
                },
            },
        }
        try:
            response = self._http_client.post(
                f"{self._config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"OpenAI-compatible provider request failed: {exc}") from exc
        except ValueError as exc:
            raise LLMInvalidResponseError("provider response is not valid JSON") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("provider response has no assistant message content") from exc

        if not isinstance(content, str):
            raise LLMInvalidResponseError("provider assistant content must be a JSON string")
        return _parse_json_content(content)


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
            "max_tokens": 1024,
            "messages": anthropic_messages,
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": response_schema,
                }
            },
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

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
            body = response.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Anthropic provider request failed: {exc}") from exc
        except ValueError as exc:
            raise LLMInvalidResponseError("provider response is not valid JSON") from exc

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
) -> OpenAICompatibleChatProvider | AnthropicChatProvider:
    if config.kind == "openai_compatible":
        return OpenAICompatibleChatProvider(config, http_client=http_client)
    if config.kind == "anthropic":
        return AnthropicChatProvider(config, http_client=http_client)
    raise ValueError(f"unsupported provider kind: {config.kind}")


LLMProviderConfig = ProviderConfig
