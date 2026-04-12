import pytest

import financehub_market_api.recommendation.product_knowledge.embedding_client as embedding_client_module
from financehub_market_api.recommendation.product_knowledge.embedding_client import OpenAIEmbeddingClient


class _FakeResponse:
    def __init__(self, payload: object, *, json_error: Exception | None = None) -> None:
        self._payload = payload
        self._json_error = json_error

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeHttpClient:
    def __init__(
        self,
        payload: object,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._json_error = json_error
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self._payload, json_error=self._json_error)


def test_embed_query_posts_to_openai_embeddings_endpoint() -> None:
    http_client = _FakeHttpClient(
        {
            "data": [
                {
                    "embedding": [0.11, 0.22, 0.33],
                }
            ]
        }
    )
    client = OpenAIEmbeddingClient(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        http_client=http_client,
    )

    vector = client.embed_query("steady income")

    assert vector == [0.11, 0.22, 0.33]
    assert len(http_client.calls) == 1
    assert http_client.calls[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert http_client.calls[0]["json"] == {
        "model": "text-embedding-3-small",
        "input": "steady income",
    }


def test_embed_query_raises_value_error_when_response_json_is_malformed() -> None:
    client = OpenAIEmbeddingClient(
        api_key="test-key",
        http_client=_FakeHttpClient({}, json_error=ValueError("invalid json body")),
    )

    with pytest.raises(ValueError, match="invalid json body"):
        client.embed_query("steady income")


def test_embed_query_raises_for_missing_data_shape() -> None:
    client = OpenAIEmbeddingClient(
        api_key="test-key",
        http_client=_FakeHttpClient({"data": {"embedding": [0.1]}}),
    )

    with pytest.raises(ValueError, match="embedding response missing data"):
        client.embed_query("steady income")


def test_openai_embedding_client_does_not_create_default_http_client_eagerly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_client_creation() -> object:
        raise AssertionError("httpx.Client should not be created at __init__ time")

    monkeypatch.setattr(embedding_client_module.httpx, "Client", _unexpected_client_creation)

    client = OpenAIEmbeddingClient(api_key="test-key")

    assert client is not None


def test_openai_embedding_client_disables_env_proxy_for_localhost_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    def _build_client(*args: object, **kwargs: object) -> _FakeHttpClient:
        del args
        captured_kwargs.update(kwargs)
        return _FakeHttpClient({"data": [{"embedding": [0.11, 0.22, 0.33]}]})

    monkeypatch.setattr(embedding_client_module.httpx, "Client", _build_client)

    client = OpenAIEmbeddingClient(
        api_key="ollama",
        base_url="http://127.0.0.1:11434/v1",
    )

    vector = client.embed_query("steady income")

    assert vector == [0.11, 0.22, 0.33]
    assert captured_kwargs == {"trust_env": False}
