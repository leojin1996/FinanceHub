import pytest

from financehub_market_api.upstreams.dolthub import DoltHubClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self.calls: list[dict] = []

    def get(self, url: str, params: dict[str, str], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self._payloads.pop(0))


def test_fetch_watchlist_prices_queries_latest_and_previous_trade_dates() -> None:
    client = FakeHttpClient(
        [
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-04-01"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-03-31"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {
                        "tradedate": "2026-04-01",
                        "symbol": "SZ300750",
                        "close": "188.55",
                        "volume": "123456789",
                        "amount": "2345678901",
                    },
                    {
                        "tradedate": "2026-03-31",
                        "symbol": "SZ300750",
                        "close": "177.54",
                    },
                    {
                        "tradedate": "2026-04-01",
                        "symbol": "SZ002594",
                        "close": "221.88",
                        "volume": "987654321",
                        "amount": "3456789012",
                    },
                    {
                        "tradedate": "2026-03-31",
                        "symbol": "SZ002594",
                        "close": "211.72",
                    },
                ]
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-04-01"},
                    {"tradedate": "2026-03-31"},
                    {"tradedate": "2026-03-28"},
                    {"tradedate": "2026-03-27"},
                    {"tradedate": "2026-03-26"},
                    {"tradedate": "2026-03-25"},
                    {"tradedate": "2026-03-24"},
                ],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-03-24", "symbol": "SZ300750", "close": "176.00"},
                    {"tradedate": "2026-03-25", "symbol": "SZ300750", "close": "177.10"},
                    {"tradedate": "2026-03-26", "symbol": "SZ300750", "close": "178.40"},
                    {"tradedate": "2026-03-27", "symbol": "SZ300750", "close": "179.00"},
                    {"tradedate": "2026-03-28", "symbol": "SZ300750", "close": "180.50"},
                    {"tradedate": "2026-03-31", "symbol": "SZ300750", "close": "177.54"},
                    {"tradedate": "2026-04-01", "symbol": "SZ300750", "close": "188.55"},
                    {"tradedate": "2026-03-24", "symbol": "SZ002594", "close": "205.00"},
                    {"tradedate": "2026-03-25", "symbol": "SZ002594", "close": "206.50"},
                    {"tradedate": "2026-03-26", "symbol": "SZ002594", "close": "208.20"},
                    {"tradedate": "2026-03-27", "symbol": "SZ002594", "close": "209.10"},
                    {"tradedate": "2026-03-28", "symbol": "SZ002594", "close": "210.40"},
                    {"tradedate": "2026-03-31", "symbol": "SZ002594", "close": "211.72"},
                    {"tradedate": "2026-04-01", "symbol": "SZ002594", "close": "221.88"},
                ]
            },
        ]
    )

    adapter = DoltHubClient(http_client=client)
    snapshot = adapter.fetch_watchlist_prices(["SZ300750", "SZ002594"])

    assert snapshot.as_of_date == "2026-04-01"
    assert snapshot.latest_prices == {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
    }
    assert snapshot.previous_prices == {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
    }
    assert snapshot.latest_volumes == {
        "SZ300750": 123456789.0,
        "SZ002594": 987654321.0,
    }
    assert snapshot.latest_amounts == {
        "SZ300750": 2345678901.0,
        "SZ002594": 3456789012.0,
    }
    assert snapshot.recent_closes["SZ300750"] == [
        ("2026-03-24", 176.0),
        ("2026-03-25", 177.1),
        ("2026-03-26", 178.4),
        ("2026-03-27", 179.0),
        ("2026-03-28", 180.5),
        ("2026-03-31", 177.54),
        ("2026-04-01", 188.55),
    ]
    assert "SELECT MAX(tradedate)" in client.calls[0]["params"]["q"]
    assert "tradedate < '2026-04-01'" in client.calls[1]["params"]["q"]
    assert "symbol IN ('SZ300750','SZ002594')" in client.calls[2]["params"]["q"]
    assert "SELECT DISTINCT tradedate" in client.calls[3]["params"]["q"]
    assert "ORDER BY tradedate DESC" in client.calls[3]["params"]["q"]
    assert "LIMIT 7" in client.calls[3]["params"]["q"]
    assert (
        "tradedate IN ('2026-04-01','2026-03-31','2026-03-28','2026-03-27','2026-03-26','2026-03-25','2026-03-24')"
        in client.calls[4]["params"]["q"]
    )
    assert "ORDER BY symbol ASC, tradedate ASC" in client.calls[4]["params"]["q"]


