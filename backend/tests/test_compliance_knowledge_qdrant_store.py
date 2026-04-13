import pytest

import financehub_market_api.recommendation.compliance_knowledge.qdrant_store as qdrant_store_module
from financehub_market_api.recommendation.compliance_knowledge.qdrant_store import (
    QdrantComplianceKnowledgeStore,
)
from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceKnowledgeQuery,
)


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self._payload)


def test_search_posts_expected_qdrant_filter_payload() -> None:
    http_client = _FakeHttpClient(
        {
            "result": [
                {
                    "score": 0.94,
                    "payload": {
                        "evidence_id": "rule-001#1",
                        "rule_type": "suitability",
                        "jurisdiction": "CN",
                    },
                }
            ]
        }
    )
    store = QdrantComplianceKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="compliance_knowledge",
        http_client=http_client,
    )

    hits = store.search(
        query_vector=[0.1, 0.2],
        query=ComplianceKnowledgeQuery(
            query_text="公募基金 适当性 匹配",
            rule_types=["suitability", "risk_disclosure"],
            categories=["fund"],
            risk_tiers=["R2"],
            audience="fund_sales",
            jurisdiction="CN",
            effective_on="2026-04-13",
        ),
        total_limit=5,
    )

    assert [hit["evidence_id"] for hit in hits] == ["rule-001#1"]
    assert len(http_client.calls) == 1
    assert http_client.calls[0]["json"]["filter"] == {
        "must": [
            {"key": "jurisdiction", "match": {"value": "CN"}},
            {"key": "audience", "match": {"value": "fund_sales"}},
            {"key": "effective_date", "range": {"lte": "2026-04-13"}},
        ],
        "should": [
            {"key": "rule_type", "match": {"value": "suitability"}},
            {"key": "rule_type", "match": {"value": "risk_disclosure"}},
            {"key": "applies_to_categories", "match": {"value": "fund"}},
        ],
    }


def test_search_raises_for_malformed_success_payload() -> None:
    store = QdrantComplianceKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="compliance_knowledge",
        http_client=_FakeHttpClient({"status": "ok"}),
    )

    with pytest.raises(ValueError, match="malformed qdrant query response"):
        store.search(
            query_vector=[0.1, 0.2],
            query=ComplianceKnowledgeQuery(
                query_text="理财 披露 风险 提示",
                rule_types=["risk_disclosure"],
                categories=["wealth_management"],
            ),
            total_limit=3,
        )


def test_search_returns_empty_when_total_limit_or_rule_types_are_empty() -> None:
    store = QdrantComplianceKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="compliance_knowledge",
        http_client=_FakeHttpClient({"result": []}),
    )

    assert (
        store.search(
            query_vector=[0.1, 0.2],
            query=ComplianceKnowledgeQuery(
                query_text="基金 适当性",
                rule_types=[],
                categories=["fund"],
            ),
            total_limit=5,
        )
        == []
    )
    assert (
        store.search(
            query_vector=[0.1, 0.2],
            query=ComplianceKnowledgeQuery(
                query_text="基金 适当性",
                rule_types=["suitability"],
                categories=["fund"],
            ),
            total_limit=0,
        )
        == []
    )


def test_qdrant_store_does_not_create_default_http_client_eagerly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_client_creation() -> object:
        raise AssertionError("httpx.Client should not be created at __init__ time")

    monkeypatch.setattr(qdrant_store_module.httpx, "Client", _unexpected_client_creation)

    store = QdrantComplianceKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="compliance_knowledge",
    )

    assert store is not None
