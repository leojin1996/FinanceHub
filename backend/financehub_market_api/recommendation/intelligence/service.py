from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from financehub_market_api.models import (
    IndicesResponse,
    LocalizedText,
    MarketEvidenceItem,
    MarketOverviewResponse,
)

_DEFAULT_MARKET_OVERVIEW_SUMMARY = "A股宽基震荡，红利与固收风格相对占优。"
_DEFAULT_MACRO_SUMMARY = "宏观修复温和，政策基调保持稳增长。"
_DEFAULT_RATE_SUMMARY = "一年期利率中枢下移，稳健资产仍具吸引力。"
_DEFAULT_NEWS_SUMMARIES = [
    "公募资金净申购延续，低波动产品关注度提升",
    "龙头权益估值分化，建议保持行业分散",
]


class MarketDataSnapshotSource(Protocol):
    def get_market_overview(self) -> MarketOverviewResponse: ...

    def get_indices(self) -> IndicesResponse: ...


class MarketSnapshot(BaseModel):
    sentiment: Literal["neutral", "positive"]
    stance: Literal["defensive", "balanced", "offensive"]
    preferred_categories: list[str] = Field(default_factory=list)
    avoided_categories: list[str] = Field(default_factory=list)
    summary_zh: str
    summary_en: str
    evidence: list[MarketEvidenceItem] = Field(default_factory=list)


class MarketIntelligenceService:
    def __init__(
        self,
        market_data_service: MarketDataSnapshotSource | None = None,
    ) -> None:
        self._market_data_service = market_data_service

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
        preferred_categories = (
            ["wealth_management", "fund"]
            if stance == "defensive"
            else ["fund", "stock"]
        )
        avoided_categories = ["stock"] if stance == "defensive" else []

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
            preferred_categories=preferred_categories,
            avoided_categories=avoided_categories,
            summary_zh=summary_zh,
            summary_en=summary_en,
            evidence=evidence,
        )

    def build_recommendation_snapshot(self) -> MarketSnapshot:
        if self._market_data_service is None:
            return self.build_snapshot(
                market_overview_summary=_DEFAULT_MARKET_OVERVIEW_SUMMARY,
                macro_summary=_DEFAULT_MACRO_SUMMARY,
                rate_summary=_DEFAULT_RATE_SUMMARY,
                news_summaries=list(_DEFAULT_NEWS_SUMMARIES),
            )

        overview = self._market_data_service.get_market_overview()
        indices = self._market_data_service.get_indices()

        overview_metrics_zh = "、".join(
            f"{metric.label}{metric.value}（{metric.delta}）"
            for metric in overview.metrics[:2]
        ) or "主要宽基暂无更新"
        overview_metrics_en = ", ".join(
            f"{metric.label} {metric.value} ({metric.delta})"
            for metric in overview.metrics[:2]
        ) or "major mainland benchmarks unavailable"

        positive_indices = [card.name for card in indices.cards if card.changePercent > 0]
        negative_indices = [card.name for card in indices.cards if card.changePercent < 0]
        positive_indices_zh = "、".join(positive_indices) or "暂无明显偏强指数"
        negative_indices_zh = "、".join(negative_indices) or "暂无明显承压指数"
        positive_indices_en = ", ".join(positive_indices) or "no clear outperforming indices"
        negative_indices_en = ", ".join(negative_indices) or "no clear lagging indices"

        top_gainer = overview.topGainers[0].name if overview.topGainers else "暂无"
        top_loser = overview.topLosers[0].name if overview.topLosers else "暂无"

        summary_zh = (
            f"市场概览（截至 {overview.asOfDate}）：{overview_metrics_zh}；"
            f"指数表现：偏强指数 {positive_indices_zh}，承压指数 {negative_indices_zh}；"
            f"个股动向：领涨关注 {top_gainer}，回撤关注 {top_loser}"
        )
        summary_en = (
            f"Market overview as of {overview.asOfDate}: {overview_metrics_en}. "
            f"Index breadth favored {positive_indices_en} while {negative_indices_en} lagged. "
            f"Leadership watch: {top_gainer} led and {top_loser} lagged."
        )

        average_change_percent = (
            sum(card.changePercent for card in indices.cards) / len(indices.cards)
            if indices.cards
            else 0.0
        )
        sentiment: Literal["neutral", "positive"] = (
            "positive" if average_change_percent > 0 else "neutral"
        )
        stance: Literal["defensive", "balanced", "offensive"] = (
            "balanced" if average_change_percent >= 0 else "defensive"
        )
        preferred_categories = (
            ["wealth_management", "fund"]
            if stance == "defensive"
            else ["fund", "stock"]
        )
        avoided_categories = ["stock"] if stance == "defensive" else []

        evidence = [
            MarketEvidenceItem(
                source="market_overview",
                asOf=overview.asOfDate,
                summary=LocalizedText(zh=overview_metrics_zh, en=overview_metrics_en),
            ),
            MarketEvidenceItem(
                source="indices",
                asOf=indices.asOfDate,
                summary=LocalizedText(
                    zh=f"偏强指数：{positive_indices_zh}；承压指数：{negative_indices_zh}",
                    en=f"Outperforming indices: {positive_indices_en}; laggards: {negative_indices_en}",
                ),
            ),
            MarketEvidenceItem(
                source="market_leadership",
                asOf=overview.asOfDate,
                summary=LocalizedText(
                    zh=f"领涨关注：{top_gainer}；回撤关注：{top_loser}",
                    en=f"Leadership watch: {top_gainer} led while {top_loser} lagged",
                ),
            ),
        ]

        return MarketSnapshot(
            sentiment=sentiment,
            stance=stance,
            preferred_categories=preferred_categories,
            avoided_categories=avoided_categories,
            summary_zh=summary_zh,
            summary_en=summary_en,
            evidence=evidence,
        )
