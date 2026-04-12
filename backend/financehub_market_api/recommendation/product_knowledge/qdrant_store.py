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
        del limit_per_product
        if not product_ids:
            return []

        response = self._http_client.post(
            f"{self._base_url}/collections/{self._collection_name}/points/query",
            headers=self._headers(),
            json={
                "query": query_vector,
                "limit": total_limit,
                "with_payload": True,
                "filter": self._build_filter(
                    product_ids=product_ids,
                    include_internal=include_internal,
                ),
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
            product_id = doc_payload.get("product_id")
            if not isinstance(product_id, str):
                continue
            if product_id not in product_ids:
                continue
            hit = dict(doc_payload)
            score = point.get("score")
            if isinstance(score, int | float):
                hit["score"] = float(score)
            hits.append(hit)

        return hits

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    def _build_filter(
        self,
        *,
        product_ids: list[str],
        include_internal: bool,
    ) -> dict[str, object]:
        must_filters: list[dict[str, object]] = [
            {
                "key": "product_id",
                "match": {
                    "any": product_ids,
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
        return []
