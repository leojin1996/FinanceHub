from __future__ import annotations

from financehub_market_api.models import RecommendationProduct, RecommendationSummary
from financehub_market_api.recommendation.rules.product_catalog import (
    AGGRESSIVE_OPTION_SUBTITLES,
    AGGRESSIVE_OPTION_TITLES,
    DEFAULT_SUMMARY_SUBTITLE_EN,
    DEFAULT_SUMMARY_SUBTITLE_ZH,
    FUNDS as DOMAIN_FUNDS,
    RISK_NOTICE_EN,
    RISK_NOTICE_ZH,
    STOCKS as DOMAIN_STOCKS,
    WEALTH_MANAGEMENT as DOMAIN_WEALTH_MANAGEMENT,
)

FUNDS: list[RecommendationProduct] = [item.to_api_model() for item in DOMAIN_FUNDS]

WEALTH_MANAGEMENT: list[RecommendationProduct] = [item.to_api_model() for item in DOMAIN_WEALTH_MANAGEMENT]

STOCKS: list[RecommendationProduct] = [item.to_api_model() for item in DOMAIN_STOCKS]

DEFAULT_SUMMARY = RecommendationSummary(
    titleZh="",
    titleEn="",
    subtitleZh=DEFAULT_SUMMARY_SUBTITLE_ZH,
    subtitleEn=DEFAULT_SUMMARY_SUBTITLE_EN,
)
