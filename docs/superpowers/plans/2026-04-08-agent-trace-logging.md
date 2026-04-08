# Recommendation Agent Trace Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in trace logs for all six recommendation agents so local development logs show request start, request finish, provider fallback, and error details with a trimmed structured-response summary.

**Architecture:** Keep the logging feature narrow and additive. Add a small logging helper layer in the Anthropic runtime for per-agent start/finish/error logs, add lightweight provider-stage logs for structured/fallback transitions, and gate everything behind an explicit environment variable that local `.env.local` can enable while production stays off by default.

**Tech Stack:** Python 3.12, standard-library `logging`, httpx, Pydantic, pytest, FastAPI

---

## File Map

- `backend/financehub_market_api/recommendation/agents/anthropic_runtime.py`
  - Add trace-log helpers, response-summary trimming, and per-agent start/finish/error logging in `_BaseStructuredOutputAgent._execute()`.
- `backend/financehub_market_api/recommendation/agents/provider.py`
  - Add the trace-log env parser and provider-level structured/fallback logging hooks.
- `backend/tests/test_recommendation_provider.py`
  - Cover provider trace logging and trace env parsing.
- `backend/tests/test_recommendation_flow.py`
  - Cover end-to-end agent logging from the runtime layer with `caplog`.
- `backend/.env.local`
  - Enable `FINANCEHUB_LLM_AGENT_TRACE_LOGS=true` for local development verification.

### Task 1: Add the trace-log gate and provider-stage logging

**Files:**
- Modify: `backend/financehub_market_api/recommendation/agents/provider.py`
- Test: `backend/tests/test_recommendation_provider.py`

- [ ] **Step 1: Write the failing provider logging tests**

Add these tests near the existing provider tests in `backend/tests/test_recommendation_provider.py`:

```python
import logging


def test_trace_logs_are_disabled_by_default() -> None:
    assert provider_module._is_agent_trace_logging_enabled({}) is False


def test_trace_logs_accept_truthy_and_falsey_values() -> None:
    assert provider_module._is_agent_trace_logging_enabled(
        {"FINANCEHUB_LLM_AGENT_TRACE_LOGS": "true"}
    ) is True
    assert provider_module._is_agent_trace_logging_enabled(
        {"FINANCEHUB_LLM_AGENT_TRACE_LOGS": "0"}
    ) is False


def test_provider_logs_structured_invalid_and_fallback_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    http_client = _SequentialFakeHttpClient(
        [
            {"content": []},
            {"content": [{"type": "text", "text": '{"summary_zh":"稳健","summary_en":"steady"}'}]},
        ]
    )
    provider = AnthropicChatProvider(
        ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key="anthropic-test-key",
            base_url="https://oneapi.hk/v1",
        ),
        http_client=http_client,
    )

    with caplog.at_level(logging.INFO):
        payload = provider.chat_json(
            model_name="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
                {"role": "user", "content": "Return summary_zh and summary_en."},
            ],
            response_schema={"type": "object"},
            timeout_seconds=5.0,
            request_name="market_intelligence",
        )

    assert payload == {"summary_zh": "稳健", "summary_en": "steady"}
    assert "provider_structured_invalid request_name=market_intelligence model_name=claude-sonnet-4-6" in caplog.text
    assert "provider_fallback_success request_name=market_intelligence model_name=claude-sonnet-4-6" in caplog.text
```

- [ ] **Step 2: Run the provider tests and verify the new logging assertions fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q tests/test_recommendation_provider.py
```

Expected: FAIL because there is no trace-log gate and no provider-stage logging yet.

- [ ] **Step 3: Add the provider trace-log helpers**

In `backend/financehub_market_api/recommendation/agents/provider.py`, add a logger and the new env constant near the existing module constants:

```python
import logging
```

```python
LOGGER = logging.getLogger(__name__)
LLM_AGENT_TRACE_LOGS_ENV = "FINANCEHUB_LLM_AGENT_TRACE_LOGS"
```

Add the gate helper near `_is_raw_capture_enabled()`:

```python
def _is_agent_trace_logging_enabled(environ: Mapping[str, str]) -> bool:
    return _is_truthy_env_value(environ.get(LLM_AGENT_TRACE_LOGS_ENV))
```

Add a provider log helper inside `AnthropicChatProvider`:

```python
    def _trace_log(
        self,
        *,
        event: str,
        model_name: str,
        request_name: str | None,
        error_message: str | None = None,
    ) -> None:
        env_values = _build_env_values()
        if not _is_agent_trace_logging_enabled(env_values):
            return

        message = (
            f"{event} request_name={request_name or 'unknown'} "
            f"model_name={model_name}"
        )
        if error_message:
            message = f'{message} error_message="{error_message}"'
        LOGGER.info(message)
