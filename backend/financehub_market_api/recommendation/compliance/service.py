from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from financehub_market_api.recommendation.schemas import CandidateProduct

_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


class ComplianceReviewResult(BaseModel):
    verdict: Literal["approve", "revise_conservative", "block"]
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
            )

        return ComplianceReviewResult(
            verdict="approve",
            reason_zh="候选产品风险等级未超过用户风险承受能力，可继续进入推荐结果。",
            reason_en="All candidate products are within the user's risk tier and can proceed.",
            disclosures_zh=["市场有风险，投资需谨慎。"],
            disclosures_en=["Investing involves risk. Proceed prudently."],
        )
