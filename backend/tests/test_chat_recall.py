from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from financehub_market_api.chat.qdrant_store import QdrantChatMessageStore
from financehub_market_api.chat.recall_service import (
    ChatHistoryRecallService,
    build_chat_history_recall_service_from_env,
)


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class _FakeChatVectorStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.search_results: list[dict[str, object]] = []

    def upsert_user_message(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        content: str,
        created_at: str,
        vector: list[float],
        content_normalized: str,
        content_fingerprint: str,
        preference_tags: list[str],
        topic_tags: list[str],
        symbol_mentions: list[str],
        is_preference_memory: bool,
        information_density: float,
        recency_bucket: str,
    ) -> None:
        self.upserts.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "message_id": message_id,
                "content": content,
                "created_at": created_at,
                "vector": vector,
                "content_normalized": content_normalized,
                "content_fingerprint": content_fingerprint,
                "preference_tags": preference_tags,
                "topic_tags": topic_tags,
                "symbol_mentions": symbol_mentions,
                "is_preference_memory": is_preference_memory,
                "information_density": information_density,
                "recency_bucket": recency_bucket,
            }
        )

    def search(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        limit: int,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, object]]:
        call = {"user_id": user_id, "query_vector": query_vector, "limit": limit}
        if exclude_session_id is not None:
            call["exclude_session_id"] = exclude_session_id
        self.search_calls.append(call)
        return list(self.search_results)


class _FailingEmbeddingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        raise self._exc


class _FailingSearchChatVectorStore(_FakeChatVectorStore):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def search(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        limit: int,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, object]]:
        call = {"user_id": user_id, "query_vector": query_vector, "limit": limit}
        if exclude_session_id is not None:
            call["exclude_session_id"] = exclude_session_id
        self.search_calls.append(call)
        raise self._exc


def test_build_chat_message_metadata_extracts_preference_tags_and_fingerprint() -> None:
    from financehub_market_api.chat.metadata import build_chat_message_metadata

    metadata = build_chat_message_metadata(
        content="我更看重流动性，希望一年内随时能用钱，最多接受小幅回撤。",
        created_at="2026-04-16T08:00:00+00:00",
    )

    assert metadata.content_normalized
    assert metadata.content_fingerprint
    assert "liquidity_high" in metadata.preference_tags
    assert "horizon_short" in metadata.preference_tags
    assert "drawdown_low" in metadata.preference_tags
    assert metadata.is_preference_memory is True
    assert metadata.recency_bucket == "last_30d"
    assert metadata.information_density > 0


def test_build_recall_query_context_uses_current_and_recent_user_messages() -> None:
    from financehub_market_api.chat.metadata import build_recall_query_context

    context = build_recall_query_context(
        current_user_message="结合我的历史偏好继续给建议",
        recent_user_messages=[
            "我更看重流动性",
            "我的持有期大概一年到两年",
            "最近市场波动有点大",
        ],
    )

    assert "current_user_message=结合我的历史偏好继续给建议" in context.embedding_text
    assert (
        "recent_user_context=我更看重流动性 | 我的持有期大概一年到两年 | 最近市场波动有点大"
        in context.embedding_text
    )
    assert "liquidity_high" in context.preference_tags
    assert "horizon_short" in context.preference_tags


def test_build_chat_message_metadata_handles_colloquial_liquidity_and_drawdown_language() -> None:
    from financehub_market_api.chat.metadata import build_chat_message_metadata

    metadata = build_chat_message_metadata(
        content="这笔钱主要当备用金，最好随取随用，不希望净值波动太大，也别冒太大风险。",
        created_at="2026-04-16T08:00:00+00:00",
    )

    assert "liquidity_high" in metadata.preference_tags
    assert "drawdown_low" in metadata.preference_tags
    assert "risk_low" in metadata.preference_tags
    assert "wealth_management" in metadata.topic_tags
    assert "risk_management" in metadata.topic_tags


def test_build_chat_message_metadata_handles_colloquial_horizon_growth_and_volatility_language() -> None:
    from financehub_market_api.chat.metadata import build_chat_message_metadata

    metadata = build_chat_message_metadata(
        content="这部分算闲钱，能放两三年，也能承受一些波动，想多赚一点弹性。",
        created_at="2026-04-16T08:00:00+00:00",
    )

    assert "horizon_medium" in metadata.preference_tags
    assert "drawdown_medium" in metadata.preference_tags
    assert "growth" in metadata.preference_tags


