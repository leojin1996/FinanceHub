from __future__ import annotations

from pydantic import BaseModel, Field

from financehub_market_api.models import LocalizedText, MarketEvidenceItem


class MarketSnapshot(BaseModel):
    sentiment: str
    stance: str
    summary_zh: str
    summary_en: str
    evidence: list[MarketEvidenceItem] = Field(default_factory=list)


class MarketIntelligenceService:
    def build_snapshot(
        self,
        *,
        market_overview_summary: str,
        macro_summary: str,
        rate_summary: str,
        news_summaries: list[str],
    ) -> MarketSnapshot:
        news_summary = "；".join(news_summaries)
        summary_zh = (
            f"市场概览：{market_overview_summary}；"
            f"宏观环境：{macro_summary}；"
            f"利率观察：{rate_summary}；"
            f"新闻要点：{news_summary}"
        )
        summary_en = (
            "Deterministic market snapshot built from overview, macro, rates, and news inputs."
        )

        stance = "defensive" if ("债" in summary_zh or "降息" in summary_zh) else "balanced"
        sentiment = "neutral" if "震荡" in summary_zh else "positive"

        evidence = [
            MarketEvidenceItem(
                source="market_overview",
                asOf="N/A",
                summary=LocalizedText(zh=market_overview_summary, en="Market overview signal"),
            ),
            MarketEvidenceItem(
                source="macro_and_rates",
                asOf="N/A",
                summary=LocalizedText(
                    zh=f"{macro_summary}；{rate_summary}",
                    en="Macro and rate signal",
                ),
            ),
        ]

        if news_summaries:
            evidence.append(
                MarketEvidenceItem(
                    source="news_digest",
                    asOf="N/A",
                    summary=LocalizedText(zh=news_summary, en="News digest signal"),
                )
            )

        return MarketSnapshot(
            sentiment=sentiment,
            stance=stance,
            summary_zh=summary_zh,
            summary_en=summary_en,
            evidence=evidence,
        )
