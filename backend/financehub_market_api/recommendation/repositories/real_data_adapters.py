from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

import akshare as ak

from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile

DataRow = Mapping[str, object]
DataFetcher = Callable[[], object]


def _iter_data_rows(frame: object) -> Iterable[DataRow]:
    iterrows = getattr(frame, "iterrows", None)
    if iterrows is None or not callable(iterrows):
        raise TypeError("upstream frame must provide iterrows()")

    for _, row in iterrows():
        if isinstance(row, Mapping):
            yield row
            continue
        to_dict = getattr(row, "to_dict", None)
        if to_dict is None or not callable(to_dict):
            raise TypeError("upstream row must be mapping-compatible")
        yield to_dict()


def _to_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "--", "nan", "None"}:
        return ""
    return text


def _parse_percent(value: object) -> float | None:
    text = _to_str(value)
    if not text:
        return None
    normalized = text.replace("%", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_positive_float(value: object) -> float | None:
    text = _to_str(value)
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _extract_date(value: object) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return _to_str(value) or datetime.now().strftime("%Y-%m-%d")


class BondFundCandidateAdapter:
    """Fetches low-risk bond fund candidates from public AkShare data."""

    def __init__(self, fetcher: DataFetcher | None = None, *, max_items: int = 2) -> None:
        self._fetcher = fetcher or (lambda: ak.fund_open_fund_rank_em(symbol="债券型"))
        self._max_items = max_items

    def list_candidates(self, user_profile: UserProfile) -> list[CandidateProduct]:
        del user_profile
        candidates: list[CandidateProduct] = []

        frame = self._fetcher()
        for row in _iter_data_rows(frame):
            if len(candidates) >= self._max_items:
                break

            code = _to_str(row.get("基金代码"))
            name = _to_str(row.get("基金简称"))
            if not code or not name:
                continue

            unit_nav = _parse_positive_float(row.get("单位净值"))
            if unit_nav is None:
                continue

            fee_percent = _parse_percent(row.get("手续费"))
            if fee_percent is not None and fee_percent > 1.0:
                continue

            as_of_date = _extract_date(row.get("日期"))
            candidates.append(
                CandidateProduct(
                    id=f"fund-{len(candidates) + 1:03d}",
                    category="fund",
                    code=code,
                    name_zh=name,
                    name_en=name,
                    risk_level="R2",
                    tags_zh=["债券型公募", "稳健底仓", "低风险优先"],
                    tags_en=["Public bond fund", "Stable core", "Low-risk focused"],
                    rationale_zh=f"基于公开债券基金数据筛选，作为稳健型底仓候选（数据日期：{as_of_date}）。",
                    rationale_en=f"Selected from public bond-fund data as a stable core candidate (as of {as_of_date}).",
                    liquidity="T+1",
                )
            )

        return candidates


class MoneyFundWealthProxyAdapter:
    """Fetches cash-management proxy candidates from public money-fund data."""

    def __init__(self, fetcher: DataFetcher | None = None, *, max_items: int = 2) -> None:
        self._fetcher = fetcher or ak.fund_money_rank_em
        self._max_items = max_items

    def list_candidates(self, user_profile: UserProfile) -> list[CandidateProduct]:
        del user_profile
        candidates: list[CandidateProduct] = []

        frame = self._fetcher()
        for row in _iter_data_rows(frame):
            if len(candidates) >= self._max_items:
                break

            code = _to_str(row.get("基金代码"))
            name = _to_str(row.get("基金简称"))
            if not code or not name:
                continue

            annualized_7d = _parse_percent(row.get("年化收益率7日"))
            if annualized_7d is None or annualized_7d <= 0:
                continue

            fee_percent = _parse_percent(row.get("手续费"))
            if fee_percent is not None and fee_percent > 0.5:
                continue

            as_of_date = _extract_date(row.get("日期"))
            candidates.append(
                CandidateProduct(
                    id=f"wm-{len(candidates) + 1:03d}",
                    category="wealth_management",
                    code=code,
                    name_zh=name,
                    name_en=name,
                    risk_level="R1",
                    tags_zh=["货币基金代理", "现金管理", "高流动性"],
                    tags_en=["Money-fund proxy", "Cash management", "High liquidity"],
                    rationale_zh=f"该候选为公开货币基金数据代理，不代表银行专属理财（数据日期：{as_of_date}）。",
                    rationale_en=f"This candidate is a public money-fund proxy and not a proprietary bank product (as of {as_of_date}).",
                    liquidity="T+0/T+1",
                )
            )

        return candidates