def test_recall_builds_composite_query_and_returns_deduplicated_snippets() -> None:
    store = _FakeChatVectorStore()
    store.search_results = [
        {"content": "我更看重流动性", "score": 0.91},
        {"content": "我更看重流动性", "score": 0.90},
        {"content": "我能接受三到五年持有", "score": 0.88},
    ]
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    snippets = service.recall(
        user_id="user-1",
        risk_profile="balanced",
        user_intent_text="希望兼顾稳健和成长",
        latest_user_message="最近更关注科技成长",
        limit=10,
    )

    assert snippets == ["我更看重流动性", "我能接受三到五年持有"]
    assert "risk_profile=balanced" in embeddings.queries[0]
    assert "user_intent=希望兼顾稳健和成长" in embeddings.queries[0]
    assert "latest_user_message=最近更关注科技成长" in embeddings.queries[0]
    assert store.search_calls == [
        {"user_id": "user-1", "query_vector": [0.1, 0.2, 0.3], "limit": 80}
    ]


def test_index_user_message_skips_blank_content() -> None:
    store = _FakeChatVectorStore()
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    service.index_user_message(
        user_id="user-1",
        session_id="session-1",
        message_id="msg-1",
        content="   ",
        created_at="2026-04-13T00:00:00+00:00",
    )

    assert embeddings.queries == []
    assert store.upserts == []


def test_index_user_message_embeds_content_and_upserts_vector() -> None:
    store = _FakeChatVectorStore()
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    service.index_user_message(
        user_id="user-1",
        session_id="session-1",
        message_id="msg-1",
        content="hello",
        created_at="2026-04-13T00:00:00+00:00",
    )

    assert embeddings.queries == ["hello"]
    assert len(store.upserts) == 1
    assert store.upserts[0]["user_id"] == "user-1"
    assert store.upserts[0]["session_id"] == "session-1"
    assert store.upserts[0]["message_id"] == "msg-1"
    assert store.upserts[0]["content"] == "hello"
    assert store.upserts[0]["vector"] == [0.1, 0.2, 0.3]


def test_index_user_message_propagates_embedding_outage_without_upsert() -> None:
    store = _FakeChatVectorStore()
    embeddings = _FailingEmbeddingClient(httpx.HTTPError("openai unavailable"))
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    with pytest.raises(httpx.HTTPError, match="openai unavailable"):
        service.index_user_message(
            user_id="user-1",
            session_id="session-1",
            message_id="msg-1",
            content="hello",
            created_at="2026-04-13T00:00:00+00:00",
        )

    assert embeddings.queries == ["hello"]
    assert store.upserts == []


def test_recall_uses_none_placeholders_in_query_when_optional_fields_missing() -> None:
    store = _FakeChatVectorStore()
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    service.recall(
        user_id="user-1",
        risk_profile="conservative",
        user_intent_text=None,
        latest_user_message=None,
        limit=5,
    )

    q = embeddings.queries[0]
    assert "user_intent=none" in q
    assert "latest_user_message=none" in q
    assert store.search_calls[0]["limit"] == 40


def test_recall_propagates_embedding_outage_without_search() -> None:
    store = _FakeChatVectorStore()
    embeddings = _FailingEmbeddingClient(httpx.HTTPError("openai unavailable"))
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    with pytest.raises(httpx.HTTPError, match="openai unavailable"):
        service.recall(
            user_id="user-1",
            risk_profile="balanced",
            user_intent_text="希望兼顾稳健和成长",
            latest_user_message="最近更关注科技成长",
            limit=10,
        )

    assert "risk_profile=balanced" in embeddings.queries[0]
    assert store.search_calls == []


def test_recall_propagates_qdrant_outage_after_embedding() -> None:
    store = _FailingSearchChatVectorStore(httpx.HTTPError("qdrant unavailable"))
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    with pytest.raises(httpx.HTTPError, match="qdrant unavailable"):
        service.recall(
            user_id="user-1",
            risk_profile="balanced",
            user_intent_text="希望兼顾稳健和成长",
            latest_user_message="最近更关注科技成长",
            limit=10,
        )

    assert "risk_profile=balanced" in embeddings.queries[0]
    assert store.search_calls == [
        {"user_id": "user-1", "query_vector": [0.1, 0.2, 0.3], "limit": 80}
    ]


