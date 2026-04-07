from __future__ import annotations

from financehub_market_api.recommendation.agents.sample_capture import (
    build_fixture_payload,
    capture_request_names,
    fixture_filename_for_request_name,
    sanitize_captured_body,
)


def test_capture_request_names_covers_all_six_agent_stages() -> None:
    assert capture_request_names() == (
        "user_profile",
        "market_intelligence",
        "fund_selection",
        "wealth_selection",
        "stock_selection",
        "explanation",
    )


def test_fixture_filename_generation_is_stable_per_request_name() -> None:
    assert fixture_filename_for_request_name("user_profile") == "user_profile.json"
    assert fixture_filename_for_request_name("market_intelligence") == "market_intelligence.json"
    assert fixture_filename_for_request_name("fund_selection") == "fund_selection.json"
    assert fixture_filename_for_request_name("wealth_selection") == "wealth_selection.json"
    assert fixture_filename_for_request_name("stock_selection") == "stock_selection.json"
    assert fixture_filename_for_request_name("explanation") == "explanation.json"


def test_sanitize_captured_body_removes_unstable_metadata_and_preserves_nested_shape() -> None:
    raw_body = {
        "id": "msg_123",
        "created_at": "2026-01-01T00:00:00Z",
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
                "id": "block_456",
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
            "request_id": "req_789",
        },
        "nested": {"items": [{"created_at": "soon", "keep": "value"}]},
    }

    sanitized = sanitize_captured_body(raw_body)

    assert sanitized == {
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
        },
        "nested": {"items": [{"keep": "value"}]},
    }
    assert raw_body["id"] == "msg_123"
    assert raw_body["content"][0]["id"] == "block_456"
    assert raw_body["usage"]["request_id"] == "req_789"


def test_build_fixture_payload_keeps_request_name_phase_and_sanitized_body() -> None:
    payload = build_fixture_payload(
        request_name="market_intelligence",
        phase="structured",
        body={
            "id": "msg_123",
            "content": [{"type": "text", "text": '{"summary_zh":"稳健","summary_en":"Steady"}'}],
        },
    )

    assert payload == {
        "request_name": "market_intelligence",
        "capture_phase": "structured",
        "body": {
            "content": [{"type": "text", "text": '{"summary_zh":"稳健","summary_en":"Steady"}'}],
        },
    }
