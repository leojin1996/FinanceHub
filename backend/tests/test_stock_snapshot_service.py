import pytest

from financehub_market_api.service import build_stock_rows, split_rankings
from financehub_market_api.models import StockRow
from financehub_market_api.upstreams.dolthub import StockPriceSnapshot
from financehub_market_api.watchlist import WATCHLIST


def _build_snapshot(
    latest_prices: dict[str, float],
    previous_prices: dict[str, float],
) -> StockPriceSnapshot:
    latest_volumes = {
        symbol: float(index * 1_000_000)
        for index, symbol in enumerate(latest_prices, start=1)
    }
    latest_amounts = {
        symbol: float(index * 10_000_000)
        for index, symbol in enumerate(latest_prices, start=1)
    }
    recent_closes = {
        symbol: [
            ("2026-03-24", price - 6.0),
            ("2026-03-25", price - 5.0),
            ("2026-03-26", price - 4.0),
            ("2026-03-27", price - 3.0),
            ("2026-03-28", price - 2.0),
            ("2026-03-31", price - 1.0),
            ("2026-04-01", price),
        ]
        for symbol, price in latest_prices.items()
    }
    return StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices=latest_prices,
        previous_prices=previous_prices,
        latest_volumes=latest_volumes,
        latest_amounts=latest_amounts,
        recent_closes=recent_closes,
    )


def test_build_stock_rows_formats_prices_and_percentage_changes() -> None:
    latest_prices = {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
        "SH600519": 1608.00,
    }
    previous_prices = {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
        "SH600519": 1618.00,
    }

    rows = build_stock_rows(WATCHLIST[:3], _build_snapshot(latest_prices, previous_prices))

    assert [
        row.model_dump(include={"code", "name", "sector", "price", "change"})
        for row in rows
    ] == [
        {
            "code": "300750",
            "name": "宁德时代",
            "sector": "新能源",
            "price": "188.55",
            "change": "+6.2%",
        },
        {
            "code": "002594",
            "name": "比亚迪",
            "sector": "汽车",
            "price": "221.88",
            "change": "+4.8%",
        },
        {
            "code": "600519",
            "name": "贵州茅台",
            "sector": "白酒",
            "price": "1,608.00",
            "change": "-0.6%",
        },
    ]


def test_split_rankings_returns_top_and_bottom_movers() -> None:
    latest_prices = {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
        "SH600519": 1608.00,
        "SH600036": 43.50,
    }
    previous_prices = {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
        "SH600519": 1618.00,
        "SH600036": 45.10,
    }

    rows = build_stock_rows(WATCHLIST[:4], _build_snapshot(latest_prices, previous_prices))
    top_gainers, top_losers = split_rankings(rows, limit=2)

    assert [item.model_dump() for item in top_gainers] == [
        {"name": "宁德时代", "value": "+6.2%"},
        {"name": "比亚迪", "value": "+4.8%"},
    ]
    assert [item.model_dump() for item in top_losers] == [
        {"name": "招商银行", "value": "-3.5%"},
        {"name": "贵州茅台", "value": "-0.6%"},
    ]


def test_split_rankings_returns_no_losers_when_all_rows_are_positive() -> None:
    latest_prices = {
        "SZ300750": 101.00,
        "SZ002594": 102.00,
    }
    previous_prices = {
        "SZ300750": 100.00,
        "SZ002594": 100.00,
    }

    rows = build_stock_rows(WATCHLIST[:2], _build_snapshot(latest_prices, previous_prices))
    top_gainers, top_losers = split_rankings(rows, limit=3)

    assert [item.model_dump() for item in top_gainers] == [
        {"name": "比亚迪", "value": "+2.0%"},
        {"name": "宁德时代", "value": "+1.0%"},
    ]
    assert top_losers == []


def test_split_rankings_returns_no_gainers_when_all_rows_are_negative() -> None:
    latest_prices = {
        "SZ300750": 99.00,
        "SZ002594": 98.00,
    }
    previous_prices = {
        "SZ300750": 100.00,
        "SZ002594": 100.00,
    }

    rows = build_stock_rows(WATCHLIST[:2], _build_snapshot(latest_prices, previous_prices))
    top_gainers, top_losers = split_rankings(rows, limit=3)

    assert top_gainers == []
    assert [item.model_dump() for item in top_losers] == [
        {"name": "比亚迪", "value": "-2.0%"},
        {"name": "宁德时代", "value": "-1.0%"},
    ]


def test_split_rankings_uses_raw_change_for_near_ties() -> None:
    latest_prices = {
        "SZ300750": 101.03,
        "SZ002594": 101.04,
    }
    previous_prices = {
        "SZ300750": 100.00,
        "SZ002594": 100.00,
    }

    rows = build_stock_rows(WATCHLIST[:2], _build_snapshot(latest_prices, previous_prices))
    top_gainers, top_losers = split_rankings(rows, limit=2)

    assert [item.model_dump() for item in top_gainers] == [
        {"name": "比亚迪", "value": "+1.0%"},
        {"name": "宁德时代", "value": "+1.0%"},
    ]
    assert top_losers == []


def test_stock_row_schema_does_not_expose_internal_raw_change() -> None:
    schema = StockRow.model_json_schema()
    assert "raw_change" not in schema.get("properties", {})


def test_stock_row_schema_includes_numeric_fields_and_trend() -> None:
    schema = StockRow.model_json_schema()
    properties = schema["properties"]

    assert "priceValue" in properties
    assert "changePercent" in properties
    assert "volumeValue" in properties
    assert "amountValue" in properties
    assert "trend7d" in properties
    assert properties["priceValue"]["type"] == "number"
    assert properties["changePercent"]["type"] == "number"
    assert properties["volumeValue"]["type"] == "number"
    assert properties["amountValue"]["type"] == "number"
    assert properties["trend7d"]["type"] == "array"


def test_build_stock_rows_includes_volume_amount_and_trend() -> None:
    snapshot = StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices={"SZ300750": 188.55},
        previous_prices={"SZ300750": 177.54},
        latest_volumes={"SZ300750": 123456789.0},
        latest_amounts={"SZ300750": 2345678901.0},
        recent_closes={
            "SZ300750": [
                ("2026-03-24", 176.0),
                ("2026-03-25", 177.1),
                ("2026-03-26", 178.4),
                ("2026-03-27", 179.0),
                ("2026-03-28", 180.5),
                ("2026-03-31", 182.0),
                ("2026-04-01", 188.55),
            ]
        },
    )

    rows = build_stock_rows(WATCHLIST[:1], snapshot)
    expected_change_percent = ((188.55 - 177.54) / 177.54) * 100

    assert rows[0].code == "300750"
    assert rows[0].priceValue == 188.55
    assert rows[0].changePercent == pytest.approx(expected_change_percent)
    assert rows[0].volumeValue == 123456789.0
    assert rows[0].amountValue == 2345678901.0
    assert [point.date for point in rows[0].trend7d] == [
        "2026-03-24",
        "2026-03-25",
        "2026-03-26",
        "2026-03-27",
        "2026-03-28",
        "2026-03-31",
        "2026-04-01",
    ]
    assert [point.value for point in rows[0].trend7d] == [
        176.0,
        177.1,
        178.4,
        179.0,
        180.5,
        182.0,
        188.55,
    ]
