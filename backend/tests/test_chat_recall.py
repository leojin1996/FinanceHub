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
    ) -> None:
        self.upserts.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "message_id": message_id,
                "content": content,
                "created_at": created_at,
                "vector": vector,
            }
        )

    def search(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, object]]:
        self.search_calls.append(
            {"user_id": user_id, "query_vector": query_vector, "limit": limit}
        )
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
    ) -> list[dict[str, object]]:
        self.search_calls.append(
            {"user_id": user_id, "query_vector": query_vector, "limit": limit}
        )
        raise self._exc


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
        {"user_id": "user-1", "query_vector": [0.1, 0.2, 0.3], "limit": 10}
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
    assert store.search_calls[0]["limit"] == 5


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
        {"user_id": "user-1", "query_vector": [0.1, 0.2, 0.3], "limit": 10}
    ]


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
    assert svc._vector_store._collection_name == "chat_messages"


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


def test_seed_chat_messages_collection_creates_collection_and_payload_indexes() -> None:
    from scripts.seed_chat_messages_collection import main

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client.put.return_value = mock_response

    main(
        env={
            "FINANCEHUB_CHAT_RECALL_QDRANT_URL": "https://qdrant.example.com/",
            "FINANCEHUB_CHAT_RECALL_COLLECTION": "chat_messages",
            "FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY": "qdrant-test-key",
        },
        http_client=mock_client,
    )

    assert mock_client.put.call_count == 4

    create_call = mock_client.put.call_args_list[0]
    assert create_call.args[0] == "https://qdrant.example.com/collections/chat_messages"
    assert create_call.kwargs["headers"] == {
        "content-type": "application/json",
        "api-key": "qdrant-test-key",
    }
    assert create_call.kwargs["json"] == {
        "vectors": {"size": 1536, "distance": "Cosine"},
    }
    assert create_call.kwargs["timeout"] == 30.0

    index_calls = mock_client.put.call_args_list[1:]
    assert [
        (call.args[0], call.kwargs["json"], call.kwargs["timeout"])
        for call in index_calls
    ] == [
        (
            "https://qdrant.example.com/collections/chat_messages/index",
            {"field_name": "user_id", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages/index",
            {"field_name": "session_id", "field_schema": "keyword"},
            30.0,
        ),
        (
            "https://qdrant.example.com/collections/chat_messages/index",
            {"field_name": "created_at", "field_schema": "datetime"},
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