```

- [ ] **Step 4: Log structured/fallback transitions in `chat_json()`**

Update `chat_json()` in `provider.py` so the structured-invalid and fallback paths log:

```python
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
                model_name=model_name,
                request_name=request_name,
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
                parsed = self._parse_response_body(fallback_body, response_schema=response_schema)
                self._trace_log(
                    event="provider_fallback_success",
                    model_name=model_name,
                    request_name=request_name,
                )
                return parsed
            except LLMInvalidResponseError as fallback_exc:
                self._trace_log(
                    event="provider_fallback_invalid",
                    model_name=model_name,
                    request_name=request_name,
                    error_message=str(fallback_exc),
                )
                raise fallback_exc from structured_exc
```

- [ ] **Step 5: Re-run provider tests**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q tests/test_recommendation_provider.py
```

Expected: PASS for the new provider logging tests and the existing provider suite.

- [ ] **Step 6: Commit the provider logging slice**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub
git add backend/financehub_market_api/recommendation/agents/provider.py backend/tests/test_recommendation_provider.py
git commit -m "Add provider trace logging for agent fallback"
```

### Task 2: Add per-agent runtime start/finish/error logs with trimmed response summaries

**Files:**
- Modify: `backend/financehub_market_api/recommendation/agents/anthropic_runtime.py`
- Test: `backend/tests/test_recommendation_flow.py`

- [ ] **Step 1: Write the failing runtime logging tests**

Add a trace-enabled test to `backend/tests/test_recommendation_flow.py` that uses `caplog`:

```python
import logging


def test_recommendation_flow_logs_agent_start_and_finish_when_trace_enabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("FINANCEHUB_LLM_AGENT_TRACE_LOGS", "true")
    provider = FakeStructuredProvider(
        responses={
            "user_profile": {"profile_focus_zh": "稳健增值", "profile_focus_en": "steady growth"},
            "market_intelligence": {"summary_zh": "市场偏稳", "summary_en": "market steady"},
            "fund_selection": {"ranked_ids": ["fund_1"]},
            "wealth_selection": {"ranked_ids": ["wealth_1"]},
            "stock_selection": {"ranked_ids": ["stock_1"]},
            "explanation": {
                "why_this_plan_zh": ["第一条原因"],
                "why_this_plan_en": ["first reason"],
            },
        }
    )
    runtime = AnthropicMultiAgentRuntime(provider=provider, model_name="claude-sonnet-4-6")

    with caplog.at_level(logging.INFO):
        result = runtime.apply(map_user_profile("balanced"), _build_complete_state())

    assert result.assisted is True
    assert "agent_request_start request_name=user_profile model_name=claude-sonnet-4-6" in caplog.text
    assert "agent_request_finish request_name=explanation model_name=claude-sonnet-4-6" in caplog.text
    assert "response_summary=" in caplog.text
```

Add an error-path assertion in the same file:

```python
def test_recommendation_flow_logs_agent_error_when_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("FINANCEHUB_LLM_AGENT_TRACE_LOGS", "true")
    provider = FakeStructuredProvider(error=LLMProviderError("boom"))
    runtime = AnthropicMultiAgentRuntime(provider=provider, model_name="claude-opus-4-6")

    with caplog.at_level(logging.INFO):
        result = runtime.apply(map_user_profile("balanced"), _build_complete_state())

    assert result.assisted is False
    assert "agent_request_error request_name=user_profile model_name=claude-opus-4-6" in caplog.text
    assert 'error_type=LLMProviderError error_message="structured-output provider request failed: boom"' in caplog.text
```

- [ ] **Step 2: Run the flow tests and verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q tests/test_recommendation_flow.py
```

Expected: FAIL because `_BaseStructuredOutputAgent._execute()` does not log start/finish/error yet.

- [ ] **Step 3: Add the runtime summary-trimming helpers**

In `backend/financehub_market_api/recommendation/agents/anthropic_runtime.py`, add:

```python
import json
import logging
import time
from collections.abc import Mapping, Sequence
```

```python
LOGGER = logging.getLogger(__name__)
_MAX_TRACE_STRING_LENGTH = 160
_MAX_TRACE_LIST_ITEMS = 5
_MAX_TRACE_OBJECT_KEYS = 8
```

Add helper functions above `_BaseStructuredOutputAgent`:

```python
def _trim_trace_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= _MAX_TRACE_STRING_LENGTH:
            return value
        return value[:_MAX_TRACE_STRING_LENGTH] + "...(truncated)"
    if isinstance(value, list):
        trimmed = [_trim_trace_value(item) for item in value[:_MAX_TRACE_LIST_ITEMS]]
        if len(value) > _MAX_TRACE_LIST_ITEMS:
            trimmed.append("...(truncated)")
        return trimmed
    if isinstance(value, Mapping):
        trimmed: dict[str, object] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= _MAX_TRACE_OBJECT_KEYS:
                trimmed["...(truncated)"] = "..."
                break
            if isinstance(key, str):
                trimmed[key] = _trim_trace_value(nested)
        return trimmed
    return value


def _response_summary(payload: Mapping[str, object]) -> str:
    return json.dumps(_trim_trace_value(dict(payload)), ensure_ascii=False, sort_keys=True)
```

