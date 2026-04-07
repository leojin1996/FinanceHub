from __future__ import annotations

from pydantic import BaseModel, Field


class UserProfileAgentOutput(BaseModel):
    profile_focus_zh: str = Field(min_length=1)
    profile_focus_en: str = Field(min_length=1)


class MarketIntelligenceAgentOutput(BaseModel):
    summary_zh: str = Field(min_length=1)
    summary_en: str = Field(min_length=1)


class ProductRankingAgentOutput(BaseModel):
    ranked_ids: list[str]


class ExplanationAgentOutput(BaseModel):
    why_this_plan_zh: list[str] = Field(min_length=1)
    why_this_plan_en: list[str] = Field(min_length=1)