def test_recall_reranks_by_semantic_score_tags_and_freshness() -> None:
    store = _FakeChatVectorStore()
    store.search_results = [
        {
            "content": "我更看重流动性",
            "content_fingerprint": "fp-1",
            "preference_tags": ["liquidity_high"],
            "topic_tags": ["wealth_management"],
            "symbol_mentions": [],
            "is_preference_memory": True,
            "information_density": 0.9,
            "created_at": "2026-04-15T00:00:00+00:00",
            "session_id": "old-1",
            "score": 0.74,
        },
        {
            "content": "最近市场挺热闹",
            "content_fingerprint": "fp-2",
            "preference_tags": [],
            "topic_tags": ["market_view"],
            "symbol_mentions": [],
            "is_preference_memory": False,
            "information_density": 0.2,
            "created_at": "2026-04-16T00:00:00+00:00",
            "session_id": "old-2",
            "score": 0.79,
        },
    ]
    embeddings = _FakeEmbeddingClient()
    service = ChatHistoryRecallService(
        embedding_client=embeddings,
        vector_store=store,
    )

    snippets = service.recall(
        user_id="user-1",
        risk_profile="unknown",
        user_intent_text="想要高流动性、稳健一点",
        latest_user_message="结合我的历史偏好继续分析",
        limit=3,
        recent_user_messages=["我更看重流动性", "我的持有期大概一年到两年"],
        active_session_id="session-active",
    )

    assert snippets[0] == "我更看重流动性"
    assert store.search_calls == [
        {
            "user_id": "user-1",
            "query_vector": [0.1, 0.2, 0.3],
            "limit": 24,
            "exclude_session_id": "session-active",
        }
    ]
    assert "recent_user_context=我更看重流动性 | 我的持有期大概一年到两年" in embeddings.queries[0]


def test_recall_drops_same_fingerprint_and_weak_candidates() -> None:
    store = _FakeChatVectorStore()
    store.search_results = [
        {
            "content": "我计划持有三到五年",
            "content_fingerprint": "fp-horizon",
            "preference_tags": ["horizon_medium"],
            "topic_tags": ["asset_allocation"],
            "symbol_mentions": [],
            "is_preference_memory": True,
            "information_density": 0.8,
            "created_at": "2026-04-10T00:00:00+00:00",
            "session_id": "old-1",
            "score": 0.72,
        },
        {
            "content": "三到五年是我能接受的持有期",
            "content_fingerprint": "fp-horizon",
            "preference_tags": ["horizon_medium"],
            "topic_tags": ["asset_allocation"],
            "symbol_mentions": [],
            "is_preference_memory": True,
            "information_density": 0.78,
            "created_at": "2026-04-11T00:00:00+00:00",
            "session_id": "old-2",
            "score": 0.71,
        },
        {
            "content": "好的",
            "content_fingerprint": "fp-weak",
            "preference_tags": [],
            "topic_tags": [],
            "symbol_mentions": [],
            "is_preference_memory": False,
            "information_density": 0.05,
            "created_at": "2025-01-01T00:00:00+00:00",
            "session_id": "old-3",
            "score": 0.76,
        },
    ]
    service = ChatHistoryRecallService(
        embedding_client=_FakeEmbeddingClient(),
        vector_store=store,
    )

    snippets = service.recall(
        user_id="user-1",
        risk_profile="unknown",
        user_intent_text="我可以接受三到五年持有期",
        latest_user_message="结合我的历史偏好继续分析",
        limit=3,
        recent_user_messages=["我可以接受三到五年持有期"],
        active_session_id="session-active",
    )

    assert snippets == ["我计划持有三到五年"]


def test_build_chat_history_recall_service_from_env_returns_none_when_incomplete() -> None:
    assert (
        build_chat_history_recall_service_from_env(
            env={
                "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY": "sk-test",
            }
        )
        is None
    )


def test_build_chat_history_recall_service_from_env_returns_service_when_complete() -> None:
    svc = build_chat_history_recall_service_from_env(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "http://127.0.0.1:6333",
            "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY": "sk-test",
        }
    )
    assert svc is not None
    assert isinstance(svc, ChatHistoryRecallService)
    assert svc._vector_store._collection_name == "chat_messages_v2"


def test_build_chat_history_recall_service_from_env_uses_global_base_url_fallback() -> None:
    svc = build_chat_history_recall_service_from_env(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "http://127.0.0.1:6333",
            "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY": "sk-test",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL": "https://openai-proxy.example.com/v1",
        }
    )

    assert svc is not None
    assert svc._embedding_client._base_url == "https://openai-proxy.example.com/v1"