- [ ] **Step 4: Add runtime start/finish/error logging in `_BaseStructuredOutputAgent._execute()`**

Replace the body of `_execute()` with timing and logging:

```python
    def _execute(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> dict[str, object]:
        env_values = _build_env_values()
        trace_enabled = _is_agent_trace_logging_enabled(env_values)
        started_at = time.perf_counter()
        if trace_enabled:
            LOGGER.info(
                "agent_request_start request_name=%s model_name=%s",
                self._request_name,
                self._model_name,
            )
        try:
            payload = self._provider.chat_json(
                model_name=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_schema=response_schema,
                timeout_seconds=self._request_timeout_seconds,
                request_name=self._request_name,
            )
        except LLMInvalidResponseError:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            if trace_enabled:
                LOGGER.warning(
                    'agent_request_error request_name=%s model_name=%s duration_ms=%s error_type=%s error_message="%s"',
                    self._request_name,
                    self._model_name,
                    duration_ms,
                    "LLMInvalidResponseError",
                    "invalid structured response",
                )
            raise
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            provider_exc = LLMProviderError(f"structured-output provider request failed: {exc}")
            if trace_enabled:
                LOGGER.warning(
                    'agent_request_error request_name=%s model_name=%s duration_ms=%s error_type=%s error_message="%s"',
                    self._request_name,
                    self._model_name,
                    duration_ms,
                    provider_exc.__class__.__name__,
                    str(provider_exc),
                )
            raise provider_exc from exc

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if trace_enabled:
            LOGGER.info(
                "agent_request_finish request_name=%s model_name=%s duration_ms=%s response_summary=%s",
                self._request_name,
                self._model_name,
                duration_ms,
                _response_summary(payload),
            )
        return payload
```

Use the existing `_build_env_values()` and `_is_agent_trace_logging_enabled()` from `provider.py` rather than inventing a second env parser.

- [ ] **Step 5: Re-run the flow tests**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q tests/test_recommendation_flow.py
```

Expected: PASS for the new start/finish/error logging assertions and the existing flow coverage.

- [ ] **Step 6: Commit the runtime logging slice**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub
git add backend/financehub_market_api/recommendation/agents/anthropic_runtime.py backend/tests/test_recommendation_flow.py
git commit -m "Add recommendation agent trace logs"
```

### Task 3: Enable local tracing and verify logs in the running backend

**Files:**
- Modify: `backend/.env.local`
- Verify: `backend/tmp/run-logs/backend-8000.log`

- [ ] **Step 1: Enable local trace logging in `.env.local`**

Add this line to `backend/.env.local` if it is not already present:

```dotenv
FINANCEHUB_LLM_AGENT_TRACE_LOGS=true
```

- [ ] **Step 2: Run the targeted logging tests together**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q tests/test_recommendation_provider.py tests/test_recommendation_flow.py
```

Expected: PASS and no regression in provider/runtime coverage.

- [ ] **Step 3: Run the full backend test suite**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend
python3 -m pytest -q
```

Expected: PASS with the repository’s current warning profile unchanged.

- [ ] **Step 4: Restart the backend process so the new env and logging code are live**

Use the existing local backend runner:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub
screen -S financehub-backend -X quit || true
screen -dmS financehub-backend zsh -lc 'cd /Users/zefengjin/Desktop/Practice/FinanceHub/backend && python3 -m uvicorn financehub_market_api.main:app --host 127.0.0.1 --port 8000 >> /Users/zefengjin/Desktop/Practice/FinanceHub/backend/tmp/run-logs/backend-8000.log 2>&1'
```

- [ ] **Step 5: Exercise the recommendation endpoint and inspect the trace log**

Run:

```bash
curl -s -X POST http://127.0.0.1:8000/api/recommendations/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "includeAggressiveOption": true,
    "questionnaireAnswers": [],
    "historicalHoldings": [],
    "historicalTransactions": [],
    "riskAssessmentResult": {
      "baseProfile": "balanced",
      "finalProfile": "balanced",
      "totalScore": 60,
      "dimensionLevels": {
        "riskTolerance": "medium",
        "investmentHorizon": "medium",
        "capitalStability": "medium",
        "investmentExperience": "medium",
        "returnObjective": "medium"
      },
      "dimensionScores": {
        "riskTolerance": 12,
        "investmentHorizon": 12,
        "capitalStability": 12,
        "investmentExperience": 12,
        "returnObjective": 12
      }
    }
  }'
tail -n 80 /Users/zefengjin/Desktop/Practice/FinanceHub/backend/tmp/run-logs/backend-8000.log
```

Expected: the log tail includes six `agent_request_start` lines, six `agent_request_finish` lines (or matching `agent_request_error` lines if a stage degrades), plus any `provider_structured_invalid` / `provider_fallback_success` lines for lower-level transitions.

- [ ] **Step 6: Commit the env and verification slice**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub
git add backend/.env.local
git commit -m "Enable local trace logging for recommendation agents"
```
