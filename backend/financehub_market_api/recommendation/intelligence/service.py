from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from financehub_market_api.models import (
    IndicesResponse,
    LocalizedText,
    MarketEvidenceItem,
    MarketOverviewResponse,
)
from financehub_market_api.market_news import MarketNewsDigest

_DEFAULT_MARKET_OVERVIEW_SUMMARY = "A股宽基震荡，红利与固收风格相对占优。"
_DEFAULT_MACRO_SUMMARY = "宏观修复温和，政策基调保持稳增长。"
_DEFAULT_RATE_SUMMARY = "一年期利率中枢下移，稳健资产仍具吸引力。"
_DEFAULT_NEWS_SUMMARIES = [
    "公募资金净申购延续，低波动产品关注度提升",
    "龙头权益估值分化，建议保持行业分散",
]
_DEFAULT_MARKET_NEWS_QUERY = "A股 市场 今日 要闻"
_DEFAULT_MARKET_NEWS_TIME_RANGE = "week"
_DEFAULT_MARKET_NEWS_MAX_RESULTS = 10


class MarketDataSnapshotSource(Protocol):
    def get_market_overview(self) -> MarketOverviewResponse: ...

    def get_indices(self) -> IndicesResponse: ...


class MarketNewsDigestSource(Protocol):
    def fetch_digest(
        self,
        *,
        query: str,
        time_range: str,
        max_results: int,
    ) -> MarketNewsDigest: ...


class MarketSnapshot(BaseModel):
    sentiment: Literal["negative", "neutral", "positive"]
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
        market_news_service: MarketNewsDigestSource | None = None,
    ) -> None:
        self._market_data_service = market_data_service
        self._market_news_service = market_news_service

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

        sentiment = _sentiment_from_text(summary_zh)
        stance = _stance_from_text(summary_zh, sentiment=sentiment)
        preferred_categories = (
            ["wealth_management", "fund"]
            if stance == "defensive"
            else ["fund", "stock"]
            if stance == "offensive"
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
        positive_count = len(positive_indices)
        negative_count = len(negative_indices)
        sentiment: Literal["negative", "neutral", "positive"] = _sentiment_from_change(
            average_change_percent
        )
        stance: Literal["defensive", "balanced", "offensive"] = _stance_from_change(
            average_change_percent,
            positive_count=positive_count,
            negative_count=negative_count,
        )
        preferred_categories = (
            ["wealth_management", "fund"]
            if stance == "defensive"
            else ["fund", "stock"]
            if stance == "offensive"
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

        news_digest = self._fetch_market_news_digest()
        if news_digest is not None and news_digest.items:
            summary_zh = f"{summary_zh}；新闻要点：{news_digest.summaryZh}"
            summary_en = (
                f"{summary_en} News digest was included as an additional market signal."
            )
            evidence.append(
                MarketEvidenceItem(
                    source="news_digest",
                    asOf=news_digest.asOf,
                    summary=LocalizedText(
                        zh=news_digest.summaryZh,
                        en=(
                            "Market news digest signal. News sentiment is for "
                            "reference only."
                        ),
                    ),
                )
            )
            sentiment, stance = _apply_news_signal(
                sentiment=sentiment,
                stance=stance,
                news_digest=news_digest,
            )
            preferred_categories = (
                ["wealth_management", "fund"]
                if stance == "defensive"
                else ["fund", "stock"]
            )
            avoided_categories = ["stock"] if stance == "defensive" else []

        return MarketSnapshot(
            sentiment=sentiment,
            stance=stance,
            preferred_categories=preferred_categories,
            avoided_categories=avoided_categories,
            summary_zh=summary_zh,
            summary_en=summary_en,
            evidence=evidence,
        )

    def _fetch_market_news_digest(self) -> MarketNewsDigest | None:
        if self._market_news_service is None:
            return None
        try:
            return self._market_news_service.fetch_digest(
                query=_DEFAULT_MARKET_NEWS_QUERY,
                time_range=_DEFAULT_MARKET_NEWS_TIME_RANGE,
                max_results=_DEFAULT_MARKET_NEWS_MAX_RESULTS,
            )
        except Exception:  # noqa: BLE001
            return None


def _sentiment_from_text(
    summary_zh: str,
) -> Literal["negative", "neutral", "positive"]:
    if "震荡" in summary_zh:
        return "neutral"
    negative_keywords = ("承压", "回撤", "下跌", "走弱", "下行")
    positive_keywords = ("上涨", "走强", "回暖", "反弹", "修复")
    if any(keyword in summary_zh for keyword in negative_keywords):
        return "negative"
    if any(keyword in summary_zh for keyword in positive_keywords):
        return "positive"
    return "neutral"


def _stance_from_text(
    summary_zh: str,
    *,
    sentiment: Literal["negative", "neutral", "positive"],
) -> Literal["defensive", "balanced", "offensive"]:
    defensive_keywords = ("债", "降息", "避险", "低波动")
    offensive_keywords = ("科技", "成长", "权益走强", "风险偏好回升", "进攻")
    if sentiment == "negative" or any(keyword in summary_zh for keyword in defensive_keywords):
        return "defensive"
    if sentiment == "positive" and any(keyword in summary_zh for keyword in offensive_keywords):
        return "offensive"
    return "balanced"


def _sentiment_from_change(
    average_change_percent: float,
) -> Literal["negative", "neutral", "positive"]:
    if average_change_percent > 0.2:
        return "positive"
    if average_change_percent < -0.2:
        return "negative"
    return "neutral"


def _stance_from_change(
    average_change_percent: float,
    *,
    positive_count: int,
    negative_count: int,
) -> Literal["defensive", "balanced", "offensive"]:
    if average_change_percent > 0.2 and positive_count > negative_count:
        return "offensive"
    if average_change_percent < -0.2 and negative_count > positive_count:
        return "defensive"
    return "balanced"


def _apply_news_signal(
    *,
    sentiment: Literal["negative", "neutral", "positive"],
    stance: Literal["defensive", "balanced", "offensive"],
    news_digest: MarketNewsDigest,
) -> tuple[
    Literal["negative", "neutral", "positive"],
    Literal["defensive", "balanced", "offensive"],
]:
    if (
        news_digest.negativeCount > news_digest.positiveCount
        and news_digest.negativeCount > 0
    ):
        return "negative", "defensive"
    if (
        news_digest.positiveCount > news_digest.negativeCount
        and news_digest.positiveCount > 0
        and sentiment != "negative"
        and stance != "defensive"
    ):
        return "positive", "offensive"
    return sentiment, stance
