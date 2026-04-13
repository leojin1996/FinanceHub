from __future__ import annotations

import json
import os

import pytest
from pydantic import BaseModel

_API_KEY_ENV = "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY"

pytestmark = pytest.mark.live


def _skip_without_api_key() -> str:
    key = os.environ.get(_API_KEY_ENV)
    if not key:
        pytest.skip(f"{_API_KEY_ENV} not set")
    return key


class _SimpleOutput(BaseModel):
    answer: str


def test_live_single_tool_call_and_submit() -> None:
    from openai import OpenAI

    api_key = _skip_without_api_key()
    client = OpenAI(api_key=api_key)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_date",
                "description": "Return today's date as a string.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_result",
                "description": "Submit the final output.",
                "parameters": _SimpleOutput.model_json_schema(),
            },
        },
    ]

    messages: list[dict[str, object]] = [
        {"role": "system", "content": "You are a helpful assistant. Call get_current_date first, then call submit_result with the answer."},
        {"role": "user", "content": "What is today's date?"},
    ]

    for _ in range(5):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            timeout=30.0,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            break
        messages.append(message.model_dump())
        for tc in message.tool_calls:
            if tc.function.name == "submit_result":
                parsed = json.loads(tc.function.arguments)
                output = _SimpleOutput.model_validate(parsed)
                assert isinstance(output.answer, str)
                assert len(output.answer) > 0
                return
            if tc.function.name == "get_current_date":
                from datetime import date
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": date.today().isoformat()}
                )

    pytest.fail("model did not call submit_result within 5 iterations")


def test_live_multi_tool_loop() -> None:
    from openai import OpenAI

    api_key = _skip_without_api_key()
    client = OpenAI(api_key=api_key)

    class _MultiOutput(BaseModel):
        summary: str

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_news",
                "description": "Get today's top headline.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_result",
                "description": "Submit the final summary.",
                "parameters": _MultiOutput.model_json_schema(),
            },
        },
    ]

    messages: list[dict[str, object]] = [
        {"role": "system", "content": "You are a helpful assistant. Use tools to gather info, then submit_result."},
        {"role": "user", "content": "Give me a summary of Beijing weather and today's news."},
    ]

    tool_calls_made: list[str] = []
    for _ in range(8):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            timeout=30.0,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            break
        messages.append(message.model_dump())
        for tc in message.tool_calls:
            tool_calls_made.append(tc.function.name)
            if tc.function.name == "submit_result":
                parsed = json.loads(tc.function.arguments)
                output = _MultiOutput.model_validate(parsed)
                assert isinstance(output.summary, str)
                assert len(tool_calls_made) >= 2
                return
            fake_results = {
                "get_weather": '{"temp": "22C", "condition": "sunny"}',
                "get_news": '{"headline": "AI advances continue"}',
            }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": fake_results.get(tc.function.name, "{}"),
                }
            )

    pytest.fail("model did not call submit_result within 8 iterations")
