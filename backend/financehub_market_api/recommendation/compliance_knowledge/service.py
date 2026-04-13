from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import os
from pathlib import Path

from financehub_market_api.recommendation.compliance_knowledge.qdrant_store import (
    ComplianceKnowledgeStore,
    QdrantComplianceKnowledgeStore,
)
from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceEvidenceBundle,
    ComplianceKnowledgeQuery,
    RetrievedComplianceEvidence,
)
from financehub_market_api.recommendation.product_knowledge.embedding_client import (
    OpenAIEmbeddingClient,
    TextEmbeddingClient,
)


class ComplianceKnowledgeRetrievalService:
    def __init__(
        self,
        *,
        embedding_client: TextEmbeddingClient,
        knowledge_store: ComplianceKnowledgeStore,
    ) -> None:
        self._embedding_client = embedding_client
        self._knowledge_store = knowledge_store

    def retrieve_evidence(
        self,
        query: ComplianceKnowledgeQuery,
        *,
        total_limit: int = 12,
    ) -> list[ComplianceEvidenceBundle]:
        if not query.query_text.strip() or not query.rule_types:
            return []

        query_vector = self._embedding_client.embed_query(query.query_text)
        hits = self._knowledge_store.search(
            query_vector=query_vector,
            query=query,
            total_limit=total_limit,
        )
        grouped: dict[str, list[RetrievedComplianceEvidence]] = defaultdict(list)
        for hit in hits:
            evidence = RetrievedComplianceEvidence.model_validate(hit)
            grouped[evidence.rule_type].append(evidence)
        return [
            ComplianceEvidenceBundle(rule_type=rule_type, evidences=evidences)
            for rule_type, evidences in grouped.items()
        ]


def build_compliance_knowledge_retrieval_service_from_env(
    *,
    env: Mapping[str, str] | None = None,
) -> ComplianceKnowledgeRetrievalService | None:
    config = env if env is not None else _build_env_values()

    qdrant_url = _read_env(config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL")
    qdrant_collection = _read_env(
        config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION"
    )
    openai_api_key = _read_env(
        config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY"
    ) or _read_env(config, "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")

    if not qdrant_url or not qdrant_collection or not openai_api_key:
        return None

    openai_base_url = _read_env(
        config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_BASE_URL"
    )
    embedding_model = _read_env(
        config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL"
    )
    qdrant_api_key = _read_env(config, "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_API_KEY")

    embedding_client_kwargs: dict[str, str] = {"api_key": openai_api_key}
    if openai_base_url:
        embedding_client_kwargs["base_url"] = openai_base_url
    if embedding_model:
        embedding_client_kwargs["model_name"] = embedding_model

    return ComplianceKnowledgeRetrievalService(
        embedding_client=OpenAIEmbeddingClient(**embedding_client_kwargs),
        knowledge_store=QdrantComplianceKnowledgeStore(
            base_url=qdrant_url,
            collection_name=qdrant_collection,
            api_key=qdrant_api_key,
        ),
    )


def _read_env(env: Mapping[str, str], key: str) -> str | None:
    raw_value = env.get(key)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value if value else None


def _iter_env_file_candidates() -> list[Path]:
    search_roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[4],
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in search_roots:
        for filename in (".env.local", ".env"):
            candidate = root / filename
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip("\"'")
    return values


def _build_env_values(
    environ: Mapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for env_file in env_files if env_files is not None else _iter_env_file_candidates():
        values.update(_parse_env_file(env_file))
    values.update(dict(os.environ if environ is None else environ))
    return values