def test_fetch_watchlist_prices_raises_for_unsuccessful_query_payload() -> None:
    client = FakeHttpClient(
        [
            {
                "query_execution_status": "Error",
                "query_execution_message": "query error: Error parsing SQL: syntax error near SELECT",
            }
        ]
    )

    adapter = DoltHubClient(http_client=client)

    with pytest.raises(
        RuntimeError,
        match="DoltHub query failed: query error: Error parsing SQL: syntax error near SELECT",
    ):
        adapter.fetch_watchlist_prices(["SZ300750"])


def test_fetch_watchlist_prices_raises_when_requested_symbols_are_incomplete() -> None:
    client = FakeHttpClient(
        [
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-04-01"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-03-31"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {
                        "tradedate": "2026-04-01",
                        "symbol": "SZ300750",
                        "close": "188.55",
                        "volume": "123456789",
                        "amount": "2345678901",
                    },
                    {
                        "tradedate": "2026-03-31",
                        "symbol": "SZ002594",
                        "close": "211.72",
                    },
                ]
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-04-01"},
                    {"tradedate": "2026-03-31"},
                    {"tradedate": "2026-03-28"},
                    {"tradedate": "2026-03-27"},
                    {"tradedate": "2026-03-26"},
                    {"tradedate": "2026-03-25"},
                    {"tradedate": "2026-03-24"},
                ],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-03-24", "symbol": "SZ300750", "close": "176.00"},
                    {"tradedate": "2026-03-25", "symbol": "SZ300750", "close": "177.10"},
                    {"tradedate": "2026-03-26", "symbol": "SZ300750", "close": "178.40"},
                    {"tradedate": "2026-03-27", "symbol": "SZ300750", "close": "179.00"},
                    {"tradedate": "2026-03-28", "symbol": "SZ300750", "close": "180.50"},
                    {"tradedate": "2026-03-31", "symbol": "SZ300750", "close": "177.54"},
                    {"tradedate": "2026-04-01", "symbol": "SZ300750", "close": "188.55"},
                ]
            },
        ]
    )

    adapter = DoltHubClient(http_client=client)

    with pytest.raises(
        ValueError,
        match=(
            "Missing latest closes for symbols: SZ002594; "
            "missing previous closes for symbols: SZ300750; "
            "missing latest volumes for symbols: SZ002594; "
            "missing latest amounts for symbols: SZ002594; "
            "missing seven closes for symbols: SZ002594"
        ),
    ):
        adapter.fetch_watchlist_prices(["SZ300750", "SZ002594"])


def test_fetch_watchlist_prices_uses_latest_seven_valid_closes() -> None:
    client = FakeHttpClient(
        [
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-04-01"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [{"tradedate": "2026-03-31"}],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {
                        "tradedate": "2026-04-01",
                        "symbol": "SZ300750",
                        "close": "188.55",
                        "volume": "123456789",
                        "amount": "2345678901",
                    },
                    {
                        "tradedate": "2026-03-31",
                        "symbol": "SZ300750",
                        "close": "177.54",
                    },
                ],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-04-01"},
                    {"tradedate": "2026-03-31"},
                    {"tradedate": "2026-03-30"},
                    {"tradedate": "2026-03-29"},
                    {"tradedate": "2026-03-26"},
                    {"tradedate": "2026-03-25"},
                    {"tradedate": "2026-03-24"},
                ],
            },
            {
                "query_execution_status": "Success",
                "rows": [
                    {"tradedate": "2026-03-24", "symbol": "SZ300750", "close": "176.00"},
                    {"tradedate": "2026-03-25", "symbol": "SZ300750", "close": "177.10"},
                    {"tradedate": "2026-03-26", "symbol": "SZ300750", "close": "178.40"},
                    {"tradedate": "2026-03-29", "symbol": "SZ300750", "close": "179.60"},
                    {"tradedate": "2026-03-30", "symbol": "SZ300750", "close": "180.20"},
                    {"tradedate": "2026-03-31", "symbol": "SZ300750", "close": "177.54"},
                    {"tradedate": "2026-04-01", "symbol": "SZ300750", "close": "188.55"},
                ],
            },
        ]
    )

    adapter = DoltHubClient(http_client=client)

    snapshot = adapter.fetch_watchlist_prices(["SZ300750"])

    assert snapshot.recent_closes["SZ300750"] == [
        ("2026-03-24", 176.0),
        ("2026-03-25", 177.1),
        ("2026-03-26", 178.4),
        ("2026-03-29", 179.6),
        ("2026-03-30", 180.2),
        ("2026-03-31", 177.54),
        ("2026-04-01", 188.55),
    ]
    assert "SELECT DISTINCT tradedate" in client.calls[3]["params"]["q"]
    assert "LIMIT 7" in client.calls[3]["params"]["q"]
    assert "tradedate IN (" in client.calls[4]["params"]["q"]
