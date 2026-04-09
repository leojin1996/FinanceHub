from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class AgentPromptSection:
    title: str
    body: str


@dataclass(frozen=True)
class AgentPromptContext:
    task: str
    sections: tuple[AgentPromptSection, ...] = ()
    instructions: tuple[str, ...] = ()

    def render_user_prompt(self, *, tool_descriptions: tuple[str, ...] = ()) -> str:
        parts = [f"Task\n{self.task}"]

        for section in self.sections:
            parts.append(f"{section.title}\n{section.body}")

        if self.instructions:
            parts.append(
                "Rules\n" + "\n".join(f"- {instruction}" for instruction in self.instructions)
            )

        if tool_descriptions:
            parts.append(
                "Available tools\n" + "\n".join(f"- {tool_description}" for tool_description in tool_descriptions)
            )

        return "\n\n".join(parts)


@dataclass(frozen=True)
class AgentToolCallRecord:
    tool_name: str
    arguments: Mapping[str, object]
    result: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze_mapping(self.arguments))
        object.__setattr__(self, "result", _freeze_mapping(self.result))


@dataclass(frozen=True)
class SelectedPlanContext:
    fund_ids: tuple[str, ...] = ()
    wealth_management_ids: tuple[str, ...] = ()
    stock_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "fund_ids": list(self.fund_ids),
            "wealth_management_ids": list(self.wealth_management_ids),
            "stock_ids": list(self.stock_ids),
        }


def coerce_selected_plan_context(
    value: SelectedPlanContext | Mapping[str, object] | None,
) -> SelectedPlanContext | None:
    if value is None or isinstance(value, SelectedPlanContext):
        return value

    return SelectedPlanContext(
        fund_ids=_coerce_string_list(value.get("fund_ids")),
        wealth_management_ids=_coerce_string_list(value.get("wealth_management_ids")),
        stock_ids=_coerce_string_list(value.get("stock_ids")),
    )


def _coerce_string_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError("expected a list of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("expected a list of strings")
        items.append(item)
    return tuple(items)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {str(key): _freeze_value(nested_value) for key, nested_value in value.items()}
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


__all__ = [
    "AgentPromptContext",
    "AgentPromptSection",
    "AgentToolCallRecord",
    "SelectedPlanContext",
    "coerce_selected_plan_context",
]