def test_build_chat_history_recall_service_from_env_falls_back_to_product_knowledge_embedding() -> None:
    svc = build_chat_history_recall_service_from_env(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "http://127.0.0.1:6333",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY": "sk-prod",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL": "http://ollama:11434/v1",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL": "bge-m3",
        }
    )
    assert svc is not None
    assert svc._embedding_client._api_key == "sk-prod"
    assert svc._embedding_client._base_url == "http://ollama:11434/v1"
    assert svc._embedding_client._model_name == "bge-m3"


def test_build_chat_history_recall_service_from_env_prefers_product_base_url_over_llm_provider() -> None:
    svc = build_chat_history_recall_service_from_env(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "http://127.0.0.1:6333",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY": "sk-p",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL": "http://ollama/v1",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL": "https://remote.example/v1",
        }
    )
    assert svc is not None
    assert svc._embedding_client._base_url == "http://ollama/v1"


def test_qdrant_chat_message_store_search_posts_user_scoped_filter() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": {"points": []}}
    mock_response.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_response

    store = QdrantChatMessageStore(
        base_url="http://localhost:6333",
        collection_name="chat_messages",
        http_client=mock_client,
    )
    store.search(user_id="user-42", query_vector=[0.5], limit=7)

    mock_client.post.assert_called_once()
    url = mock_client.post.call_args[0][0]
    assert url.endswith("/collections/chat_messages/points/query")
    body = mock_client.post.call_args[1]["json"]
    assert body["query"] == [0.5]
    assert body["limit"] == 7
    assert body["with_payload"] is True
    assert body["filter"] == {
        "must": [{"key": "user_id", "match": {"value": "user-42"}}],
    }


def test_qdrant_chat_message_store_search_excludes_active_session_when_requested() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": {"points": []}}
    mock_response.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_response

    store = QdrantChatMessageStore(
        base_url="http://localhost:6333",
        collection_name="chat_messages_v2",
        http_client=mock_client,
    )
    store.search(
        user_id="user-42",
        query_vector=[0.5],
        limit=7,
        exclude_session_id="session-active",
    )

    body = mock_client.post.call_args[1]["json"]
    assert body["filter"] == {
        "must": [{"key": "user_id", "match": {"value": "user-42"}}],
        "must_not": [{"key": "session_id", "match": {"value": "session-active"}}],
    }


def test_qdrant_chat_message_store_upsert_put_includes_point_payload() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client.put.return_value = mock_response

    store = QdrantChatMessageStore(
        base_url="http://localhost:6333/",
        collection_name="chat_messages",
        http_client=mock_client,
    )
    store.upsert_user_message(
        user_id="u1",
        session_id="s1",
        message_id="mid-1",
        content="body",
        created_at="2026-04-13T00:00:00+00:00",
        vector=[0.1, 0.2],
        content_normalized="body",
        content_fingerprint="fp-body",
        preference_tags=[],
        topic_tags=[],
        symbol_mentions=[],
        is_preference_memory=False,
        information_density=0.5,
        recency_bucket="last_30d",
    )

    mock_client.put.assert_called_once()
    url = mock_client.put.call_args[0][0]
    assert "/collections/chat_messages/points" in url
    body = mock_client.put.call_args[1]["json"]
    assert "points" in body
    assert len(body["points"]) == 1
    point = body["points"][0]
    assert point["vector"] == [0.1, 0.2]
    assert point["payload"]["user_id"] == "u1"
    assert point["payload"]["session_id"] == "s1"
    assert point["payload"]["message_id"] == "mid-1"
    assert point["payload"]["role"] == "user"
    assert point["payload"]["content"] == "body"
    assert point["payload"]["content_normalized"] == "body"
    assert point["payload"]["content_fingerprint"] == "fp-body"


