from __future__ import annotations

from typing import Protocol

import httpx


class ProductKnowledgeStore(Protocol):
    def search(
        self,
        *,
        query_vector: list[float],
        product_ids: list[str],
        include_internal: bool,
        limit_per_product: int,
        total_limit: int,
    ) -> list[dict[str, object]]:
        """Return ranked product-knowledge hits."""


class QdrantProductKnowledgeStore:
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
        self._http_client = http_client or httpx.Client()
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        *,
        query_vector: list[float],
        product_ids: list[str],
        include_internal: bool,
        limit_per_product: int,
        total_limit: int,
    ) -> list[dict[str, object]]:
        if not product_ids or total_limit <= 0 or limit_per_product <= 0:
            return []
        ranked_hits: list[tuple[float, dict[str, object]]] = []
        for product_id in product_ids:
            response = self._http_client.post(
                f"{self._base_url}/collections/{self._collection_name}/points/query",
                headers=self._headers(),
                json={
                    "query": query_vector,
                    "limit": limit_per_product,
                    "with_payload": True,
                    "filter": self._build_filter(
                        product_id=product_id,
                        include_internal=include_internal,
                    ),
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()

            points = self._extract_points(payload)
            product_hits = 0
            for point in points:
                if not isinstance(point, dict):
                    continue
                doc_payload = point.get("payload")
                if not isinstance(doc_payload, dict):
                    continue
                payload_product_id = doc_payload.get("product_id")
                if not isinstance(payload_product_id, str):
                    continue
                if payload_product_id != product_id:
                    continue

                hit = dict(doc_payload)
                score = point.get("score")
                hit_score = float(score) if isinstance(score, int | float) else float("-inf")
                if isinstance(score, int | float):
                    hit["score"] = hit_score
                ranked_hits.append((hit_score, hit))
                product_hits += 1
                if product_hits >= limit_per_product:
                    break

        ranked_hits.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in ranked_hits[:total_limit]]

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    def _build_filter(
        self,
        *,
        product_id: str,
        include_internal: bool,
    ) -> dict[str, object]:
        must_filters: list[dict[str, object]] = [
            {
                "key": "product_id",
                "match": {
                    "value": product_id,
                },
            }
        ]
        if not include_internal:
            must_filters.append(
                {
                    "key": "visibility",
                    "match": {
                        "value": "public",
                    },
                }
            )
        return {"must": must_filters}

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
