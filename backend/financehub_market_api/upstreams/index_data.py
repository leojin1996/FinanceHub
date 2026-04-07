from __future__ import annotations

from dataclasses import dataclass

import akshare as ak


@dataclass(frozen=True)
class IndexSnapshot:
    name: str
    as_of_date: str
    closes: list[tuple[str, float]]


@dataclass(frozen=True)
class IndexMetadata:
    code: str
    ak_symbol: str
    description: str
    market: str = "中国市场"


INDEX_METADATA = {
    "上证指数": IndexMetadata(
        code="000001.SH",
        ak_symbol="sh000001",
        description="沪市核心宽基指数",
    ),
    "深证成指": IndexMetadata(
        code="399001.SZ",
        ak_symbol="sz399001",
        description="深市代表性综合指数",
    ),
    "创业板指": IndexMetadata(
        code="399006.SZ",
        ak_symbol="sz399006",
        description="成长风格代表指数",
    ),
    "科创50": IndexMetadata(
        code="000688.SH",
        ak_symbol="sh000688",
        description="科创板核心龙头指数",
    ),
}
INDEX_ORDER = tuple(INDEX_METADATA.keys())


def _normalize_date(value: object) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


class IndexDataClient:
    def fetch_recent_closes(self, days: int = 5) -> dict[str, IndexSnapshot]:
        snapshots: dict[str, IndexSnapshot] = {}

        for name in INDEX_ORDER:
            metadata = INDEX_METADATA[name]
            frame = ak.stock_zh_index_daily(symbol=metadata.ak_symbol).tail(days).copy()
            normalized = [
                (
                    _normalize_date(row["date"]),
                    float(row["close"]),
                )
                for _, row in frame.iterrows()
            ]
            snapshots[name] = IndexSnapshot(
                name=name,
                as_of_date=normalized[-1][0],
                closes=normalized,
            )

        return snapshots
