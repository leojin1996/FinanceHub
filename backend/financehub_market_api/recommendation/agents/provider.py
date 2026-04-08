from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import httpx

LOGGER = logging.getLogger(__name__)

ProviderKind = Literal["anthropic"]

ANTHROPIC_PROVIDER_NAME = "anthropic"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
ANTHROPIC_MAX_TOKENS = 100000
ANTHROPIC_MAX_ATTEMPTS = 2
ANTHROPIC_RETRY_BACKOFF_SECONDS = 1.0
LLM_CAPTURE_RAW_RESPONSES_ENV = "FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES"
LLM_CAPTURE_DIR_ENV = "FINANCEHUB_LLM_CAPTURE_DIR"
LLM_AGENT_TRACE_LOGS_ENV = "FINANCEHUB_LLM_AGENT_TRACE_LOGS"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
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


def _is_truthy_env_value(value: str | None) -> bool:
    cleaned = _clean_env_value(value)
    if cleaned is None:
        return False
    return cleaned.lower() in _TRUTHY_ENV_VALUES


def _is_raw_capture_enabled(environ: Mapping[str, str]) -> bool:
    return _is_truthy_env_value(environ.get(LLM_CAPTURE_RAW_RESPONSES_ENV))


def _is_agent_trace_logging_enabled(environ: Mapping[str, str]) -> bool:
    return _is_truthy_env_value(environ.get(LLM_AGENT_TRACE_LOGS_ENV))


def _default_capture_dir() -> Path:
    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / "tmp" / "llm-captures"


def _resolve_capture_dir(environ: Mapping[str, str]) -> Path:
    override_dir = _clean_env_value(environ.get(LLM_CAPTURE_DIR_ENV))
    if override_dir is None:
        return _default_capture_dir()
    return Path(override_dir).expanduser()


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


def _extract_json_candidates_from_text(content: str) -> list[dict[str, object]]:
    normalized_content = content.strip()
    candidates = [normalized_content]

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", normalized_content, re.DOTALL)
    if fenced_match is not None:
        candidates.append(fenced_match.group(1).strip())

    found: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
        else:
            if not isinstance(parsed, dict):
                raise LLMInvalidResponseError("provider JSON content must be an object")
            found.append(parsed)
            continue

        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate, idx=match.start())
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(parsed, dict):
                found.append(parsed)

    if found:
        return found

    raise LLMInvalidResponseError("provider returned invalid JSON content") from last_error


def _extract_required_schema_keys(response_schema: Mapping[str, object] | None) -> set[str]:
    if response_schema is None:
        return set()
    raw_required = response_schema.get("required")
    if not isinstance(raw_required, list):
        return set()
    required_keys = {item for item in raw_required if isinstance(item, str)}
    if len(required_keys) != len(raw_required):
        return set()
    return required_keys


