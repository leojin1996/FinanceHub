from __future__ import annotations

import json
from pathlib import Path

import pytest

from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AnthropicChatProvider,
    ProviderConfig,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "anthropic_responses"


def _provider() -> AnthropicChatProvider:
    return AnthropicChatProvider(
        ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key="test-key",
            base_url="https://example.com/v1",
        )
    )


@pytest.mark.parametrize(
    ("request_name", "response_schema", "output_model"),
    [
        (
            "user_profile_analyst",
            UserProfileAgentOutput.model_json_schema(),
            UserProfileAgentOutput,
        ),
        (
            "market_intelligence",
            MarketIntelligenceAgentOutput.model_json_schema(),
            MarketIntelligenceAgentOutput,
        ),
        (
            "product_match_expert",
            ProductMatchAgentOutput.model_json_schema(),
            ProductMatchAgentOutput,
        ),
        (
            "compliance_risk_officer",
            ComplianceReviewAgentOutput.model_json_schema(),
            ComplianceReviewAgentOutput,
        ),
        (
            "manager_coordinator",
            ManagerCoordinatorAgentOutput.model_json_schema(),
            ManagerCoordinatorAgentOutput,
        ),
    ],
)
def test_parse_response_body_extracts_required_fields_from_sanitized_real_fixture(
    request_name: str,
    response_schema: dict[str, object],
    output_model: type[
        UserProfileAgentOutput
        | MarketIntelligenceAgentOutput
        | ProductMatchAgentOutput
        | ComplianceReviewAgentOutput
        | ManagerCoordinatorAgentOutput
    ],
) -> None:
    fixture_path = _FIXTURE_DIR / f"{request_name}.json"
    assert fixture_path.is_file(), f"Missing fixture file: {fixture_path}"
    fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture_payload["request_name"] == request_name

    payload = _provider()._parse_response_body(
        fixture_payload["body"],
        response_schema=response_schema,
    )

    validated_output = output_model.model_validate(payload)
    assert isinstance(validated_output, output_model)
