from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.graph import (
    append_agent_trace_event,
    append_warning,
    build_initial_graph_state,
)


def _build_payload() -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我有 10 万闲钱，想存一年，不想亏本",
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": True,
            "questionnaireAnswers": [],
            "riskAssessmentResult": {
                "baseProfile": "balanced",
                "dimensionLevels": {
                    "capitalStability": "medium",
                    "investmentExperience": "medium",
                    "investmentHorizon": "medium",
                    "returnObjective": "medium",
                    "riskTolerance": "medium",
                },
                "dimensionScores": {
                    "capitalStability": 12,
                    "investmentExperience": 12,
                    "investmentHorizon": 12,
                    "returnObjective": 12,
                    "riskTolerance": 12,
                },
                "finalProfile": "balanced",
                "totalScore": 60,
            },
        }
    )


def test_build_initial_graph_state_seeds_request_context_and_trace_defaults() -> None:
    payload = _build_payload()
    state = build_initial_graph_state(payload)

    assert state["request_context"].user_intent_text == "我有 10 万闲钱，想存一年，不想亏本"
    assert state["request_context"].request_id
    assert state["request_context"].trace_id
    assert state["warnings"] == []
    assert state["agent_trace"] == []
    assert state["final_response"] is None

    payload.userIntentText = "变更后的意图"
    assert state["request_context"].payload.userIntentText == "我有 10 万闲钱，想存一年，不想亏本"


def test_append_helpers_preserve_existing_state() -> None:
    state = build_initial_graph_state(_build_payload())
    original_warnings = state["warnings"]
    original_agent_trace = state["agent_trace"]

    warning_state = append_warning(
        state,
        stage="market_intelligence",
        code="provider_error",
        message="timeout",
    )
    trace_state = append_agent_trace_event(
        warning_state,
        node_name="market_intelligence",
        request_name="market_intelligence",
        status="error",
        model_name="claude-opus-4-6",
        response_summary="timeout",
    )

    assert state["warnings"] == []
    assert state["agent_trace"] == []
    assert warning_state["warnings"] is not original_warnings
    assert warning_state["agent_trace"] is original_agent_trace
    assert trace_state["warnings"] is warning_state["warnings"]
    assert trace_state["agent_trace"] is not original_agent_trace
    assert trace_state["warnings"][0].stage == "market_intelligence"
    assert trace_state["agent_trace"][0].requestName == "market_intelligence"
