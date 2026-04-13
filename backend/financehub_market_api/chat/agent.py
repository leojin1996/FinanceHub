from __future__ import annotations

import json
import logging
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from openai import OpenAI

from ..recommendation.agents.provider import (
    OPENAI_DEFAULT_BASE_URL,
    OPENAI_DEFAULT_MODEL,
    _build_env_values,
    _clean_env_value,
    _normalize_base_url,
    _parse_request_timeout_seconds,
)
from ..service import MarketDataService

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a bilingual financial assistant for FinanceHub, "
    "specializing in the Chinese A-share market.\n"
    "You can help users understand market conditions, look up stock information, "
    "and generate personalized investment recommendations.\n"
    "Always respond in the same language the user used. "
    "Be concise, accurate, and professional.\n"
    "For English user messages, write in English only. "
    "For Chinese user messages, write in Chinese only: do not insert English words "
    "(except unavoidable stock/index codes like 600519 or 000001.SZ).\n"
    "Do not use Markdown in replies (no **bold**, no # headings, no backticks); "
    "the client shows plain text. Use line breaks and punctuation for structure.\n"
    "你是FinanceHub的双语智能理财助手，专注于中国A股市场。\n"
    "你可以帮助用户了解市场状况、查询股票信息、生成个性化投资推荐。\n"
    "请始终使用用户使用的语言回复。回答要简洁、准确、专业。\n"
    "若用户使用中文提问，全文使用中文表述，不要在句中夹杂英文单词或短语"
    "（股票/指数代码等必要符号除外）。\n"
    "不要使用 Markdown 格式（不要用 ** 加粗、不要用 # 标题、不要用反引号代码块）；"
    "界面按纯文本展示，请用换行与中文标点组织层次。"
)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": (
                "Get the current A-share market overview including major index values, "
                "changes, top gainers and losers."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_stocks",
            "description": (
                "Search for stocks by code or name. "
                "Returns matching stock rows with price, change, volume and trend data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Stock code or name to search for, e.g. '600519' or '贵州茅台'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_recommendations",
            "description": (
                "Generate personalized investment recommendations based on a risk profile."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_profile": {
                        "type": "string",
                        "description": (
                            "The user's risk profile level. "
                            "One of: conservative, stable, balanced, growth, aggressive."
                        ),
                        "enum": [
                            "conservative",
                            "stable",
                            "balanced",
                            "growth",
                            "aggressive",
                        ],
                    },
                },
                "required": ["risk_profile"],
            },
        },
    },
]

MAX_TOOL_ROUNDS = 10
CHAT_STREAM_OPENAI_TIMEOUT_DEFAULT = 120.0


class ChatAgentState(TypedDict):
    messages: list[dict[str, Any]]


@dataclass(frozen=True)
class ChatStreamEvent:
    event: Literal["delta", "tool_call", "done", "error"]
    data: dict[str, Any] = field(default_factory=dict)


