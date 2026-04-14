from __future__ import annotations

from typing import Protocol

import httpx

from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceKnowledgeQuery,
)


class ComplianceKnowledgeStore(Protocol):
    def search(
        self,
        *,
        query_vector: list[float],
        query: ComplianceKnowledgeQuery,
        total_limit: int,
    ) -> list[dict[str, object]]:
        """Return ranked compliance-knowledge hits."""


class QdrantComplianceKnowledgeStore:
    def __init__(
        self,
        *,
        base_url: str,
        collection_name: str,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._collection_name = collection_name
        self._api_key = api_key
        self._http_client = http_client
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        *,
        query_vector: list[float],
        query: ComplianceKnowledgeQuery,
        total_limit: int,
    ) -> list[dict[str, object]]:
        if total_limit <= 0 or not query.rule_types:
            return []

        response = self._get_http_client().post(
            f"{self._base_url}/collections/{self._collection_name}/points/query",
            headers=self._headers(),
            json={
                "query": query_vector,
                "limit": total_limit,
                "with_payload": True,
                "filter": self._build_filter(query),
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        points = self._extract_points(payload)
        hits: list[dict[str, object]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            doc_payload = point.get("payload")
            if not isinstance(doc_payload, dict):
                continue
            hit = dict(doc_payload)
            score = point.get("score")
            if isinstance(score, int | float):
                hit["score"] = float(score)
            hits.append(hit)
        return hits

    def _build_filter(self, query: ComplianceKnowledgeQuery) -> dict[str, object]:
        must_filters: list[dict[str, object]] = [
            {"key": "jurisdiction", "match": {"value": query.jurisdiction}},
        ]
        if query.audience:
            must_filters.append({"key": "audience", "match": {"value": query.audience}})
        if query.effective_on:
            must_filters.append(
                {"key": "effective_date", "range": {"lte": query.effective_on}}
            )
        should_filters: list[dict[str, object]] = [
            {"key": "rule_type", "match": {"value": rule_type}}
            for rule_type in query.rule_types
        ]
        should_filters.extend(
            {"key": "applies_to_categories", "match": {"value": category}}
            for category in query.categories
        )
        return {"must": must_filters, "should": should_filters}

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    def _extract_points(self, payload: object) -> list[object]:
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                points = result.get("points")
                if isinstance(points, list):
                    return points
        raise ValueError("malformed qdrant query response: missing result points list")

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client()
        return self._http_client
