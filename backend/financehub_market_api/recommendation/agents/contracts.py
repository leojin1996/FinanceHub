from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


def _normalize_text_list(
    value: object,
    *,
    preferred_keys: tuple[str, ...],
) -> list[str] | None:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return None

    normalized_items: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized_items.append(item)
            continue
        if isinstance(item, dict):
            for key in preferred_keys:
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    normalized_items.append(candidate)
                    break
            else:
                for candidate in item.values():
                    if isinstance(candidate, str) and candidate.strip():
                        normalized_items.append(candidate)
                        break
                else:
                    normalized_items.append(str(item))
            continue
        normalized_items.append(str(item))
    return normalized_items


class UserProfileAgentOutput(BaseModel):
    risk_tier: str = Field(min_length=1)
    liquidity_preference: str = Field(min_length=1)
    investment_horizon: str = Field(min_length=1)
    return_objective: str = Field(min_length=1)
    drawdown_sensitivity: str = Field(min_length=1)
    profile_focus_zh: str = Field(min_length=1)
    profile_focus_en: str = Field(min_length=1)
    derived_signals: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_derived_signals(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        raw_risk_tier = normalized.get("risk_tier")
        if isinstance(raw_risk_tier, str):
            risk_tier_aliases = {
                "r1": "R1",
                "r2": "R2",
                "r3": "R3",
                "r4": "R4",
                "r5": "R5",
                "conservative": "R2",
                "stable": "R2",
                "balanced": "R3",
                "growth": "R4",
                "aggressive": "R5",
            }
            alias_key = raw_risk_tier.strip().lower()
            normalized["risk_tier"] = risk_tier_aliases.get(alias_key, raw_risk_tier)

        raw_signals = normalized.get("derived_signals")
        if not isinstance(raw_signals, list):
            return normalized

        derived_signals: list[str] = []
        for item in raw_signals:
            if isinstance(item, str):
                derived_signals.append(item)
                continue
            if isinstance(item, dict):
                signal = item.get("signal")
                rationale = item.get("rationale") or item.get("reason")
                if isinstance(signal, str) and isinstance(rationale, str):
                    derived_signals.append(f"{signal}: {rationale}")
                    continue
                if isinstance(signal, str):
                    derived_signals.append(signal)
                    continue
                source = item.get("source")
                if isinstance(source, str) and isinstance(rationale, str):
                    derived_signals.append(f"{source}: {rationale}")
                    continue
            derived_signals.append(str(item))

        normalized["derived_signals"] = derived_signals
        return normalized


class MarketIntelligenceAgentOutput(BaseModel):
    sentiment: str = Field(min_length=1)
    stance: str = Field(min_length=1)
    preferred_categories: list[str] = Field(default_factory=list)
    avoided_categories: list[str] = Field(default_factory=list)
    summary_zh: str = Field(min_length=1)
    summary_en: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        raw_sentiment = normalized.get("sentiment")
        if isinstance(raw_sentiment, str):
            sentiment_aliases = {
                "bullish": "positive",
                "constructive": "positive",
                "bearish": "negative",
                "risk_off": "negative",
                "mixed": "neutral",
            }
            normalized["sentiment"] = sentiment_aliases.get(
                raw_sentiment.strip().lower(),
                raw_sentiment,
            )

        raw_stance = normalized.get("stance")
        if isinstance(raw_stance, str):
            stance_aliases = {
                "bullish": "offensive",
                "constructive": "offensive",
                "opportunistic": "offensive",
                "aggressive": "offensive",
                "risk_on": "offensive",
                "bearish": "defensive",
                "cautious": "defensive",
                "neutral": "balanced",
                "mixed": "balanced",
            }
            normalized["stance"] = stance_aliases.get(
                raw_stance.strip().lower(),
                raw_stance,
            )

        return normalized


class ProductRankingAgentOutput(BaseModel):
    ranked_ids: list[str] = Field(min_length=1)


class ProductMatchAgentOutput(BaseModel):
    recommended_categories: list[str] = Field(default_factory=list)
    selected_product_ids: list[str] = Field(default_factory=list)
    fund_ids: list[str] = Field(default_factory=list)
    wealth_management_ids: list[str] = Field(default_factory=list)
    stock_ids: list[str] = Field(default_factory=list)
    ranking_rationale_zh: str = Field(min_length=1)
    ranking_rationale_en: str = Field(min_length=1)
    filtered_out_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        selected_groups = normalized.get("selected_ids")
        if not isinstance(selected_groups, dict):
            alias_selected_groups = normalized.get("selected_products")
            if isinstance(alias_selected_groups, dict):
                selected_groups = alias_selected_groups
        if isinstance(selected_groups, dict):
            if "fund_ids" not in normalized and isinstance(selected_groups.get("fund"), list):
                normalized["fund_ids"] = list(selected_groups["fund"])
            if "wealth_management_ids" not in normalized and isinstance(
                selected_groups.get("wealth_management"), list
            ):
                normalized["wealth_management_ids"] = list(
                    selected_groups["wealth_management"]
                )
            if "stock_ids" not in normalized and isinstance(selected_groups.get("stock"), list):
                normalized["stock_ids"] = list(selected_groups["stock"])

        selected_product_ids = normalized.get("selected_product_ids")
        if isinstance(selected_product_ids, list):
            ordered_ids = [str(item) for item in selected_product_ids]
        else:
            ordered_ids = [
                *[str(item) for item in normalized.get("fund_ids", [])],
                *[str(item) for item in normalized.get("wealth_management_ids", [])],
                *[str(item) for item in normalized.get("stock_ids", [])],
            ]
        primary_recommendation_id = normalized.get("primary_recommendation_id")
        if isinstance(primary_recommendation_id, str) and primary_recommendation_id in ordered_ids:
            ordered_ids = [
                primary_recommendation_id,
                *[
                    candidate_id
                    for candidate_id in ordered_ids
                    if candidate_id != primary_recommendation_id
                ],
            ]
        if ordered_ids:
            normalized["selected_product_ids"] = ordered_ids

        ranking_rationale = normalized.get("ranking_rationale")
        if isinstance(ranking_rationale, dict):
            if "ranking_rationale_zh" not in normalized and isinstance(
                ranking_rationale.get("zh"), str
            ):
                normalized["ranking_rationale_zh"] = ranking_rationale["zh"]
            if "ranking_rationale_en" not in normalized and isinstance(
                ranking_rationale.get("en"), str
            ):
                normalized["ranking_rationale_en"] = ranking_rationale["en"]
        if "ranking_rationale_zh" not in normalized and isinstance(
            normalized.get("rationale_zh"), str
        ):
            normalized["ranking_rationale_zh"] = normalized["rationale_zh"]
        if "ranking_rationale_en" not in normalized and isinstance(
            normalized.get("rationale_en"), str
        ):
            normalized["ranking_rationale_en"] = normalized["rationale_en"]

        filtered_out = normalized.get("filtered_out")
        filtered_out_reasons = normalized.get("filtered_out_reasons")
        if isinstance(filtered_out_reasons, dict):
            normalized["filtered_out_reasons"] = [
                str(reason) for reason in filtered_out_reasons.values()
            ]
        if "filtered_out_reasons" not in normalized:
            if isinstance(filtered_out, list):
                normalized["filtered_out_reasons"] = [str(item) for item in filtered_out]
            elif isinstance(filtered_out, dict):
                if isinstance(filtered_out.get("reasons"), dict):
                    normalized["filtered_out_reasons"] = [
                        str(reason) for reason in filtered_out["reasons"].values()
                    ]
                else:
                    normalized["filtered_out_reasons"] = [
                        f"{candidate_id}: {reason}"
                        for candidate_id, reason in filtered_out.items()
                    ]

        return normalized

    @model_validator(mode="after")
    def _validate_non_empty_selection(self) -> ProductMatchAgentOutput:
        if (
            self.selected_product_ids
            or self.fund_ids
            or self.wealth_management_ids
            or self.stock_ids
        ):
            return self
        raise ValueError(
            "product_match_expert must return at least one selected product id"
        )


class ComplianceReviewAgentOutput(BaseModel):
    verdict: str = Field(min_length=1)
    approved_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    reason_summary_zh: str = Field(min_length=1)
    reason_summary_en: str = Field(min_length=1)
    required_disclosures_zh: list[str] = Field(default_factory=list)
    required_disclosures_en: list[str] = Field(default_factory=list)
    suitability_notes_zh: list[str] = Field(default_factory=list)
    suitability_notes_en: list[str] = Field(default_factory=list)
    applied_rule_ids: list[str] = Field(default_factory=list)
    blocking_reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        alias_pairs = {
            "approved_candidate_ids": "approved_ids",
            "rejected_candidate_ids": "rejected_ids",
            "reason_zh": "reason_summary_zh",
            "reason_en": "reason_summary_en",
        }
        for source_key, target_key in alias_pairs.items():
            if target_key not in normalized and source_key in normalized:
                normalized[target_key] = normalized[source_key]

        disclosures = normalized.get("disclosures")
        disclosure_list = _normalize_text_list(
            disclosures,
            preferred_keys=("disclosure_zh", "disclosure_en", "message_zh", "message_en"),
        )
        if disclosure_list is not None:
            if "required_disclosures_zh" not in normalized:
                normalized["required_disclosures_zh"] = list(disclosure_list)
            if "required_disclosures_en" not in normalized:
                normalized["required_disclosures_en"] = list(disclosure_list)
        normalized_required_disclosures_zh = _normalize_text_list(
            normalized.get("required_disclosures_zh"),
            preferred_keys=("disclosure_zh", "disclosure", "message_zh", "message"),
        )
        if normalized_required_disclosures_zh is not None:
            normalized["required_disclosures_zh"] = normalized_required_disclosures_zh
        normalized_required_disclosures_en = _normalize_text_list(
            normalized.get("required_disclosures_en"),
            preferred_keys=("disclosure_en", "disclosure", "message_en", "message"),
        )
        if normalized_required_disclosures_en is not None:
            normalized["required_disclosures_en"] = normalized_required_disclosures_en

        suitability_notes = normalized.get("suitability_notes")
        note_list = _normalize_text_list(
            suitability_notes,
            preferred_keys=("note_zh", "note_en", "suitability_note", "message"),
        )
        if note_list is not None:
            if "suitability_notes_zh" not in normalized:
                normalized["suitability_notes_zh"] = list(note_list)
            if "suitability_notes_en" not in normalized:
                normalized["suitability_notes_en"] = list(note_list)
        normalized_suitability_notes_zh = _normalize_text_list(
            normalized.get("suitability_notes_zh"),
            preferred_keys=("note_zh", "note", "message_zh", "message"),
        )
        if normalized_suitability_notes_zh is not None:
            normalized["suitability_notes_zh"] = normalized_suitability_notes_zh
        normalized_suitability_notes_en = _normalize_text_list(
            normalized.get("suitability_notes_en"),
            preferred_keys=("note_en", "note", "message_en", "message"),
        )
        if normalized_suitability_notes_en is not None:
            normalized["suitability_notes_en"] = normalized_suitability_notes_en

        return normalized


class ExplanationAgentOutput(BaseModel):
    why_this_plan_zh: list[str] = Field(min_length=1)
    why_this_plan_en: list[str] = Field(min_length=1)


class ManagerCoordinatorAgentOutput(BaseModel):
    recommendation_status: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    summary_en: str = Field(min_length=1)
    why_this_plan_zh: list[str] = Field(min_length=1)
    why_this_plan_en: list[str] = Field(min_length=1)
