from __future__ import annotations

import json

import httpx
from openai import OpenAI


def _mock_transport_with_tool_call(
    tool_call_id: str = "call_abc123",
    function_name: str = "get_weather",
    function_arguments: str = '{"location": "Beijing"}',
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": function_name,
                                        "arguments": function_arguments,
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    return httpx.MockTransport(handler)


def _mock_transport_with_error(status_code: int) -> httpx.MockTransport:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(status_code, json={"error": {"message": "transient"}})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-retry",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "recovered"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    return httpx.MockTransport(handler)


def test_sdk_tool_call_round_trip() -> None:
    transport = _mock_transport_with_tool_call()
    client = OpenAI(api_key="test-key", http_client=httpx.Client(transport=transport))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                },
            }
        ],
    )
    message = response.choices[0].message
    assert message.tool_calls is not None
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0].function.name == "get_weather"
    assert json.loads(message.tool_calls[0].function.arguments) == {"location": "Beijing"}


def test_sdk_tool_result_message_format() -> None:
    transport = _mock_transport_with_tool_call(
        tool_call_id="call_xyz",
        function_name="submit_result",
        function_arguments='{"risk_tier": "R3"}',
    )
    client = OpenAI(api_key="test-key", http_client=httpx.Client(transport=transport))
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_prev",
                    "type": "function",
                    "function": {"name": "get_data", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_prev", "content": '{"data": "value"}'},
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_result",
                    "description": "Submit",
                    "parameters": {
                        "type": "object",
                        "properties": {"risk_tier": {"type": "string"}},
                        "required": ["risk_tier"],
                    },
                },
            }
        ],
    )
    assert response.choices[0].message.tool_calls is not None


def test_sdk_submit_result_argument_parsing() -> None:
    arguments_json = json.dumps({"risk_tier": "R2", "liquidity_preference": "high"})
    transport = _mock_transport_with_tool_call(
        function_name="submit_result",
        function_arguments=arguments_json,
    )
    client = OpenAI(api_key="test-key", http_client=httpx.Client(transport=transport))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_result",
                    "description": "Submit",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    tool_call = response.choices[0].message.tool_calls[0]
    parsed = json.loads(tool_call.function.arguments)
    assert parsed == {"risk_tier": "R2", "liquidity_preference": "high"}


from financehub_market_api.recommendation.agents.provider import (
    OpenAIChatProvider,
    ProviderConfig,
)


def test_sdk_retry_on_transient_error() -> None:
    transport = _mock_transport_with_error(500)
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=transport),
        max_retries=2,
    )
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
    )
    assert response.choices[0].message.content == "recovered"


def test_chat_with_tools_provider_returns_tool_calls() -> None:
    transport = _mock_transport_with_tool_call(
        function_name="submit_result",
        function_arguments='{"verdict": "approve"}',
    )
    provider = OpenAIChatProvider(
        ProviderConfig(
            name="openai",
            kind="openai",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        ),
        http_client=httpx.Client(transport=transport),
    )
    result = provider.chat_with_tools(
        model_name="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_result",
                    "description": "Submit",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        timeout_seconds=10.0,
    )
    assert "tool_calls" in result
    assert result["tool_calls"][0]["function"]["name"] == "submit_result"
