import pytest

import financehub_market_api.recommendation.product_knowledge.qdrant_store as qdrant_store_module
from financehub_market_api.recommendation.product_knowledge.qdrant_store import (
    QdrantProductKnowledgeStore,
)


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _SequentialFakeHttpClient:
    def __init__(self, payloads: list[object]) -> None:
        self._payloads = list(payloads)
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
        if not self._payloads:
            raise AssertionError("unexpected extra HTTP call")
        return _FakeResponse(self._payloads.pop(0))


def test_search_queries_per_product_and_enforces_per_product_limit() -> None:
    http_client = _SequentialFakeHttpClient(
        [
            {
                "result": [
                    {
                        "score": 0.98,
                        "payload": {
                            "evidence_id": "fund-001-public-1",
                            "product_id": "fund-001",
                            "visibility": "public",
                        },
                    },
                    {
                        "score": 0.95,
                        "payload": {
                            "evidence_id": "fund-001-public-2",
                            "product_id": "fund-001",
                            "visibility": "public",
                        },
                    },
                ]
            },
            {
                "result": [
                    {
                        "score": 0.97,
                        "payload": {
                            "evidence_id": "fund-002-public-1",
                            "product_id": "fund-002",
                            "visibility": "public",
                        },
                    }
                ]
            },
        ]
    )
    store = QdrantProductKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="product_knowledge",
        http_client=http_client,
    )

    hits = store.search(
        query_vector=[0.1, 0.2],
        product_ids=["fund-001", "fund-002"],
        include_internal=False,
        limit_per_product=1,
        total_limit=5,
    )

    assert [hit["evidence_id"] for hit in hits] == [
        "fund-001-public-1",
        "fund-002-public-1",
    ]
    assert len(http_client.calls) == 2
    assert http_client.calls[0]["json"]["limit"] == 1
    assert http_client.calls[1]["json"]["limit"] == 1
    assert http_client.calls[0]["json"]["filter"] == {
        "must": [
            {
                "key": "product_id",
                "match": {"value": "fund-001"},
            },
            {
                "key": "visibility",
                "match": {"value": "public"},
            },
        ]
    }


def test_search_raises_for_malformed_success_payload() -> None:
    store = QdrantProductKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="product_knowledge",
        http_client=_SequentialFakeHttpClient([{"status": "ok"}]),
    )

    with pytest.raises(ValueError, match="malformed qdrant query response"):
        store.search(
            query_vector=[0.1, 0.2],
            product_ids=["fund-001"],
            include_internal=True,
            limit_per_product=2,
            total_limit=4,
        )


def test_search_applies_total_limit_after_merging_products() -> None:
    store = QdrantProductKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="product_knowledge",
        http_client=_SequentialFakeHttpClient(
            [
                {
                    "result": [
                        {
                            "score": 0.91,
                            "payload": {
                                "evidence_id": "fund-001-public-1",
                                "product_id": "fund-001",
                                "visibility": "public",
                            },
                        }
                    ]
                },
                {
                    "result": [
                        {
                            "score": 0.93,
                            "payload": {
                                "evidence_id": "fund-002-public-1",
                                "product_id": "fund-002",
                                "visibility": "public",
                            },
                        }
                    ]
                },
            ]
        ),
    )

    hits = store.search(
        query_vector=[0.1],
        product_ids=["fund-001", "fund-002"],
        include_internal=True,
        limit_per_product=2,
        total_limit=1,
    )

    assert [hit["evidence_id"] for hit in hits] == ["fund-002-public-1"]


def test_qdrant_store_does_not_create_default_http_client_eagerly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_client_creation() -> object:
        raise AssertionError("httpx.Client should not be created at __init__ time")

    monkeypatch.setattr(qdrant_store_module.httpx, "Client", _unexpected_client_creation)

    store = QdrantProductKnowledgeStore(
        base_url="http://qdrant.local",
        collection_name="product_knowledge",
    )

    assert store is not None
