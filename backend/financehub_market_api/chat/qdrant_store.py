from __future__ import annotations

from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import httpx


class ChatMessageVectorStore(Protocol):
    def upsert_user_message(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        content: str,
        created_at: str,
        vector: list[float],
    ) -> None: ...

    def search(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, object]]: ...


class QdrantChatMessageStore:
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
        point_id = str(uuid5(NAMESPACE_URL, f"chat-message:{message_id}"))
        self._client().put(
            f"{self._base_url}/collections/{self._collection_name}/points",
            headers=self._headers(),
            json={
                "points": [
                    {
                        "id": point_id,
                        "vector": vector,
                        "payload": {
                            "user_id": user_id,
                            "session_id": session_id,
                            "message_id": message_id,
                            "role": "user",
                            "content": content,
                            "created_at": created_at,
                        },
                    }
                ]
            },
            timeout=self._timeout_seconds,
        ).raise_for_status()

    def search(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, object]]:
        response = self._client().post(
            f"{self._base_url}/collections/{self._collection_name}/points/query",
            headers=self._headers(),
            json={
                "query": query_vector,
                "limit": limit,
                "with_payload": True,
                "filter": {
                    "must": [{"key": "user_id", "match": {"value": user_id}}],
                },
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        points = _extract_points(body)
        results: list[dict[str, object]] = []
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
            results.append(hit)
        return results

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client()
        return self._http_client

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers


def _extract_points(payload: object) -> list[object]:
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            points = result.get("points")
            if isinstance(points, list):
                return points
    raise ValueError("malformed qdrant query response: missing result points list")
