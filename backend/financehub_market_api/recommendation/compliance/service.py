from __future__ import annotations

from pydantic import BaseModel, Field

from financehub_market_api.recommendation.schemas import CandidateProduct

_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


class ComplianceReviewResult(BaseModel):
    verdict: str
    reason_zh: str
    reason_en: str
    disclosures_zh: list[str] = Field(default_factory=list)
    disclosures_en: list[str] = Field(default_factory=list)


class ComplianceReviewService:
    def review(
        self,
        *,
        risk_tier: str,
        candidates: list[CandidateProduct],
    ) -> ComplianceReviewResult:
        allowed_risk_level = _RISK_ORDER.get(risk_tier, 0)

        exceeds_profile = any(
            _RISK_ORDER.get(candidate.risk_level, 0) > allowed_risk_level
            for candidate in candidates
        )
        if exceeds_profile:
            return ComplianceReviewResult(
                verdict="revise_conservative",
                reason_zh="候选产品中存在风险等级高于用户风险承受能力的产品，需调整为更稳健方案。",
                reason_en="At least one candidate exceeds the user's risk profile and the plan must be revised to a more conservative mix.",
                disclosures_zh=[
                    "本建议仅供参考，最终请以产品说明书及适当性评估结果为准。",
                    "请重点关注产品风险等级、期限与流动性安排。",
                ],
                disclosures_en=[
                    "This recommendation is for reference only and must be validated with formal suitability checks.",
                    "Review product risk level, tenor, and liquidity terms before investing.",
                ],
            )

        return ComplianceReviewResult(
            verdict="approve",
            reason_zh="候选产品风险等级未超过用户风险承受能力，可继续进入推荐结果。",
            reason_en="All candidate products are within the user's risk tier and can proceed.",
            disclosures_zh=["市场有风险，投资需谨慎。"],
            disclosures_en=["Investing involves risk. Proceed prudently."],
        )