class ChatAgent:
    """ReAct chat agent backed by OpenAI streaming and three financial tools."""

    def __init__(
        self,
        openai_client: OpenAI,
        model_name: str,
        market_data_service: MarketDataService,
        *,
        stream_timeout_seconds: float = CHAT_STREAM_OPENAI_TIMEOUT_DEFAULT,
    ) -> None:
        self._openai_client = openai_client
        self._model_name = model_name
        self._market_data_service = market_data_service
        self._stream_timeout_seconds = stream_timeout_seconds
        self._tool_definitions = TOOL_DEFINITIONS

    def stream(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[ChatStreamEvent, None, None]:
        """Run the ReAct agent loop, yielding streaming events.

        The outer loop alternates between *agent_node* (call OpenAI with
        streaming) and *tool_node* (execute requested tools) until the model
        responds without tool calls.
        """
        state: ChatAgentState = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages,
            ],
        }

        for _ in range(MAX_TOOL_ROUNDS):
            tool_calls_requested: list[dict[str, Any]] = []
            assistant_content_parts: list[str] = []

            try:
                yield from self._agent_node(
                    state,
                    tool_calls_out=tool_calls_requested,
                    content_parts_out=assistant_content_parts,
                )
            except Exception as exc:  # noqa: BLE001 — safety net for OpenAI/network errors
                LOGGER.exception("agent_node failed")
                yield ChatStreamEvent(event="error", data={"message": str(exc)})
                return

            if not tool_calls_requested:
                yield ChatStreamEvent(event="done")
                return

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": tool_calls_requested,
            }
            if assistant_content_parts:
                assistant_msg["content"] = "".join(assistant_content_parts)
            state["messages"].append(assistant_msg)

            yield from self._tool_node(state, tool_calls_requested)

        yield ChatStreamEvent(event="done")

    def _agent_node(
        self,
        state: ChatAgentState,
        *,
        tool_calls_out: list[dict[str, Any]],
        content_parts_out: list[str],
    ) -> Generator[ChatStreamEvent, None, None]:
        """Stream an OpenAI chat completion and collect deltas / tool calls."""
        with self._openai_client.chat.completions.create(
            model=self._model_name,
            messages=state["messages"],
            tools=self._tool_definitions,
            stream=True,
            timeout=self._stream_timeout_seconds,
        ) as response_stream:
            pending_tool_calls: dict[int, dict[str, Any]] = {}

            for chunk in response_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    content_parts_out.append(delta.content)
                    yield ChatStreamEvent(
                        event="delta",
                        data={"content": delta.content},
                    )

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in pending_tool_calls:
                            pending_tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = pending_tool_calls[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["function"]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["function"]["arguments"] += tc_delta.function.arguments

            for idx in sorted(pending_tool_calls):
                tool_calls_out.append(pending_tool_calls[idx])

    def _tool_node(
        self,
        state: ChatAgentState,
        tool_calls: list[dict[str, Any]],
    ) -> Generator[ChatStreamEvent, None, None]:
        """Execute each requested tool and append results to state messages."""
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            tool_call_id = tc["id"]

            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                LOGGER.warning("Malformed tool arguments for %s: %r", fn_name, raw_args)
                args = {}

            try:
                result = self._execute_tool(fn_name, args)
            except Exception as exc:  # noqa: BLE001 — tools may raise arbitrary errors
                LOGGER.exception("Tool %s failed", fn_name)
                result = {"error": str(exc)}
                yield ChatStreamEvent(
                    event="error",
                    data={"message": f"Tool {fn_name} failed: {exc}"},
                )

            yield ChatStreamEvent(
                event="tool_call",
                data={"name": fn_name, "result": result},
            )

            state["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_market_overview":
            overview = self._market_data_service.get_market_overview()
            return overview.model_dump(mode="json")

        if name == "search_stocks":
            query = args.get("query", "")
            stocks = self._market_data_service.get_stocks(query=query)
            return stocks.model_dump(mode="json")

        if name == "generate_recommendations":
            risk_profile = args.get("risk_profile", "balanced")
            return {
                "status": "triggered",
                "risk_profile": risk_profile,
                "message": (
                    "Recommendation generation triggered. "
                    "The full recommendation workflow will be wired through "
                    "the router in a later integration step."
                ),
            }

        return {"error": f"Unknown tool: {name}"}


def _chat_stream_openai_timeout_seconds(env: Mapping[str, str]) -> float:
    """Uses FINANCEHUB_LLM_TIMEOUT_SECONDS when set; else 120s for long streams."""
    if _clean_env_value(env.get("FINANCEHUB_LLM_TIMEOUT_SECONDS")) is None:
        return CHAT_STREAM_OPENAI_TIMEOUT_DEFAULT
    return _parse_request_timeout_seconds(env)


def build_chat_agent(
    market_data_service: MarketDataService,
    environ: Mapping[str, str] | None = None,
) -> ChatAgent:
    """Factory: build a ChatAgent from environment configuration."""
    env = _build_env_values(environ=environ)

    api_key = _clean_env_value(env.get("FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")) or ""
    base_url = _normalize_base_url(
        _clean_env_value(env.get("FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL"))
        or OPENAI_DEFAULT_BASE_URL
    )
    model_name = (
        _clean_env_value(env.get("FINANCEHUB_LLM_AGENT_CHAT_ASSISTANT_MODEL"))
        or _clean_env_value(env.get("FINANCEHUB_LLM_PROVIDER_OPENAI_MODEL_DEFAULT"))
        or OPENAI_DEFAULT_MODEL
    )

    openai_client = OpenAI(api_key=api_key, base_url=base_url)
    stream_timeout_seconds = _chat_stream_openai_timeout_seconds(env)
    return ChatAgent(
        openai_client,
        model_name,
        market_data_service,
        stream_timeout_seconds=stream_timeout_seconds,
    )
