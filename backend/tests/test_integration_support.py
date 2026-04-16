from __future__ import annotations

from typing import Any

import integration_support


class _FakeTestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> str:
        self.calls.append((method, url, kwargs))
        return "ok"


def test_request_via_testclient_strips_timeout_kwarg() -> None:
    client = _FakeTestClient()

    response = integration_support.request_via_testclient(
        client,
        "POST",
        "/api/recommendations/generate",
        json={"hello": "world"},
        headers={"Authorization": "Bearer test-token"},
        timeout=600.0,
    )

    assert response == "ok"
    assert client.calls == [
        (
            "POST",
            "/api/recommendations/generate",
            {
                "json": {"hello": "world"},
                "headers": {"Authorization": "Bearer test-token"},
            },
        )
    ]
