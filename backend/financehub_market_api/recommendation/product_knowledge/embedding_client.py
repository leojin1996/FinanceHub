from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse

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
        self._http_client = http_client
        self._timeout_seconds = timeout_seconds

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("query text must not be empty")

        response = self._get_http_client().post(
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

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            client_kwargs: dict[str, bool] = {}
            if _is_loopback_base_url(self._base_url):
                client_kwargs["trust_env"] = False
            self._http_client = httpx.Client(**client_kwargs)
        return self._http_client


def _is_loopback_base_url(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}
