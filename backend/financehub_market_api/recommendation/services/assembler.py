from __future__ import annotations

from financehub_market_api.models import (
    LocalizedText,
    LocalizedTextList,
    RecommendationOption,
    RecommendationResponse,
    RecommendationSection,
    RecommendationSections,
    RecommendationSummary,
    RecommendationWarning,
)
from financehub_market_api.recommendation.rules import (
    AGGRESSIVE_OPTION_SUBTITLES,
    AGGRESSIVE_OPTION_TITLES,
    DEFAULT_SUMMARY_SUBTITLE_EN,
    DEFAULT_SUMMARY_SUBTITLE_ZH,
    RISK_NOTICE_EN,
    RISK_NOTICE_ZH,
)
from financehub_market_api.recommendation.schemas import FinalRecommendation


def assemble_recommendation_response(
    recommendation: FinalRecommendation,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationResponse:
    profile = recommendation.user_profile

    return RecommendationResponse(
        summary=RecommendationSummary(
            titleZh=f"适合您的{profile.label_zh}配置建议",
            titleEn=f"A {profile.label_en} plan that fits you",
            subtitleZh=DEFAULT_SUMMARY_SUBTITLE_ZH,
            subtitleEn=DEFAULT_SUMMARY_SUBTITLE_EN,
        ),
        profileSummary=LocalizedText(
            zh=f"您的测评结果更接近{profile.label_zh}，适合先控制回撤，再追求稳步增值。",
            en=f"Your assessment aligns with a {profile.label_en} profile, which calls for drawdown control before chasing extra upside.",
        ),
        marketSummary=LocalizedText(
            zh=recommendation.market_context.summary_zh,
            en=recommendation.market_context.summary_en,
        ),
        allocationDisplay=recommendation.allocation_plan.to_display(),
        sections=RecommendationSections(
            funds=RecommendationSection(
                titleZh="基金推荐",
                titleEn="Fund ideas",
                items=[item.to_api_model() for item in recommendation.fund_items],
            ),
            wealthManagement=RecommendationSection(
                titleZh="银行理财推荐",
                titleEn="Wealth management ideas",
                items=[item.to_api_model() for item in recommendation.wealth_management_items],
            ),
            stocks=RecommendationSection(
                titleZh="股票增强",
                titleEn="Equity boost",
                items=[item.to_api_model() for item in recommendation.stock_items],
            ),
        ),
        aggressiveOption=(
            RecommendationOption(
                titleZh=AGGRESSIVE_OPTION_TITLES[0],
                titleEn=AGGRESSIVE_OPTION_TITLES[1],
                subtitleZh=AGGRESSIVE_OPTION_SUBTITLES[0],
                subtitleEn=AGGRESSIVE_OPTION_SUBTITLES[1],
                allocation=recommendation.aggressive_allocation_plan.to_display(),
            )
            if include_aggressive_option
            else None
        ),
        riskNotice=LocalizedTextList(
            zh=list(RISK_NOTICE_ZH),
            en=list(RISK_NOTICE_EN),
        ),
        whyThisPlan=LocalizedTextList(
            zh=list(recommendation.why_this_plan_zh),
            en=list(recommendation.why_this_plan_en),
        ),
        reviewStatus=recommendation.risk_review_result.review_status,
        executionMode=recommendation.execution_trace.execution_mode,
        warnings=[
            RecommendationWarning(
                stage=warning.stage,
                code=warning.code,
                message=warning.message,
            )
            for warning in recommendation.execution_trace.warnings
        ],
    )