def test_qdrant_chat_message_store_upsert_put_includes_enriched_payload() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client.put.return_value = mock_response

    store = QdrantChatMessageStore(
        base_url="http://localhost:6333/",
        collection_name="chat_messages_v2",
        http_client=mock_client,
    )
    store.upsert_user_message(
        user_id="u1",
        session_id="s1",
        message_id="mid-1",
        content="我更看重流动性",
        created_at="2026-04-13T00:00:00+00:00",
        vector=[0.1, 0.2],
        content_normalized="我更看重流动性",
        content_fingerprint="fp-1",
        preference_tags=["liquidity_high"],
        topic_tags=["wealth_management"],
        symbol_mentions=[],
        is_preference_memory=True,
        information_density=0.8,
        recency_bucket="last_30d",
    )

    point = mock_client.put.call_args[1]["json"]["points"][0]
    assert point["payload"]["content_fingerprint"] == "fp-1"
    assert point["payload"]["preference_tags"] == ["liquidity_high"]
    assert point["payload"]["topic_tags"] == ["wealth_management"]
    assert point["payload"]["is_preference_memory"] is True
    assert point["payload"]["information_density"] == 0.8
    assert point["payload"]["recency_bucket"] == "last_30d"


def test_resolve_chat_recall_vector_size_uses_embedding_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from financehub_market_api.chat import qdrant_collection_bootstrap as bootstrap

    class _FakeEmbeddingClient:
        def embed_query(self, text: str) -> list[float]:
            assert "vector size probe" in text
            return [0.1] * 1024

    class _FakeRecallService:
        def __init__(self) -> None:
            self._embedding_client = _FakeEmbeddingClient()

    monkeypatch.setattr(
        bootstrap,
        "build_chat_history_recall_service_from_env",
        lambda *, env: _FakeRecallService(),
    )

    assert (
        bootstrap.resolve_chat_recall_vector_size(
            env={
                "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "https://qdrant.example.com",
                "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY": "sk-test",
            }
        )
        == 1024
    )


def test_ensure_chat_recall_qdrant_collection_reuses_existing_collection_when_vector_size_matches() -> (
    None
):
    from financehub_market_api.chat.qdrant_collection_bootstrap import (
        CHAT_RECALL_PAYLOAD_INDEX_SCHEMAS,
        ensure_chat_recall_qdrant_collection,
    )

    mock_client = MagicMock()

    create_response = MagicMock()
    create_response.is_success = False
    create_response.status_code = 409
    create_response.raise_for_status = MagicMock()

    get_response = MagicMock()
    get_response.raise_for_status = MagicMock()
    get_response.json.return_value = {
        "result": {
            "config": {
                "params": {
                    "vectors": {"size": 1024, "distance": "Cosine"},
                }
            }
        }
    }

    index_response = MagicMock()
    index_response.is_success = True
    index_response.status_code = 200
    index_response.raise_for_status = MagicMock()

    mock_client.put.side_effect = [create_response] + [
        index_response
    ] * len(CHAT_RECALL_PAYLOAD_INDEX_SCHEMAS)
    mock_client.get.return_value = get_response

    ensure_chat_recall_qdrant_collection(
        base_url="https://qdrant.example.com/",
        collection_name="chat_messages_v2",
        api_key="qdrant-test-key",
        vector_size=1024,
        http_client=mock_client,
    )

    mock_client.get.assert_called_once_with(
        "https://qdrant.example.com/collections/chat_messages_v2",
        headers={"content-type": "application/json", "api-key": "qdrant-test-key"},
        timeout=30.0,
    )
    assert mock_client.put.call_count == 1 + len(CHAT_RECALL_PAYLOAD_INDEX_SCHEMAS)


def test_ensure_chat_recall_qdrant_collection_raises_when_existing_vector_size_mismatches() -> (
    None
):
    from financehub_market_api.chat.qdrant_collection_bootstrap import (
        ensure_chat_recall_qdrant_collection,
    )

    mock_client = MagicMock()

    create_response = MagicMock()
    create_response.is_success = False
    create_response.status_code = 409
    create_response.raise_for_status = MagicMock()

    get_response = MagicMock()
    get_response.raise_for_status = MagicMock()
    get_response.json.return_value = {
        "result": {
            "config": {
                "params": {
                    "vectors": {"size": 1536, "distance": "Cosine"},
                }
            }
        }
    }

    mock_client.put.return_value = create_response
    mock_client.get.return_value = get_response

    with pytest.raises(RuntimeError, match="vector size mismatch"):
        ensure_chat_recall_qdrant_collection(
            base_url="https://qdrant.example.com/",
            collection_name="chat_messages_v2",
            vector_size=1024,
            http_client=mock_client,
        )


