from __future__ import annotations

from typing import Protocol

import httpx


class TextEmbeddingClient(Protocol):
    def embed_query(self, text: str) -> list[float]:
        """Return embedding vector for retrieval query text."""


class OpenAIEmbeddingClient:
    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model_name: str = DEFAULT_MODEL,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._http_client = http_client or httpx.Client()
        self._timeout_seconds = timeout_seconds

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("query text must not be empty")

        response = self._http_client.post(
            f"{self._base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self._model_name,
                "input": text,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()

        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("embedding response missing data")

        first_item = data[0]
        if not isinstance(first_item, dict):
            raise ValueError("embedding response item must be an object")

        embedding = first_item.get("embedding")
        if not isinstance(embedding, list):
            raise ValueError("embedding response missing vector")

        return [float(value) for value in embedding]
