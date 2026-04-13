from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import httpx

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
UVICORN_ERROR_LOGGER = logging.getLogger("uvicorn.error")

ProviderKind = Literal["openai"]
OpenAIWireAPI = Literal["chat_completions", "responses"]

OPENAI_PROVIDER_NAME = "openai"
OPENAI_DEFAULT_MODEL = "gpt-5.4"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_WIRE_API: OpenAIWireAPI = "chat_completions"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
OPENAI_MAX_ATTEMPTS = 3
OPENAI_RETRY_BACKOFF_SECONDS = 1.0
LLM_CAPTURE_RAW_RESPONSES_ENV = "FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES"
LLM_CAPTURE_DIR_ENV = "FINANCEHUB_LLM_CAPTURE_DIR"
LLM_AGENT_TRACE_LOGS_ENV = "FINANCEHUB_LLM_AGENT_TRACE_LOGS"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
AGENT_MODEL_ROUTE_ENV_NAMES = {
    "user_profile_analyst": "USER_PROFILE_ANALYST",
    "market_intelligence": "MARKET_INTELLIGENCE",
    "product_match_expert": "PRODUCT_MATCH_EXPERT",
    "compliance_risk_officer": "COMPLIANCE_RISK_OFFICER",
    "manager_coordinator": "MANAGER_COORDINATOR",
}
LEGACY_AGENT_MODEL_ROUTE_ENV_NAMES = {
    "user_profile_analyst": ("USER_PROFILE",),
    "product_match_expert": (
        "FUND_SELECTION",
        "WEALTH_SELECTION",
        "STOCK_SELECTION",
    ),
    "manager_coordinator": ("EXPLANATION",),
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


def _default_openai_model(env_values: Mapping[str, str]) -> str:
    return (
        _clean_env_value(env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_MODEL_DEFAULT"))
        or OPENAI_DEFAULT_MODEL
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


def raw_capture_enabled(environ: Mapping[str, str]) -> bool:
    return _is_truthy_env_value(environ.get(LLM_CAPTURE_RAW_RESPONSES_ENV))


def _is_raw_capture_enabled(environ: Mapping[str, str]) -> bool:
    return raw_capture_enabled(environ)


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


def _emit_trace_log(message: str, *args: object) -> None:
    LOGGER.info(message, *args)
    if not logging.getLogger().handlers:
        UVICORN_ERROR_LOGGER.info(message, *args)


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    kind: ProviderKind
    api_key: str
    base_url: str
    wire_api: OpenAIWireAPI = OPENAI_DEFAULT_WIRE_API


@dataclass(frozen=True)
class AgentModelRoute:
    provider_name: str
    model_name: str


DEFAULT_AGENT_MODEL_ROUTES = {
    agent_name: AgentModelRoute(
        provider_name=OPENAI_PROVIDER_NAME,
        model_name=OPENAI_DEFAULT_MODEL,
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

    openai_api_key = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")
    )
    openai_base_url = _clean_env_value(
        env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL")
    )
    openai_wire_api = _parse_openai_wire_api(
        env_values.get("FINANCEHUB_LLM_PROVIDER_OPENAI_WIRE_API")
    )
    if openai_api_key:
        providers[OPENAI_PROVIDER_NAME] = ProviderConfig(
            name=OPENAI_PROVIDER_NAME,
            kind="openai",
            api_key=openai_api_key,
            base_url=_normalize_base_url(openai_base_url or OPENAI_DEFAULT_BASE_URL),
            wire_api=openai_wire_api,
        )

    return providers


def _load_agent_model_routes(env_values: Mapping[str, str]) -> dict[str, AgentModelRoute]:
    default_model = _default_openai_model(env_values)
    routes = {
        agent_name: AgentModelRoute(
            provider_name=OPENAI_PROVIDER_NAME,
            model_name=default_model,
        )
        for agent_name in DEFAULT_AGENT_MODEL_ROUTES
    }

    for agent_name, env_name in AGENT_MODEL_ROUTE_ENV_NAMES.items():
        model_name = _clean_env_value(env_values.get(f"FINANCEHUB_LLM_AGENT_{env_name}_MODEL"))
        if model_name is None:
            model_name = _legacy_agent_model_override(env_values, agent_name)
        routes[agent_name] = AgentModelRoute(
            provider_name=OPENAI_PROVIDER_NAME,
            model_name=model_name or default_model,
        )

    return routes


def _legacy_agent_model_override(
    env_values: Mapping[str, str],
    agent_name: str,
) -> str | None:
    legacy_env_names = LEGACY_AGENT_MODEL_ROUTE_ENV_NAMES.get(agent_name, ())
    if not legacy_env_names:
        return None

    legacy_models = [
        model_name
        for env_name in legacy_env_names
        if (model_name := _clean_env_value(env_values.get(f"FINANCEHUB_LLM_AGENT_{env_name}_MODEL")))
        is not None
    ]
    if not legacy_models:
        return None

    distinct_models = list(dict.fromkeys(legacy_models))
    if agent_name == "product_match_expert" and len(distinct_models) > 1:
        return None
    return distinct_models[0]


def _parse_openai_wire_api(value: str | None) -> OpenAIWireAPI:
    cleaned = _clean_env_value(value)
    if cleaned is None:
        return OPENAI_DEFAULT_WIRE_API
    normalized = cleaned.strip().lower().replace("-", "_")
    if normalized == "responses":
        return "responses"
    if normalized in {"chat", "chat_completions", "chat_completion"}:
        return "chat_completions"
    return OPENAI_DEFAULT_WIRE_API


def _array_required_field_candidates_from_text(
    content: str,
    *,
    response_schema: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if response_schema is None:
        return []

    raw_properties = response_schema.get("properties")
    if not isinstance(raw_properties, dict):
        return []

    required_keys = _extract_required_schema_keys(response_schema)
    if not required_keys:
        return []

    property_schemas = {
        key: value for key, value in raw_properties.items() if isinstance(value, dict)
    }
    if any(property_schemas.get(key, {}).get("type") != "array" for key in required_keys):
        return []

    snippets = [content.strip()]
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
    if fenced_match is not None:
        snippets.insert(0, fenced_match.group(1).strip())

    candidates: list[dict[str, object]] = []
    for snippet in snippets:
        candidate: dict[str, object] = {}
        for key in required_keys:
            match = re.search(
                rf'"{re.escape(key)}"\s*:\s*\[(?P<items>.*?)\]\s*(?=,\s*"|\s*\}})',
                snippet,
                re.DOTALL,
            )
            if match is None:
                break
            items = re.findall(
                r'"([^"\\]*(?:\\.[^"\\]*)*)"',
                match.group("items"),
                re.DOTALL,
            )
            candidate[key] = [json.loads(f'"{item}"') for item in items]
        else:
            candidates.append(candidate)
    return _dedupe_dict_candidates(candidates)


def _decode_json_like_string(value: str) -> str:
    return (
        value.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\/", "/")
        .replace("\\\\", "\\")
    )


def _schema_field_candidates_from_text(
    content: str,
    *,
    response_schema: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if response_schema is None:
        return []

    raw_properties = response_schema.get("properties")
    if not isinstance(raw_properties, dict):
        return []

    required_keys = _extract_required_schema_keys(response_schema)
    if not required_keys:
        return []

    property_schemas = {
        key: value for key, value in raw_properties.items() if isinstance(value, dict)
    }
    supported_required_field_types = {"array", "string"}
    if any(
        property_schemas.get(key, {}).get("type") not in supported_required_field_types
        for key in required_keys
    ):
        return []

    snippets = [content.strip()]
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
    if fenced_match is not None:
        snippets.insert(0, fenced_match.group(1).strip())

    candidates: list[dict[str, object]] = []
    for snippet in snippets:
        candidate: dict[str, object] = {}
        for key, property_schema in property_schemas.items():
            field_type = property_schema.get("type")
            if field_type == "array":
                items_schema = property_schema.get("items")
                if not isinstance(items_schema, dict) or items_schema.get("type") != "string":
                    continue
                match = re.search(
                    rf'"{re.escape(key)}"\s*:\s*\[(?P<items>.*?)\]\s*(?=,\s*"|\s*\}})',
                    snippet,
                    re.DOTALL,
                )
                if match is None:
                    continue
                items = re.findall(
                    r'"([^"\\]*(?:\\.[^"\\]*)*)"',
                    match.group("items"),
                    re.DOTALL,
                )
                candidate[key] = [_decode_json_like_string(item) for item in items]
            elif field_type == "string":
                match = re.search(
                    rf'"{re.escape(key)}"\s*:\s*"(?P<value>.*?)(?="\s*(?:,\s*"|\s*\}}))',
                    snippet,
                    re.DOTALL,
                )
                if match is None:
                    continue
                candidate[key] = _decode_json_like_string(match.group("value"))
        if required_keys.issubset(candidate.keys()):
            candidates.append(candidate)
    return _dedupe_dict_candidates(candidates)


def _extract_json_candidates_from_text(
    content: str,
    *,
    response_schema: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
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

    relaxed_candidates = _array_required_field_candidates_from_text(
        normalized_content,
        response_schema=response_schema,
    )
    if relaxed_candidates:
        return relaxed_candidates

    schema_field_candidates = _schema_field_candidates_from_text(
        normalized_content,
        response_schema=response_schema,
    )
    if schema_field_candidates:
        return schema_field_candidates

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


def _extract_schema_property_keys(response_schema: Mapping[str, object] | None) -> set[str]:
    if response_schema is None:
        return set()
    raw_properties = response_schema.get("properties")
    if not isinstance(raw_properties, dict):
        return set()
    return {key for key in raw_properties if isinstance(key, str)}


def _select_best_schema_candidate(
    candidates: Sequence[dict[str, object]],
    *,
    response_schema: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not candidates:
        raise ValueError("candidates must not be empty")
    if len(candidates) == 1:
        return candidates[0]

    schema_property_keys = _extract_schema_property_keys(response_schema)
    if not schema_property_keys:
        return candidates[0]

    best_index = 0
    best_score = (-1, -1, -1)
    for index, candidate in enumerate(candidates):
        matching_keys = len(schema_property_keys.intersection(candidate))
        score = (matching_keys, len(candidate), index)
        if score > best_score:
            best_score = score
            best_index = index
    return candidates[best_index]


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


def _looks_like_usage_metadata(candidate: Mapping[str, object]) -> bool:
    keys = set(candidate)
    if {"input_tokens", "output_tokens"}.issubset(keys):
        return all(isinstance(candidate.get(key), int) for key in {"input_tokens", "output_tokens"})
    if {"prompt_tokens", "completion_tokens", "total_tokens"}.intersection(keys):
        return all(isinstance(candidate.get(key), int) for key in keys if "tokens" in key)
    return False


def _is_provider_metadata_object(candidate: Mapping[str, object]) -> bool:
    if _looks_like_usage_metadata(candidate):
        return True
    block_type = candidate.get("type")
    if isinstance(block_type, str):
        return "text" in candidate or "input" in candidate or "content" in candidate
    if {"role", "content"}.issubset(candidate):
        return True
    if {"index", "message", "finish_reason"}.issubset(candidate):
        return True
    if "choices" in candidate or "usage" in candidate:
        return True
    return False


def _is_retryable_openai_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return False


def _message_text_parts(message: Mapping[str, object]) -> list[str]:
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []

    texts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if not isinstance(text_value, str):
            continue
        block_type = item.get("type")
        if block_type in {None, "text", "output_text", "input_text"}:
            texts.append(text_value)
    return texts


def _has_empty_openai_message_content(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    legacy_content = body.get("content")
    if isinstance(legacy_content, list):
        return len(legacy_content) == 0
    output_blocks = _response_output_content_blocks(body)
    if output_blocks is not None:
        return len(output_blocks) == 0
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        return True
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        texts = [text.strip() for text in _message_text_parts(message) if text.strip()]
        if texts:
            return False
    return True


def _response_format_name(request_name: str | None) -> str:
    raw_name = request_name or "structured_output"
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name).strip("_")
    return sanitized or "structured_output"


def _response_output_content_blocks(body: Mapping[str, object]) -> list[object] | None:
    output = body.get("output")
    if not isinstance(output, list):
        return None

    content_blocks: list[object] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            content_blocks.extend(content)
    return content_blocks


class OpenAIChatProvider:
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
        payload = self._base_payload(model_name=model_name, messages=messages)
        structured_payload = self._structured_payload(
            payload,
            response_schema=response_schema,
            request_name=request_name,
        )

        try:
            structured_body = self._post_completions(
                structured_payload,
                timeout_seconds=timeout_seconds,
            )
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
                fallback_body = self._post_completions(
                    fallback_payload,
                    timeout_seconds=timeout_seconds,
                )
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
        _emit_trace_log(message)

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

    def _post_completions(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> object:
        endpoint_path = "/responses" if self._config.wire_api == "responses" else "/chat/completions"
        for attempt in range(OPENAI_MAX_ATTEMPTS):
            try:
                response = self._http_client.post(
                    f"{self._config.base_url}{endpoint_path}",
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "content-type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                response_body = response.json()
                if (
                    _has_empty_openai_message_content(response_body)
                    and attempt + 1 < OPENAI_MAX_ATTEMPTS
                ):
                    time.sleep(OPENAI_RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                return response_body
            except httpx.HTTPError as exc:
                if attempt + 1 >= OPENAI_MAX_ATTEMPTS or not _is_retryable_openai_error(exc):
                    raise LLMProviderError(f"OpenAI provider request failed: {exc}") from exc
                time.sleep(OPENAI_RETRY_BACKOFF_SECONDS * (attempt + 1))
            except ValueError as exc:
                raise LLMInvalidResponseError("provider response is not valid JSON") from exc

        raise AssertionError("openai request retry loop exited unexpectedly")

    def _parse_response_body(
        self,
        body: object,
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if isinstance(body, dict) and isinstance(body.get("content"), list):
            return self._parse_legacy_content_blocks(
                cast(list[object], body["content"]),
                response_schema=response_schema,
            )
        if isinstance(body, dict):
            output_blocks = _response_output_content_blocks(body)
            if output_blocks is not None:
                return self._parse_legacy_content_blocks(
                    output_blocks,
                    response_schema=response_schema,
                )

        try:
            choices = body["choices"]
        except (KeyError, TypeError) as exc:
            raise LLMInvalidResponseError("provider response has no choices") from exc

        if not isinstance(choices, list) or len(choices) == 0:
            raise LLMInvalidResponseError("provider response has no choices")

        required_keys = _extract_required_schema_keys(response_schema)
        text_candidates: list[dict[str, object]] = []
        deferred_text_error: LLMInvalidResponseError | None = None

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            for text in _message_text_parts(message):
                try:
                    text_candidates.extend(
                        _extract_json_candidates_from_text(
                            text,
                            response_schema=response_schema,
                        )
                    )
                except LLMInvalidResponseError as exc:
                    if _looks_like_structured_json_text(text) and deferred_text_error is None:
                        deferred_text_error = exc
                    continue

        if text_candidates and not required_keys:
            return _select_best_schema_candidate(
                text_candidates,
                response_schema=response_schema,
            )

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
                return _select_best_schema_candidate(
                    non_metadata_candidates,
                    response_schema=response_schema,
                )
            raise LLMInvalidResponseError("provider response has no extractable structured content")

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

    def _parse_legacy_content_blocks(
        self,
        content_blocks: list[object],
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        required_keys = _extract_required_schema_keys(response_schema)
        text_candidates: list[dict[str, object]] = []
        deferred_text_error: LLMInvalidResponseError | None = None

        for block in content_blocks:
            if not isinstance(block, dict) or block.get("type") not in {None, "text", "output_text", "input_text"}:
                continue
            text = block.get("text")
            if not isinstance(text, str):
                raise LLMInvalidResponseError("provider text block must contain a string")
            try:
                text_candidates.extend(
                    _extract_json_candidates_from_text(
                        text,
                        response_schema=response_schema,
                    )
                )
            except LLMInvalidResponseError as exc:
                if _looks_like_structured_json_text(text) and deferred_text_error is None:
                    deferred_text_error = exc
                continue

        if text_candidates and not required_keys:
            return _select_best_schema_candidate(
                text_candidates,
                response_schema=response_schema,
            )

        text_schema_matches = _match_schema_candidates(text_candidates, required_keys=required_keys)
        if len(text_schema_matches) > 1:
            raise LLMInvalidResponseError(
                "provider response has multiple schema-matching structured objects"
            )
        if len(text_schema_matches) == 1:
            return text_schema_matches[0]
        if deferred_text_error is not None and not required_keys:
            raise deferred_text_error

        recursive_candidates = _iter_dict_candidates({"content": content_blocks}, include_self=False)
        if recursive_candidates and not required_keys:
            non_metadata_candidates = [
                candidate
                for candidate in recursive_candidates
                if not _is_provider_metadata_object(candidate)
            ]
            if non_metadata_candidates:
                return _select_best_schema_candidate(
                    non_metadata_candidates,
                    response_schema=response_schema,
                )
            raise LLMInvalidResponseError("provider response has no extractable structured content")

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

    def _base_payload(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
    ) -> dict[str, object]:
        if self._config.wire_api == "responses":
            return {
                "model": model_name,
                "input": messages,
            }
        return {
            "model": model_name,
            "messages": messages,
        }

    def _structured_payload(
        self,
        payload: dict[str, object],
        *,
        response_schema: dict[str, object],
        request_name: str | None,
    ) -> dict[str, object]:
        structured_payload = dict(payload)
        if self._config.wire_api == "responses":
            structured_payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _response_format_name(request_name),
                    "schema": response_schema,
                }
            }
            return structured_payload

        structured_payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": _response_format_name(request_name),
                "schema": response_schema,
            },
        }
        return structured_payload


def build_provider(
    config: ProviderConfig,
    *,
    http_client: httpx.Client | None = None,
) -> OpenAIChatProvider:
    if config.kind != "openai":
        raise ValueError(f"unsupported provider kind: {config.kind}")
    return OpenAIChatProvider(config, http_client=http_client)


LLMProviderConfig = ProviderConfig
