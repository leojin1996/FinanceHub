from __future__ import annotations

from financehub_market_api.models import (
    AllocationDisplay,
    ComplianceReviewPayload,
    LocalizedText,
    LocalizedTextList,
    ProfileInsightsPayload,
    RecommendationEvidenceReference,
    RecommendationOption,
    RecommendationProduct,
    RecommendationMarketIntelligencePayload,
    RecommendationResponse,
    RecommendationSection,
    RecommendationSections,
    RecommendationSummary,
    RecommendationWarning,
)
from financehub_market_api.recommendation.graph.state import RecommendationGraphState
from financehub_market_api.recommendation.product_knowledge import ProductEvidenceBundle
from financehub_market_api.recommendation.rules import (
    AGGRESSIVE_ALLOCATIONS,
    AGGRESSIVE_OPTION_SUBTITLES,
    AGGRESSIVE_OPTION_TITLES,
    BASE_ALLOCATIONS,
    DEFAULT_SUMMARY_SUBTITLE_EN,
    DEFAULT_SUMMARY_SUBTITLE_ZH,
    PROFILE_LABELS_EN,
    PROFILE_LABELS_ZH,
    RISK_NOTICE_EN,
    RISK_NOTICE_ZH,
)
from financehub_market_api.recommendation.rules.product_catalog import FUNDS, STOCKS, WEALTH_MANAGEMENT
from financehub_market_api.recommendation.schemas import FinalRecommendation
from financehub_market_api.recommendation.services.evidence_projection import (
    project_public_evidence_references,
)

_PRODUCT_LOOKUP = {
    product.id: product
    for product in [*FUNDS, *WEALTH_MANAGEMENT, *STOCKS]
}


def _summary_subtitle_for_allocation(allocation: AllocationDisplay) -> tuple[str, str]:
    if allocation.stock > 0:
        return DEFAULT_SUMMARY_SUBTITLE_ZH, DEFAULT_SUMMARY_SUBTITLE_EN
    if allocation.fund > 0 and allocation.wealthManagement > 0:
        return (
            "以稳健资产打底，优先配置基金与银行理财，等待更清晰的进攻信号。",
            "Build the base with steadier assets, prioritizing funds and wealth management until clearer risk-taking signals emerge.",
        )
    if allocation.fund > 0:
        return (
            "以基金配置为核心，先控制组合波动并保留调整空间。",
            "Use funds as the core while controlling portfolio volatility and preserving room to adjust.",
        )
    if allocation.wealthManagement > 0:
        return (
            "以银行理财配置为核心，优先兼顾稳定性与流动性。",
            "Use wealth management as the core while prioritizing stability and liquidity.",
        )
    return (
        "当前条件不足以形成可执行配置，请等待人工复核后再决策。",
        "Current conditions are insufficient for an executable allocation; wait for manual review before acting.",
    )


def _risk_notice_for_allocation(allocation: AllocationDisplay) -> tuple[list[str], list[str]]:
    zh: list[str] = []
    en: list[str] = []
    if allocation.fund > 0 or allocation.wealthManagement > 0:
        zh.append(RISK_NOTICE_ZH[0])
        en.append(RISK_NOTICE_EN[0])
    if allocation.stock > 0:
        zh.append(RISK_NOTICE_ZH[1])
        en.append(RISK_NOTICE_EN[1])
    if not zh:
        zh.append("当前推荐未形成可执行配置，请等待人工复核后再决策。")
        en.append("This result did not form an executable allocation. Wait for manual review before acting.")
    return zh, en


def _section_for_allocation(
    section: RecommendationSection,
    allocation_value: int,
) -> RecommendationSection:
    if allocation_value > 0:
        return section
    return section.model_copy(update={"items": []})


def _sections_for_allocation_display(
    sections: RecommendationSections,
    allocation: AllocationDisplay,
) -> RecommendationSections:
    return RecommendationSections(
        funds=_section_for_allocation(sections.funds, allocation.fund),
        wealthManagement=_section_for_allocation(
            sections.wealthManagement,
            allocation.wealthManagement,
        ),
        stocks=_section_for_allocation(sections.stocks, allocation.stock),
    )


