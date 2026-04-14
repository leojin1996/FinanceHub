from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from financehub_market_api.env import (
    build_env_values as _build_shared_env_values,
    iter_env_file_candidates as _iter_shared_env_file_candidates,
    parse_env_file as _parse_shared_env_file,
    read_env as _read_env,
)
from financehub_market_api.chat.qdrant_store import (
    ChatMessageVectorStore,
    QdrantChatMessageStore,
)
from financehub_market_api.recommendation.product_knowledge.embedding_client import (
    OpenAIEmbeddingClient,
    TextEmbeddingClient,
)


class ChatHistoryRecallService:
    def __init__(
        self,
        *,
        embedding_client: TextEmbeddingClient,
        vector_store: ChatMessageVectorStore,
    ) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store

    def index_user_message(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        content: str,
        created_at: str,
    ) -> None:
        if not content.strip():
            return
        vector = self._embedding_client.embed_query(content)
        self._vector_store.upsert_user_message(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            content=content,
            created_at=created_at,
            vector=vector,
        )

    def recall(
        self,
        *,
        user_id: str,
        risk_profile: str,
        user_intent_text: str | None,
        latest_user_message: str | None,
        limit: int = 10,
    ) -> list[str]:
        query_text = "\n".join(
            [
                f"risk_profile={risk_profile}",
                f"user_intent={user_intent_text or 'none'}",
                f"latest_user_message={latest_user_message or 'none'}",
            ]
        )
        query_vector = self._embedding_client.embed_query(query_text)
        hits = self._vector_store.search(
            user_id=user_id,
            query_vector=query_vector,
            limit=limit,
        )
        snippets: list[str] = []
        seen: set[str] = set()
        for hit in hits:
            content = hit.get("content")
            if not isinstance(content, str):
                continue
            normalized = content.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            snippets.append(normalized)
        return snippets


def build_chat_history_recall_service_from_env(
    *,
    env: Mapping[str, str] | None = None,
) -> ChatHistoryRecallService | None:
    config = env if env is not None else _build_env_values()
    qdrant_url = _read_env(config, "FINANCEHUB_CHAT_RECALL_QDRANT_URL")
    qdrant_collection = _read_env(
        config, "FINANCEHUB_CHAT_RECALL_COLLECTION"
    ) or "chat_messages"
    # Embedding stack: same resolution pattern as product_knowledge / compliance_knowledge
    # (local Ollama + bge-m3 via *_OPENAI_* / *_EMBEDDING_MODEL*), then chat LLM gateway.
    openai_api_key = (
        _read_env(config, "FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY")
        or _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY")
        or _read_env(config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY")
        or _read_env(config, "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")
    )
    if not qdrant_url or not openai_api_key:
        return None
    openai_base_url = (
        _read_env(config, "FINANCEHUB_CHAT_RECALL_OPENAI_BASE_URL")
        or _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL")
        or _read_env(config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_BASE_URL")
        or _read_env(config, "FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL")
    )
    embedding_model = (
        _read_env(config, "FINANCEHUB_CHAT_RECALL_EMBEDDING_MODEL")
        or _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL")
        or _read_env(config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL")
    )
    qdrant_api_key = _read_env(config, "FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY")
    embedding_kwargs: dict[str, str] = {"api_key": openai_api_key}
    if openai_base_url:
        embedding_kwargs["base_url"] = openai_base_url
    if embedding_model:
        embedding_kwargs["model_name"] = embedding_model
    return ChatHistoryRecallService(
        embedding_client=OpenAIEmbeddingClient(**embedding_kwargs),
        vector_store=QdrantChatMessageStore(
            base_url=qdrant_url,
            collection_name=qdrant_collection,
            api_key=qdrant_api_key,
        ),
    )


def _iter_env_file_candidates() -> list[Path]:
    return _iter_shared_env_file_candidates()


def _parse_env_file(env_file: Path) -> dict[str, str]:
    return _parse_shared_env_file(env_file)


def _build_env_values(
    environ: Mapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    return _build_shared_env_values(
        environ=environ,
        env_files=env_files if env_files is not None else _iter_env_file_candidates(),
    )
