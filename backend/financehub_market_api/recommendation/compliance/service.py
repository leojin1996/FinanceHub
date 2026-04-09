from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from financehub_market_api.recommendation.schemas import CandidateProduct

_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}
_HIGH_LIQUIDITY_LABELS = {"T+0", "T+1", "开放式"}
_LOW_RISK_MAX_DAYS = 90


class ComplianceReviewResult(BaseModel):
    verdict: Literal["approve", "revise_conservative", "block"]
    reason_zh: str
    reason_en: str
    disclosures_zh: list[str] = Field(default_factory=list)
    disclosures_en: list[str] = Field(default_factory=list)
    suitability_notes_zh: list[str] = Field(default_factory=list)
    suitability_notes_en: list[str] = Field(default_factory=list)


class ComplianceReviewService:
    def review(
        self,
        *,
        risk_tier: str,
        liquidity_preference: str | None = None,
        candidates: list[CandidateProduct],
    ) -> ComplianceReviewResult:
        allowed_risk_level = _RISK_ORDER.get(risk_tier)
        if allowed_risk_level is None:
            return ComplianceReviewResult(
                verdict="revise_conservative",
                reason_zh="用户风险等级无法识别，需按更稳健方案进行调整后再评审。",
                reason_en="The user risk tier is unknown, so the plan must be revised conservatively before approval.",
                disclosures_zh=[
                    "本建议仅供参考，最终请以产品说明书及适当性评估结果为准。",
                    "请重点关注产品风险等级、期限与流动性安排。",
                ],
                disclosures_en=[
                    "This recommendation is for reference only and must be validated with formal suitability checks.",
                    "Review product risk level, tenor, and liquidity terms before investing.",
                ],
                suitability_notes_zh=[
                    "请先完成正式风险测评，再确认推荐方案是否适配。",
                    "若近期有大额支出计划，请优先选择流动性更高的产品。",
                ],
                suitability_notes_en=[
                    "Complete a formal risk assessment before finalizing the recommendation.",
                    "If near-term cash needs are expected, prioritize more liquid products.",
                ],
            )

        exceeds_profile = False
        for candidate in candidates:
            candidate_risk_level = _RISK_ORDER.get(candidate.risk_level)
            if candidate_risk_level is None or candidate_risk_level > allowed_risk_level:
                exceeds_profile = True
                break
        if exceeds_profile:
            return ComplianceReviewResult(
                verdict="revise_conservative",
                reason_zh="候选产品中存在超出或无法识别风险等级的产品，需调整为更稳健方案。",
                reason_en="At least one candidate exceeds or has an unknown risk level, so the plan must be revised to a more conservative mix.",
                disclosures_zh=[
                    "本建议仅供参考，最终请以产品说明书及适当性评估结果为准。",
                    "请重点关注产品风险等级、期限与流动性安排。",
                ],
                disclosures_en=[
                    "This recommendation is for reference only and must be validated with formal suitability checks.",
                    "Review product risk level, tenor, and liquidity terms before investing.",
                ],
                suitability_notes_zh=[
                    "请将候选产品风险等级控制在您的风险承受范围内。",
                    "若需保留权益增强，请降低仓位并重新确认适当性。",
                ],
                suitability_notes_en=[
                    "Keep candidate risk levels within the user's approved suitability band.",
                    "If equity exposure is retained, reduce sizing and rerun suitability checks.",
                ],
            )

        if self._requires_conservative_liquidity_guardrail(
            risk_tier=risk_tier,
            liquidity_preference=liquidity_preference,
        ):
            illiquid_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if not self._matches_low_risk_liquidity_requirement(candidate.liquidity)
                ),
                None,
            )
            if illiquid_candidate is not None:
                return ComplianceReviewResult(
                    verdict="revise_conservative",
                    reason_zh="候选产品流动性偏弱，不适合当前稳健画像，需调整为更高流动性的方案。",
                    reason_en="At least one candidate is too illiquid for the current conservative suitability profile, so the plan must be revised.",
                    disclosures_zh=[
                        "请重点关注产品封闭期、申赎安排与到账时间。",
                        "理财非存款，投资需谨慎。",
                    ],
                    disclosures_en=[
                        "Review lock-up terms, redemption arrangements, and settlement timing carefully.",
                        "Investing involves risk. Proceed prudently.",
                    ],
                    suitability_notes_zh=[
                        "请优先选择封闭期不超过 90 天或支持 T+0/T+1 赎回的产品。",
                        "若资金一年内可能使用，请再次确认申赎规则与到账时间。",
                    ],
                    suitability_notes_en=[
                        "Prefer products with lock-up periods no longer than 90 days or T+0/T+1 redemption.",
                        "If funds may be needed within a year, verify redemption rules and settlement timing again.",
                    ],
                )

        return ComplianceReviewResult(
            verdict="approve",
            reason_zh="候选产品风险等级未超过用户风险承受能力，可继续进入推荐结果。",
            reason_en="All candidate products are within the user's risk tier and can proceed.",
            disclosures_zh=["市场有风险，投资需谨慎。"],
            disclosures_en=["Investing involves risk. Proceed prudently."],
            suitability_notes_zh=["当前候选产品在风险与流动性维度内基本匹配。"],
            suitability_notes_en=[
                "The current candidate set is broadly aligned on risk and liquidity dimensions."
            ],
        )

    def _requires_conservative_liquidity_guardrail(
        self,
        *,
        risk_tier: str,
        liquidity_preference: str | None,
    ) -> bool:
        return risk_tier in {"R1", "R2"} or liquidity_preference == "high"

    def _matches_low_risk_liquidity_requirement(self, liquidity: str | None) -> bool:
        normalized = (liquidity or "").strip()
        if normalized in _HIGH_LIQUIDITY_LABELS:
            return True
        if normalized.endswith("天"):
            days_text = normalized.removesuffix("天")
            if days_text.isdigit():
                return int(days_text) <= _LOW_RISK_MAX_DAYS
        return False
