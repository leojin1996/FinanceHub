from __future__ import annotations

from dataclasses import dataclass

import httpx


class DoltHubQueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class StockPriceSnapshot:
    as_of_date: str
    latest_prices: dict[str, float]
    previous_prices: dict[str, float]
    latest_volumes: dict[str, float]
    latest_amounts: dict[str, float]
    recent_closes: dict[str, list[tuple[str, float]]]


class DoltHubClient:
    BASE_URL = "https://www.dolthub.com/api/v1alpha1/chenditc/investment_data"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client()

    def _query(self, sql: str) -> dict:
        response = self._http_client.get(self.BASE_URL, params={"q": sql}, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
        if payload.get("query_execution_status") != "Success":
            error_message = payload.get("query_execution_message") or payload.get(
                "error_message",
                "unknown upstream error",
            )
            raise DoltHubQueryError(f"DoltHub query failed: {error_message}")
        return payload

    def fetch_watchlist_prices(self, symbols: list[str]) -> StockPriceSnapshot:
        requested_symbols = set(symbols)
        quoted_symbols = ",".join(f"'{symbol}'" for symbol in symbols)

        latest_date_payload = self._query(
            f"SELECT MAX(tradedate) AS tradedate FROM final_a_stock_eod_price WHERE symbol IN ({quoted_symbols})"
        )
        latest_date = latest_date_payload["rows"][0]["tradedate"]

        previous_date_payload = self._query(
            "SELECT MAX(tradedate) AS tradedate "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) AND tradedate < '{latest_date}'"
        )
        previous_date = previous_date_payload["rows"][0]["tradedate"]

        prices_payload = self._query(
            "SELECT tradedate, symbol, close, volume, amount "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) AND tradedate IN ('{latest_date}','{previous_date}')"
        )
        recent_dates_payload = self._query(
            "SELECT DISTINCT tradedate "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) "
            "ORDER BY tradedate DESC "
            "LIMIT 7"
        )
        recent_dates = [
            row["tradedate"]
            for row in recent_dates_payload["rows"]
            if row.get("tradedate") not in (None, "")
        ]
        recent_dates_sql = ",".join(f"'{trade_date}'" for trade_date in recent_dates)
        recent_closes_payload = self._query(
            "SELECT tradedate, symbol, close "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) "
            "AND close IS NOT NULL "
            "AND close <> '' "
            f"AND tradedate IN ({recent_dates_sql}) "
            "ORDER BY symbol ASC, tradedate ASC"
        )

        latest_prices: dict[str, float] = {}
        previous_prices: dict[str, float] = {}
        latest_volumes: dict[str, float] = {}
        latest_amounts: dict[str, float] = {}
        for row in prices_payload["rows"]:
            symbol = row["symbol"]
            close_value = row.get("close")
            if close_value in (None, ""):
                continue
            close = float(close_value)
            if row["tradedate"] == latest_date:
                latest_prices[symbol] = close
                volume_value = row.get("volume")
                amount_value = row.get("amount")
                if volume_value not in (None, ""):
                    latest_volumes[symbol] = float(volume_value)
                if amount_value not in (None, ""):
                    latest_amounts[symbol] = float(amount_value)
            else:
                previous_prices[symbol] = close

        recent_closes: dict[str, list[tuple[str, float]]] = {}
        for row in recent_closes_payload["rows"]:
            close_value = row.get("close")
            trade_date = row.get("tradedate")
            if close_value in (None, "") or trade_date in (None, ""):
                continue
            recent_closes.setdefault(row["symbol"], []).append((trade_date, float(close_value)))

        missing_latest = sorted(requested_symbols - set(latest_prices))
        missing_previous = sorted(requested_symbols - set(previous_prices))
        missing_volumes = sorted(requested_symbols - set(latest_volumes))
        missing_amounts = sorted(requested_symbols - set(latest_amounts))
        missing_recent = sorted(
            symbol
            for symbol in requested_symbols
            if len(recent_closes.get(symbol, [])) != 7
        )
        if (
            missing_latest
            or missing_previous
            or missing_volumes
            or missing_amounts
            or missing_recent
        ):
            message_parts: list[str] = []
            if missing_latest:
                message_parts.append(
                    f"Missing latest closes for symbols: {', '.join(missing_latest)}"
                )
            if missing_previous:
                prefix = "Missing previous closes" if not message_parts else "missing previous closes"
                message_parts.append(
                    f"{prefix} for symbols: {', '.join(missing_previous)}"
                )
            if missing_volumes:
                prefix = "Missing latest volumes" if not message_parts else "missing latest volumes"
                message_parts.append(
                    f"{prefix} for symbols: {', '.join(missing_volumes)}"
                )
            if missing_amounts:
                prefix = "Missing latest amounts" if not message_parts else "missing latest amounts"
                message_parts.append(
                    f"{prefix} for symbols: {', '.join(missing_amounts)}"
                )
            if missing_recent:
                prefix = "Missing seven closes" if not message_parts else "missing seven closes"
                message_parts.append(
                    f"{prefix} for symbols: {', '.join(missing_recent)}"
                )
            raise ValueError("; ".join(message_parts))

        return StockPriceSnapshot(
            as_of_date=latest_date,
            latest_prices=latest_prices,
            previous_prices=previous_prices,
            latest_volumes=latest_volumes,
            latest_amounts=latest_amounts,
            recent_closes=recent_closes,
        )