def test_seed_chat_messages_collection_creates_collection_and_payload_indexes() -> None:
    import scripts.seed_chat_messages_collection as seed_script

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_client.put.return_value = mock_response
    seed_script.resolve_chat_recall_vector_size = lambda *, env: 1024

    seed_script.main(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "https://qdrant.example.com/",
            "FINANCEHUB_CHAT_RECALL_COLLECTION": "chat_messages_v2",
            "FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY": "qdrant-test-key",
        },
        http_client=mock_client,
    )

    assert mock_client.put.call_count == 10

    create_call = mock_client.put.call_args_list[0]
    assert create_call.args[0] == "https://qdrant.example.com/collections/chat_messages_v2"
    assert create_call.kwargs["headers"] == {
        "content-type": "application/json",
        "api-key": "qdrant-test-key",
    }
    assert create_call.kwargs["json"] == {
        "vectors": {"size": 1024, "distance": "Cosine"},
    }
    assert create_call.kwargs["timeout"] == 30.0

    index_calls = mock_client.put.call_args_list[1:]
    assert [
        (call.args[0], call.kwargs["json"], call.kwargs["timeout"])
        for call in index_calls
    ] == [
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "user_id", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "session_id", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "created_at", "field_schema": "datetime"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "is_preference_memory", "field_schema": "bool"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "recency_bucket", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "preference_tags", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "topic_tags", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "symbol_mentions", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages_v2/index",
            {"field_name": "content_fingerprint", "field_schema": "keyword"},
            30.0,
        ),
    ]


def test_seed_chat_messages_collection_reads_backend_env_files_when_env_is_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.seed_chat_messages_collection as seed_script

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client.put.return_value = mock_response
    monkeypatch.setattr(
        seed_script,
        "build_env_values",
        lambda: {
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "https://qdrant.from-file",
            "FINANCEHUB_CHAT_RECALL_COLLECTION": "chat_messages_file",
        },
    )

    seed_script.main(http_client=mock_client)

    assert mock_client.put.call_args_list[0].args[0] == (
        "https://qdrant.from-file/collections/chat_messages_file"
    )


@pytest.mark.parametrize(
    "env_key_to_drop",
    [
        "FINANCEHUB_CHAT_RECALL_QDRANT_URL",
        "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY",
    ],
)
def test_build_from_env_requires_only_url_and_api_key(env_key_to_drop: str) -> None:
    full = {
        "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "http://127.0.0.1:6333",
        "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY": "sk-test",
    }
    env = {k: v for k, v in full.items() if k != env_key_to_drop}
    assert build_chat_history_recall_service_from_env(env=env) is None


def test_rebuild_chat_recall_index_reads_user_messages_and_upserts_enriched_payload() -> None:
    from scripts.rebuild_chat_recall_index import rebuild_chat_recall_index

    class _FakeRedis:
        def scan_iter(self, pattern: str):
            if pattern == "financehub:chat:session:*":
                return iter([b"financehub:chat:session:session-1"])
            raise AssertionError(pattern)

        def hgetall(self, key: bytes | str) -> dict[bytes, bytes]:
            if key == b"financehub:chat:session:session-1" or key == "financehub:chat:session:session-1":
                return {b"user_id": b"user-1"}
            return {}

        def lrange(self, key: bytes | str, start: int, stop: int) -> list[bytes]:
            assert start == 0
            assert stop == -1
            if key == b"financehub:chat:messages:session-1" or key == "financehub:chat:messages:session-1":
                return [
                    b'{"id":"msg-user","role":"user","content":"\xe6\x88\x91\xe6\x9b\xb4\xe7\x9c\x8b\xe9\x87\x8d\xe6\xb5\x81\xe5\x8a\xa8\xe6\x80\xa7","created_at":"2026-04-16T08:00:00+00:00"}',
                    b'{"id":"msg-assistant","role":"assistant","content":"\xe5\xa5\xbd\xe7\x9a\x84","created_at":"2026-04-16T08:01:00+00:00"}',
                ]
            return []

    class _FakeRecallService:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def index_user_message(
            self,
            *,
            user_id: str,
            session_id: str,
            message_id: str,
            content: str,
            created_at: str,
        ) -> None:
            self.calls.append(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "message_id": message_id,
                    "content": content,
                    "created_at": created_at,
                }
            )

    recall_service = _FakeRecallService()

    indexed_count = rebuild_chat_recall_index(
        redis_client=_FakeRedis(),
        recall_service=recall_service,
    )

    assert indexed_count == 1
    assert recall_service.calls == [
        {
            "user_id": "user-1",
            "session_id": "session-1",
            "message_id": "msg-user",
            "content": "我更看重流动性",
            "created_at": "2026-04-16T08:00:00+00:00",
        }
    ]
