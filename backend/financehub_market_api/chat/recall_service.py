from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from financehub_market_api.env import (
    build_env_values as _build_shared_env_values,
    iter_env_file_candidates as _iter_shared_env_file_candidates,
    parse_env_file as _parse_shared_env_file,
    read_env as _read_env,
)
from financehub_market_api.chat.metadata import build_chat_message_metadata
from financehub_market_api.chat.metadata import (
    bucketize_recency,
    build_recall_query_context,
    extract_preference_tags,
    extract_symbol_mentions,
    extract_topic_tags,
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
        metadata = build_chat_message_metadata(content=content, created_at=created_at)
        self._vector_store.upsert_user_message(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            content=content,
            created_at=created_at,
            vector=vector,
            content_normalized=metadata.content_normalized,
            content_fingerprint=metadata.content_fingerprint,
            preference_tags=list(metadata.preference_tags),
            topic_tags=list(metadata.topic_tags),
            symbol_mentions=list(metadata.symbol_mentions),
            is_preference_memory=metadata.is_preference_memory,
            information_density=metadata.information_density,
            recency_bucket=metadata.recency_bucket,
        )

    def recall(
        self,
        *,
        user_id: str,
        risk_profile: str,
        user_intent_text: str | None,
        latest_user_message: str | None,
        limit: int = 10,
        recent_user_messages: Sequence[str] = (),
        active_session_id: str | None = None,
    ) -> list[str]:
        query_context = build_recall_query_context(
            current_user_message=latest_user_message or "",
            recent_user_messages=recent_user_messages,
        )
        desired_preference_tags = tuple(
            dict.fromkeys(
                [
                    *query_context.preference_tags,
                    *extract_preference_tags(user_intent_text or ""),
                ]
            )
        )
        desired_topic_tags = tuple(
            dict.fromkeys(
                [
                    *query_context.topic_tags,
                    *extract_topic_tags(user_intent_text or ""),
                ]
            )
        )
        desired_symbol_mentions = tuple(
            dict.fromkeys(
                [
                    *query_context.symbol_mentions,
                    *extract_symbol_mentions(user_intent_text or ""),
                ]
            )
        )
        query_text = "\n".join(
            [
                f"risk_profile={risk_profile}",
                f"user_intent={user_intent_text or 'none'}",
                f"latest_user_message={latest_user_message or 'none'}",
                query_context.embedding_text,
            ]
        )
        query_vector = self._embedding_client.embed_query(query_text)
        hits = self._vector_store.search(
            user_id=user_id,
            query_vector=query_vector,
            limit=max(limit * 8, 20),
            exclude_session_id=active_session_id,
        )
        ranked_hits = self._rerank_hits(
            hits,
            desired_preference_tags=desired_preference_tags,
            desired_topic_tags=desired_topic_tags,
            desired_symbol_mentions=desired_symbol_mentions,
        )
        return self._select_snippets(ranked_hits, limit=min(limit, 3))

    def _rerank_hits(
        self,
        hits: Sequence[dict[str, object]],
        *,
        desired_preference_tags: Sequence[str],
        desired_topic_tags: Sequence[str],
        desired_symbol_mentions: Sequence[str],
    ) -> list[dict[str, object]]:
        ranked_hits: list[dict[str, object]] = []
        for hit in hits:
            reranked = dict(hit)
            reranked["rerank_score"] = self._score_hit(
                reranked,
                desired_preference_tags=desired_preference_tags,
                desired_topic_tags=desired_topic_tags,
                desired_symbol_mentions=desired_symbol_mentions,
            )
            ranked_hits.append(reranked)
        ranked_hits.sort(
            key=lambda hit: (
                float(hit.get("rerank_score", 0.0)),
                float(hit.get("score", 0.0)),
            ),
            reverse=True,
        )
        return ranked_hits

    def _score_hit(
        self,
        hit: Mapping[str, object],
        *,
        desired_preference_tags: Sequence[str],
        desired_topic_tags: Sequence[str],
        desired_symbol_mentions: Sequence[str],
    ) -> float:
        score = float(hit.get("score", 0.0))
        preference_overlap = len(
            set(_string_list(hit.get("preference_tags"))) & set(desired_preference_tags)
        )
        topic_overlap = len(set(_string_list(hit.get("topic_tags"))) & set(desired_topic_tags))
        symbol_overlap = len(
            set(_string_list(hit.get("symbol_mentions"))) & set(desired_symbol_mentions)
        )
        score += preference_overlap * 0.25
        score += topic_overlap * 0.08
        score += symbol_overlap * 0.12
        if hit.get("is_preference_memory") is True:
            score += 0.18
        information_density_raw = hit.get("information_density")
        information_density = _float_value(hit.get("information_density"))
        if information_density_raw is None:
            score += 0.05
        else:
            score += min(max(information_density, 0.0), 1.0) * 0.15
        if information_density_raw is not None and information_density < 0.15:
            score -= 0.45
        score += self._freshness_bonus(hit.get("created_at"), hit.get("recency_bucket"))
        return score

    def _select_snippets(
        self,
        ranked_hits: Sequence[dict[str, object]],
        *,
        limit: int,
    ) -> list[str]:
        snippets: list[str] = []
        seen_fingerprints: set[str] = set()
        seen_contents: set[str] = set()
        for hit in ranked_hits:
            rerank_score = _float_value(hit.get("rerank_score"))
            if rerank_score < 0.7:
                continue
            content = hit.get("content")
            if not isinstance(content, str):
                continue
            normalized = content.strip()
            if not normalized:
                continue
            fingerprint = hit.get("content_fingerprint")
            if isinstance(fingerprint, str) and fingerprint in seen_fingerprints:
                continue
            if normalized in seen_contents:
                continue
            if isinstance(fingerprint, str):
                seen_fingerprints.add(fingerprint)
            seen_contents.add(normalized)
            snippets.append(normalized)
            if len(snippets) >= limit:
                break
        return snippets

    def _freshness_bonus(
        self,
        created_at: object,
        recency_bucket: object,
    ) -> float:
        if isinstance(recency_bucket, str) and recency_bucket:
            bucket = recency_bucket
        elif isinstance(created_at, str) and created_at.strip():
            bucket = bucketize_recency(created_at)
        else:
            return 0.0
        if bucket == "last_30d":
            return 0.08
        if bucket == "last_90d":
            return 0.04
        if bucket == "last_365d":
            return -0.02
        return -0.12


def build_chat_history_recall_service_from_env(
    *,
    env: Mapping[str, str] | None = None,
) -> ChatHistoryRecallService | None:
    config = env if env is not None else _build_env_values()
    qdrant_url = _read_env(config, "FINANCEHUB_CHAT_RECALL_QDRANT_URL")
    qdrant_collection = _read_env(
        config, "FINANCEHUB_CHAT_RECALL_COLLECTION"
    ) or "chat_messages_v2"
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0
