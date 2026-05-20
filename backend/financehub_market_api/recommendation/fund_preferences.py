from __future__ import annotations

from financehub_market_api.recommendation.schemas import CandidateProduct

_EQUITY_FUND_KEYWORDS = (
    "股票型",
    "权益型",
    "权益增强",
    "成长弹性",
    "偏股",
    "equity",
    "stock fund",
)
_BOND_FUND_KEYWORDS = (
    "债券型",
    "债券",
    "固收",
    "bond",
    "stable core",
)


def classify_fund_candidate_style(candidate: CandidateProduct) -> str:
    if candidate.category != "fund":
        return "other"

    searchable_text = " ".join(
        [
            *candidate.tags_zh,
            *candidate.tags_en,
            candidate.rationale_zh,
            candidate.rationale_en,
        ]
    ).lower()
    if any(keyword.lower() in searchable_text for keyword in _EQUITY_FUND_KEYWORDS):
        return "equity"
    if any(keyword.lower() in searchable_text for keyword in _BOND_FUND_KEYWORDS):
        return "bond"
    if candidate.risk_level in {"R4", "R5"}:
        return "equity"
    if candidate.risk_level in {"R1", "R2"}:
        return "bond"
    return "other"


def fund_preference_rank(candidate: CandidateProduct, *, risk_profile: str) -> int:
    if candidate.category != "fund":
        return 0
    if risk_profile not in {"growth", "aggressive"}:
        return 0

    style = classify_fund_candidate_style(candidate)
    if style == "equity":
        return 0
    if style == "other":
        return 1
    return 2


def order_fund_candidates_for_profile(
    candidates: list[CandidateProduct],
    *,
    risk_profile: str,
) -> list[CandidateProduct]:
    indexed_candidates = list(enumerate(candidates))
    ordered = sorted(
        indexed_candidates,
        key=lambda item: (
            fund_preference_rank(item[1], risk_profile=risk_profile),
            item[0],
        ),
    )
    return [candidate for _, candidate in ordered]
