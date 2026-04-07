from financehub_market_api.upstreams import index_data
from financehub_market_api.upstreams.index_data import IndexDataClient


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def tail(self, days: int) -> "FakeFrame":
        return FakeFrame(self._rows[-days:])

    def copy(self) -> "FakeFrame":
        return FakeFrame(self._rows.copy())

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


def test_fetch_recent_closes_uses_expected_symbols_and_normalizes_string_dates(
    monkeypatch,
) -> None:
    calls: list[str] = []
    payloads = {
        "sh000001": [
            {"date": "2026-04-01", "close": "3340.12"},
            {"date": "2026-04-02", "close": "3355.48"},
        ],
        "sz399001": [
            {"date": "2026-04-01", "close": 10422.32},
            {"date": "2026-04-02", "close": 10501.65},
        ],
        "sz399006": [
            {"date": "2026-04-01", "close": 2100.11},
            {"date": "2026-04-02", "close": 2112.98},
        ],
        "sh000688": [
            {"date": "2026-04-01", "close": 980.31},
            {"date": "2026-04-02", "close": 992.44},
        ],
    }

    def fake_stock_zh_index_daily(symbol: str) -> FakeFrame:
        calls.append(symbol)
        return FakeFrame(payloads[symbol])

    monkeypatch.setattr(index_data.ak, "stock_zh_index_daily", fake_stock_zh_index_daily)

    snapshots = IndexDataClient().fetch_recent_closes(days=2)

    assert calls == ["sh000001", "sz399001", "sz399006", "sh000688"]
    assert snapshots["上证指数"].as_of_date == "2026-04-02"
    assert snapshots["上证指数"].closes == [
        ("2026-04-01", 3340.12),
        ("2026-04-02", 3355.48),
    ]
    assert snapshots["深证成指"].closes == [
        ("2026-04-01", 10422.32),
        ("2026-04-02", 10501.65),
    ]
    assert snapshots["创业板指"].as_of_date == "2026-04-02"
    assert snapshots["科创50"].as_of_date == "2026-04-02"
    assert snapshots["科创50"].closes == [
        ("2026-04-01", 980.31),
        ("2026-04-02", 992.44),
    ]