def _iter_dict_candidates(value: object, *, include_self: bool = True) -> Sequence[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        if include_self and all(isinstance(key, str) for key in value):
            found.append(cast(dict[str, object], value))
        for nested_value in value.values():
            found.extend(_iter_dict_candidates(nested_value))
    elif isinstance(value, list):
        for item in value:
            found.extend(_iter_dict_candidates(item))
    return found


def _dedupe_dict_candidates(candidates: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    distinct: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in candidates:
        fingerprint = json.dumps(
            candidate,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        distinct.append(candidate)
    return distinct


def _match_schema_candidates(
    candidates: Sequence[dict[str, object]],
    *,
    required_keys: set[str],
) -> list[dict[str, object]]:
    if not required_keys:
        return list(candidates)
    matching = [candidate for candidate in candidates if required_keys.issubset(candidate.keys())]
    return _dedupe_dict_candidates(matching)


def _is_leaf_dict(candidate: Mapping[str, object]) -> bool:
    return all(not isinstance(value, dict) for value in candidate.values())


def _looks_like_structured_json_text(content: str) -> bool:
    normalized = content.strip()
    if not normalized:
        return False
    if normalized.startswith("{") or normalized.startswith("["):
        return True
    for fenced_match in re.finditer(r"```([^\n`]*)\n?(.*?)```", normalized, re.DOTALL):
        fence_language = fenced_match.group(1).strip().lower()
        fence_body = fenced_match.group(2).lstrip()
        if fence_language in {"json", "application/json"}:
            return True
        if fence_body.startswith("{") or fence_body.startswith("["):
            return True
    return re.search(r'\{\s*"', normalized) is not None


def _is_provider_metadata_object(candidate: Mapping[str, object]) -> bool:
    block_type = candidate.get("type")
    if not isinstance(block_type, str):
        return False
    return "text" in candidate or "input" in candidate or "content" in candidate


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
        request_name: str | None = None,
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
            structured_body = self._post_messages(structured_payload, timeout_seconds=timeout_seconds)
            self._capture_raw_response(
                body=structured_body,
                model_name=model_name,
                request_name=request_name,
                phase="structured",
            )
            return self._parse_response_body(structured_body, response_schema=response_schema)
        except LLMInvalidResponseError as structured_exc:
            self._trace_log(
                event="provider_structured_invalid",
                request_name=request_name,
                model_name=model_name,
                error_message=str(structured_exc),
            )
            fallback_payload = dict(payload)
            try:
                fallback_body = self._post_messages(fallback_payload, timeout_seconds=timeout_seconds)
                self._capture_raw_response(
                    body=fallback_body,
                    model_name=model_name,
                    request_name=request_name,
                    phase="fallback",
                )
                parsed_fallback_body = self._parse_response_body(
                    fallback_body,
                    response_schema=response_schema,
                )
                self._trace_log(
                    event="provider_fallback_success",
                    request_name=request_name,
                    model_name=model_name,
                )
                return parsed_fallback_body
            except LLMInvalidResponseError as fallback_exc:
                self._trace_log(
                    event="provider_fallback_invalid",
                    request_name=request_name,
                    model_name=model_name,
                    error_message=str(fallback_exc),
                )
                raise fallback_exc from structured_exc

    def _trace_log(
        self,
        *,
        event: str,
        request_name: str | None,
        model_name: str,
        error_message: str | None = None,
    ) -> None:
        env_values = _build_env_values()
        if not _is_agent_trace_logging_enabled(env_values):
            return

        request_label = request_name or "unknown"
        message = f"{event} request_name={request_label} model_name={model_name}"
        if error_message is not None:
            message = f'{message} error_message="{error_message}"'
        LOGGER.info(message)

    def _capture_raw_response(
        self,
        *,
        body: object,
        model_name: str,
        request_name: str | None,
        phase: str,
    ) -> None:
        env_values = _build_env_values()
        if not _is_raw_capture_enabled(env_values):
            return

        capture_payload = {
            "request_name": request_name,
            "model_name": model_name,
            "phase": phase,
            "body": body,
        }
        capture_dir = _resolve_capture_dir(env_values)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        request_label = request_name or "unknown"
        filename = f"{timestamp}-{phase}-{request_label}-{uuid4().hex}.json"
        capture_path = capture_dir / filename
        try:
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            capture_path.write_text(
                json.dumps(capture_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            raise LLMProviderError(
                f"failed to write raw response capture at {capture_path}: {exc}"
            ) from exc

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

    def _parse_response_body(
        self,
        body: object,
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            content_blocks = body["content"]
        except (KeyError, TypeError) as exc:
            raise LLMInvalidResponseError("provider response has no content blocks") from exc

        if not isinstance(content_blocks, list):
            raise LLMInvalidResponseError("provider content blocks must be a list")

        required_keys = _extract_required_schema_keys(response_schema)
        text_candidates: list[dict[str, object]] = []
        deferred_text_error: LLMInvalidResponseError | None = None
        for block in content_blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                raise LLMInvalidResponseError("provider text block must contain a string")
            try:
                text_candidates.extend(_extract_json_candidates_from_text(text))
            except LLMInvalidResponseError as exc:
                if _looks_like_structured_json_text(text) and deferred_text_error is None:
                    deferred_text_error = exc
                continue

        if text_candidates and not required_keys:
            return text_candidates[0]

        text_schema_matches = _match_schema_candidates(text_candidates, required_keys=required_keys)
        if len(text_schema_matches) > 1:
            raise LLMInvalidResponseError(
                "provider response has multiple schema-matching structured objects"
            )
        if len(text_schema_matches) == 1:
            return text_schema_matches[0]
        if deferred_text_error is not None and not required_keys:
            raise deferred_text_error

        recursive_candidates = _iter_dict_candidates(body, include_self=False)
        if recursive_candidates and not required_keys:
            non_metadata_candidates = [
                candidate
                for candidate in recursive_candidates
                if not _is_provider_metadata_object(candidate)
            ]
            if non_metadata_candidates:
                leaf_candidates = [
                    candidate for candidate in non_metadata_candidates if _is_leaf_dict(candidate)
                ]
                if leaf_candidates:
                    return leaf_candidates[0]
                return non_metadata_candidates[0]

            leaf_candidates = [candidate for candidate in recursive_candidates if _is_leaf_dict(candidate)]
            if leaf_candidates:
                return leaf_candidates[0]
            return recursive_candidates[0]

        recursive_schema_matches = _match_schema_candidates(
            recursive_candidates,
            required_keys=required_keys,
        )
        if len(recursive_schema_matches) > 1:
            raise LLMInvalidResponseError(
                "provider response has multiple schema-matching structured objects"
            )
        if len(recursive_schema_matches) == 1:
            return recursive_schema_matches[0]

        if deferred_text_error is not None:
            raise deferred_text_error
        if required_keys:
            raise LLMInvalidResponseError("provider response has no schema-matching structured content")
        raise LLMInvalidResponseError("provider response has no extractable structured content")


def build_provider(
    config: ProviderConfig,
    *,
    http_client: httpx.Client | None = None,
) -> AnthropicChatProvider:
    if config.kind != "anthropic":
        raise ValueError(f"unsupported provider kind: {config.kind}")
    return AnthropicChatProvider(config, http_client=http_client)


LLMProviderConfig = ProviderConfig