def assemble_domain_recommendation_response(
    recommendation: FinalRecommendation,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationResponse:
    profile = recommendation.user_profile
    allocation_display = recommendation.allocation_plan.to_display()
    subtitle_zh, subtitle_en = _summary_subtitle_for_allocation(allocation_display)
    risk_notice_zh, risk_notice_en = _risk_notice_for_allocation(allocation_display)
    raw_sections = RecommendationSections(
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
    )

    return RecommendationResponse(
        summary=RecommendationSummary(
            titleZh=f"适合您的{profile.label_zh}配置建议",
            titleEn=f"A {profile.label_en} plan that fits you",
            subtitleZh=subtitle_zh,
            subtitleEn=subtitle_en,
        ),
        profileSummary=LocalizedText(
            zh=f"您的测评结果更接近{profile.label_zh}，适合先控制回撤，再追求稳步增值。",
            en=f"Your assessment aligns with a {profile.label_en} profile, which calls for drawdown control before chasing extra upside.",
        ),
        marketSummary=LocalizedText(
            zh=recommendation.market_context.summary_zh,
            en=recommendation.market_context.summary_en,
        ),
        allocationDisplay=allocation_display,
        sections=_sections_for_allocation_display(raw_sections, allocation_display),
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
            zh=risk_notice_zh,
            en=risk_notice_en,
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


def _fallback_graph_product(product_id: str, category: str, rationale: str) -> RecommendationProduct:
    return RecommendationProduct(
        id=product_id,
        category=category,
        code=None,
        liquidity=None,
        asOfDate=None,
        detailRoute=f"/recommendations/products/{product_id}",
        nameZh=f"推荐产品 {product_id}",
        nameEn=f"Recommended product {product_id}",
        rationaleZh=rationale,
        rationaleEn="Selected by deterministic retrieval ranking.",
        riskLevel="R3",
        tagsZh=[],
        tagsEn=[],
    )


def _public_evidence_preview(
    evidence_bundles: list[ProductEvidenceBundle],
    *,
    product_id: str,
    limit: int = 2,
) -> list[RecommendationEvidenceReference]:
    if limit <= 0:
        return []
    bundle = next(
        (candidate_bundle for candidate_bundle in evidence_bundles if candidate_bundle.product_id == product_id),
        None,
    )
    if bundle is None:
        return []
    return project_public_evidence_references(bundle.evidences, limit=limit)


def _assemble_graph_sections(graph_state: RecommendationGraphState) -> RecommendationSections:
    retrieval_context = graph_state["retrieval_context"]
    evidence_bundles = [] if retrieval_context is None else list(retrieval_context.product_evidences)
    funds: list[RecommendationProduct] = []
    wealth_management: list[RecommendationProduct] = []
    stocks: list[RecommendationProduct] = []

    if retrieval_context is not None:
        for item in retrieval_context.candidates:
            if item.runtime_candidate is not None:
                snapshot = item.runtime_candidate
                api_product = RecommendationProduct(
                    id=snapshot.id,
                    category=snapshot.category,
                    code=snapshot.code,
                    liquidity=snapshot.liquidity,
                    asOfDate=snapshot.as_of_date,
                    detailRoute=(
                        snapshot.detail_route
                        if snapshot.detail_route is not None
                        else f"/recommendations/products/{snapshot.id}"
                    ),
                    nameZh=snapshot.name_zh,
                    nameEn=snapshot.name_en,
                    rationaleZh=snapshot.rationale_zh,
                    rationaleEn=snapshot.rationale_en,
                    riskLevel=snapshot.risk_level,
                    tagsZh=list(snapshot.tags_zh),
                    tagsEn=list(snapshot.tags_en),
                )
            else:
                product = _PRODUCT_LOOKUP.get(item.product_id)
                api_product = (
                    product.to_api_model()
                    if product is not None
                    else _fallback_graph_product(item.product_id, item.category, item.rationale)
                )
            api_product = api_product.model_copy(
                update={
                    "evidencePreview": _public_evidence_preview(
                        evidence_bundles,
                        product_id=api_product.id,
                        limit=2,
                    )
                }
            )
            if item.category == "fund":
                funds.append(api_product)
            elif item.category == "wealth_management":
                wealth_management.append(api_product)
            elif item.category == "stock":
                stocks.append(api_product)

    return RecommendationSections(
        funds=RecommendationSection(
            titleZh="基金推荐",
            titleEn="Fund ideas",
            items=funds,
        ),
        wealthManagement=RecommendationSection(
            titleZh="银行理财推荐",
            titleEn="Wealth management ideas",
            items=wealth_management,
        ),
        stocks=RecommendationSection(
            titleZh="股票增强",
            titleEn="Equity boost",
            items=stocks,
        ),
    )


def _graph_allocation_display(
    *,
    allocation: AllocationDisplay,
    sections: RecommendationSections,
) -> AllocationDisplay:
    display = {
        "fund": allocation.fund,
        "wealthManagement": allocation.wealthManagement,
        "stock": allocation.stock,
    }
    available_categories = {
        "fund": bool(sections.funds.items),
        "wealthManagement": bool(sections.wealthManagement.items),
        "stock": bool(sections.stocks.items),
    }
    rebalance_order = {
        "fund": ("wealthManagement", "stock"),
        "wealthManagement": ("fund", "stock"),
        "stock": ("wealthManagement", "fund"),
    }

    for category, is_available in available_categories.items():
        if is_available:
            continue
        amount = display[category]
        display[category] = 0
        target = next(
            (
                fallback_category
                for fallback_category in rebalance_order[category]
                if available_categories[fallback_category]
            ),
            None,
        )
        if target is not None:
            display[target] += amount

    return AllocationDisplay(
        fund=display["fund"],
        wealthManagement=display["wealthManagement"],
        stock=display["stock"],
    )


def _recommendation_allocation_display(
    *,
    risk_profile: str,
    recommendation_status: str,
    sections: RecommendationSections,
) -> AllocationDisplay:
    del recommendation_status
    return _graph_allocation_display(
        allocation=BASE_ALLOCATIONS[risk_profile].to_display(),
        sections=sections,
    )


def assemble_graph_recommendation_response(
    graph_state: RecommendationGraphState,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationResponse:
    payload = graph_state["request_context"].payload
    risk_profile = payload.riskAssessmentResult.finalProfile
    profile_label_zh = PROFILE_LABELS_ZH[risk_profile]
    profile_label_en = PROFILE_LABELS_EN[risk_profile]

    user_intelligence = graph_state["user_intelligence"]
    market_intelligence = graph_state["market_intelligence"]
    compliance_review = graph_state["compliance_review"]
    final_response = graph_state["final_response"]
    manager_brief = graph_state["manager_brief"]

    recommendation_status = "ready" if final_response is None else final_response.recommendation_status

    compliance_payload = None
    if compliance_review is not None and (
        compliance_review.verdict != "approve" or recommendation_status != "ready"
    ):
        compliance_payload = ComplianceReviewPayload(
            verdict=compliance_review.verdict,
            reasonSummary=LocalizedText(
                zh=compliance_review.reason_zh,
                en=compliance_review.reason_en,
            ),
            requiredDisclosures=LocalizedTextList(
                zh=list(compliance_review.disclosures_zh),
                en=list(compliance_review.disclosures_en),
            ),
            suitabilityNotes=LocalizedTextList(
                zh=list(compliance_review.suitability_notes_zh),
                en=list(compliance_review.suitability_notes_en),
            ),
            appliedRuleIds=list(compliance_review.applied_rule_ids),
            blockingReasonCodes=list(compliance_review.blocking_reason_codes),
        )

    review_status = "pass" if recommendation_status == "ready" else "partial_pass"
    if manager_brief is not None:
        why_this_plan_zh = list(manager_brief.why_this_plan_zh)
        why_this_plan_en = list(manager_brief.why_this_plan_en)
    elif recommendation_status == "blocked":
        why_this_plan_zh = [
            "本次 AI 多智能体评审未完整完成，系统已自动阻断推荐。",
            "建议由人工顾问结合最新规则和用户情况进一步复核。",
        ]
        why_this_plan_en = [
            "The AI multi-agent review did not complete, so the recommendation was automatically blocked.",
            "Route this case to a human advisor for a rules and suitability review.",
        ]
    else:
        why_this_plan_zh = [
            f"您的风险画像为{profile_label_zh}，主方案优先兼顾稳健和流动性。",
            "该建议由多代理流程串行生成，并经过合规节点审阅。",
            "资产分层配置有助于平衡稳健性与收益弹性。",
        ]
        why_this_plan_en = [
            f"Your profile is {profile_label_en}, so the base plan prioritizes stability and liquidity.",
            "The recommendation is generated by a multi-agent graph and reviewed by compliance.",
            "A layered allocation balances resilience with upside potential.",
        ]
    raw_sections = _assemble_graph_sections(graph_state)
    allocation_display = _recommendation_allocation_display(
        risk_profile=risk_profile,
        recommendation_status=recommendation_status,
        sections=raw_sections,
    )
    sections = _sections_for_allocation_display(raw_sections, allocation_display)
    subtitle_zh, subtitle_en = _summary_subtitle_for_allocation(allocation_display)
    risk_notice_zh, risk_notice_en = _risk_notice_for_allocation(allocation_display)
    profile_insights = (
        None
        if user_intelligence is None
        else ProfileInsightsPayload(
            riskTier=user_intelligence.risk_tier,
            liquidityPreference=user_intelligence.liquidity_preference,
            investmentHorizon=user_intelligence.investment_horizon,
            returnObjective=user_intelligence.return_objective,
            drawdownSensitivity=user_intelligence.drawdown_sensitivity,
            derivedSignals=list(user_intelligence.derived_signals),
        )
    )
    market_intelligence_payload = (
        None
        if market_intelligence is None
        else RecommendationMarketIntelligencePayload(
            sentiment=market_intelligence.sentiment,
            stance=market_intelligence.stance,
            preferredCategories=list(market_intelligence.preferred_categories),
            avoidedCategories=list(market_intelligence.avoided_categories),
            evidenceRefs=list(market_intelligence.evidence_refs),
        )
    )

    return RecommendationResponse(
        summary=RecommendationSummary(
            titleZh=f"适合您的{profile_label_zh}配置建议",
            titleEn=f"A {profile_label_en} plan that fits you",
            subtitleZh=subtitle_zh,
            subtitleEn=subtitle_en,
        ),
        profileSummary=LocalizedText(
            zh=(
                user_intelligence.profile_summary_zh
                if user_intelligence is not None
                else (
                    "画像分析暂不可用，请人工复核后再确认推荐。"
                    if recommendation_status == "blocked"
                    else f"您的测评结果更接近{profile_label_zh}。"
                )
            ),
            en=(
                user_intelligence.profile_summary_en
                if user_intelligence is not None
                else (
                    "Profile analysis is unavailable and needs manual review."
                    if recommendation_status == "blocked"
                    else f"Your assessment aligns with a {profile_label_en} profile."
                )
            ),
        ),
        profileInsights=profile_insights,
        marketSummary=LocalizedText(
            zh=(
                market_intelligence.summary_zh
                if market_intelligence is not None
                else (
                    "市场与合规信息尚未完成 AI 评审，请人工复核。"
                    if recommendation_status == "blocked"
                    else "市场信息暂不可用，请稍后重试。"
                )
            ),
            en=(
                market_intelligence.summary_en
                if market_intelligence is not None
                else (
                    "Market and compliance review did not complete and need manual review."
                    if recommendation_status == "blocked"
                    else "Market intelligence is temporarily unavailable."
                )
            ),
        ),
        marketIntelligence=market_intelligence_payload,
        allocationDisplay=allocation_display,
        sections=sections,
        aggressiveOption=(
            RecommendationOption(
                titleZh=AGGRESSIVE_OPTION_TITLES[0],
                titleEn=AGGRESSIVE_OPTION_TITLES[1],
                subtitleZh=AGGRESSIVE_OPTION_SUBTITLES[0],
                subtitleEn=AGGRESSIVE_OPTION_SUBTITLES[1],
                allocation=_graph_allocation_display(
                    allocation=AGGRESSIVE_ALLOCATIONS[risk_profile].to_display(),
                    sections=raw_sections,
                ),
            )
            if include_aggressive_option
            else None
        ),
        riskNotice=LocalizedTextList(
            zh=risk_notice_zh,
            en=risk_notice_en,
        ),
        whyThisPlan=LocalizedTextList(
            zh=why_this_plan_zh,
            en=why_this_plan_en,
        ),
        reviewStatus=review_status,
        executionMode="agent_assisted",
        warnings=list(graph_state["warnings"]),
        recommendationStatus=recommendation_status,
        complianceReview=compliance_payload,
        marketEvidence=([] if market_intelligence is None else list(market_intelligence.evidence)),
        agentTrace=list(graph_state["agent_trace"]),
    )


# Backward-compatible alias for existing call sites.
def assemble_recommendation_response(
    recommendation: FinalRecommendation,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationResponse:
    return assemble_domain_recommendation_response(
        recommendation,
        include_aggressive_option=include_aggressive_option,
    )
