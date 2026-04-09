from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from math import isfinite

import akshare as ak

from financehub_market_api.recommendation.candidate_pool.schemas import (
    ProductChartPoint,
    ProductDetailSnapshot,
)
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile
from financehub_market_api.upstreams.dolthub import DoltHubClient, StockPriceSnapshot
from financehub_market_api.watchlist import WATCHLIST, WatchlistEntry

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


def _first_present(row: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if key in row and row[key] not in (None, "", "--"):
            return row[key]
    return None


def _normalize_risk_level(value: object, *, default: str = "R2") -> str:
    text = _to_str(value).upper()
    if text in {"R1", "R2", "R3", "R4", "R5"}:
        return text
    for level in ("1", "2", "3", "4", "5"):
        if level in text:
            return f"R{level}"
    return default


def _to_stock_symbol(code: str) -> str:
    normalized = code.strip()
    if normalized.startswith(("600", "601", "603", "605", "688", "689")):
        return f"SH{normalized}"
    return f"SZ{normalized}"


def _estimate_liquidity_from_term(term: object) -> str | None:
    text = _to_str(term)
    if not text:
        return None
    return text


def _chunk_symbols(symbols: list[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(symbols), batch_size):
        yield symbols[start : start + batch_size]


def _merge_stock_price_snapshots(snapshots: Sequence[StockPriceSnapshot]) -> StockPriceSnapshot:
    if not snapshots:
        raise ValueError("at least one stock snapshot is required to merge")

    latest_prices: dict[str, float] = {}
    previous_prices: dict[str, float] = {}
    latest_volumes: dict[str, float] = {}
    latest_amounts: dict[str, float] = {}
    recent_closes: dict[str, list[tuple[str, float]]] = {}
    for snapshot in snapshots:
        latest_prices.update(snapshot.latest_prices)
        previous_prices.update(snapshot.previous_prices)
        latest_volumes.update(snapshot.latest_volumes)
        latest_amounts.update(snapshot.latest_amounts)
        recent_closes.update(snapshot.recent_closes)

    return StockPriceSnapshot(
        as_of_date=max(snapshot.as_of_date for snapshot in snapshots),
        latest_prices=latest_prices,
        previous_prices=previous_prices,
        latest_volumes=latest_volumes,
        latest_amounts=latest_amounts,
        recent_closes=recent_closes,
    )


def _candidate_to_detail_snapshot(
    candidate: CandidateProduct,
    *,
    as_of_date: str,
    source: str,
    provider_name: str | None,
    summary_zh: str,
    summary_en: str,
    yield_metrics: dict[str, str] | None = None,
    fees: dict[str, str] | None = None,
    drawdown_or_volatility: dict[str, str] | None = None,
    chart: list[ProductChartPoint] | None = None,
    chart_label_zh: str = "近期走势",
    chart_label_en: str = "Recent trend",
    fit_for_profile_zh: str = "适合稳健增值型配置。",
    fit_for_profile_en: str = "Fits a steady-growth allocation.",
) -> ProductDetailSnapshot:
    generated_at = datetime.now().astimezone().isoformat()
    return ProductDetailSnapshot(
        id=candidate.id,
        category=candidate.category,  # type: ignore[arg-type]
        code=candidate.code,
        provider_name=provider_name,
        name_zh=candidate.name_zh,
        name_en=candidate.name_en,
        as_of_date=as_of_date,
        generated_at=generated_at,
        fresh_until=generated_at,
        source=source,
        stale=False,
        risk_level=candidate.risk_level,
        liquidity=candidate.liquidity,
        tags_zh=list(candidate.tags_zh),
        tags_en=list(candidate.tags_en),
        summary_zh=summary_zh,
        summary_en=summary_en,
        recommendation_rationale_zh=candidate.rationale_zh,
        recommendation_rationale_en=candidate.rationale_en,
        chart_label_zh=chart_label_zh,
        chart_label_en=chart_label_en,
        chart=list(chart or []),
        yield_metrics=dict(yield_metrics or {}),
        fees=dict(fees or {}),
        drawdown_or_volatility=dict(drawdown_or_volatility or {}),
        fit_for_profile_zh=fit_for_profile_zh,
        fit_for_profile_en=fit_for_profile_en,
    )


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


class BondFundDetailAdapter:
    def __init__(self, adapter: BondFundCandidateAdapter | None = None) -> None:
        self._adapter = adapter or BondFundCandidateAdapter()

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        default_profile = UserProfile(
            risk_profile="stable",
            label_zh="稳健型",
            label_en="Stable",
        )
        details: list[ProductDetailSnapshot] = []
        for candidate in self._adapter.list_candidates(default_profile):
            details.append(
                _candidate_to_detail_snapshot(
                    candidate,
                    as_of_date=datetime.now().strftime("%Y-%m-%d"),
                    source="public_bond_fund_refresh",
                    provider_name="Public bond fund universe",
                    summary_zh="公开债券基金底仓候选，强调稳健与流动性。",
                    summary_en="Public bond-fund candidate focused on stability and liquidity.",
                    chart_label_zh="近期净值",
                    chart_label_en="Recent NAV",
                )
            )
        return details


class PublicWealthManagementDetailAdapter:
    """Attempts to parse public bank or wealth-subsidiary products into detail snapshots."""

    def __init__(self, fetcher: DataFetcher | None = None, *, max_items: int = 3) -> None:
        self._fetcher = fetcher
        self._max_items = max_items

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        if self._fetcher is None:
            return []

        details: list[ProductDetailSnapshot] = []
        frame = self._fetcher()
        for row in _iter_data_rows(frame):
            if len(details) >= self._max_items:
                break

            code = _to_str(_first_present(row, "产品代码", "登记编码", "编码"))
            name = _to_str(_first_present(row, "产品名称", "名称"))
            provider_name = _to_str(_first_present(row, "机构名称", "发行机构", "理财公司"))
            if not name:
                continue

            risk_level = _normalize_risk_level(
                _first_present(row, "风险等级", "风险级别"),
                default="R2",
            )
            if risk_level not in {"R1", "R2"}:
                continue

            as_of_date = _extract_date(_first_present(row, "日期", "净值日期", "更新日期"))
            liquidity = _estimate_liquidity_from_term(
                _first_present(row, "期限", "开放频率", "开放周期")
            )
            expected_yield = _parse_percent(
                _first_present(row, "近1月年化收益率", "七日年化收益率", "业绩比较基准")
            )
            fee_percent = _parse_percent(_first_present(row, "管理费", "手续费"))
            product_id = f"wm-{code}" if code else f"wm-public-{len(details) + 1:03d}"
            details.append(
                ProductDetailSnapshot(
                    id=product_id,
                    category="wealth_management",
                    code=code or None,
                    provider_name=provider_name or "Public wealth-management source",
                    name_zh=name,
                    name_en=name,
                    as_of_date=as_of_date,
                    generated_at=datetime.now().astimezone().isoformat(),
                    fresh_until=datetime.now().astimezone().isoformat(),
                    source="public_wealth_management_refresh",
                    stale=False,
                    risk_level=risk_level,
                    liquidity=liquidity,
                    tags_zh=["银行理财", "公开披露", "稳健候选"],
                    tags_en=["Bank wealth management", "Public disclosure", "Steady candidate"],
                    summary_zh="公开理财产品候选，优先满足稳健和期限可解释性。",
                    summary_en="Public wealth-management candidate prioritizing steady use cases and explainable tenor.",
                    recommendation_rationale_zh="来自公开理财产品池，兼顾稳健收益诉求与期限适配。",
                    recommendation_rationale_en="Selected from the public wealth-management pool for steady return and tenor fit.",
                    chart_label_zh="近期表现",
                    chart_label_en="Recent performance",
                    chart=[],
                    yield_metrics=(
                        {"expectedYield": f"{expected_yield:.2f}%"}
                        if expected_yield is not None
                        else {}
                    ),
                    fees=(
                        {"managementFee": f"{fee_percent:.2f}%"}
                        if fee_percent is not None
                        else {}
                    ),
                    drawdown_or_volatility={},
                    fit_for_profile_zh="适合低到中低风险、强调期限匹配的用户。",
                    fit_for_profile_en="Fits low- to lower-medium-risk users who care about tenor matching.",
                )
            )

        return details


class MoneyFundWealthProxyDetailAdapter:
    def __init__(self, adapter: MoneyFundWealthProxyAdapter | None = None) -> None:
        self._adapter = adapter or MoneyFundWealthProxyAdapter()

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        default_profile = UserProfile(
            risk_profile="stable",
            label_zh="稳健型",
            label_en="Stable",
        )
        details: list[ProductDetailSnapshot] = []
        for candidate in self._adapter.list_candidates(default_profile):
            details.append(
                _candidate_to_detail_snapshot(
                    candidate,
                    as_of_date=datetime.now().strftime("%Y-%m-%d"),
                    source="money_fund_proxy_refresh",
                    provider_name="Money-fund proxy universe",
                    summary_zh="公开现金管理代理候选，用于理财产品源缺失时的稳健兜底。",
                    summary_en="Public cash-management proxy candidate used as a steady fallback.",
                    chart_label_zh="近期收益",
                    chart_label_en="Recent yield",
                    fit_for_profile_zh="适合强调高流动性和稳健性的用户。",
                    fit_for_profile_en="Fits users who prioritize high liquidity and steadiness.",
                )
            )
        return details


class PremiumStockDetailAdapter:
    def __init__(
        self,
        constituent_fetchers: Sequence[tuple[str, DataFetcher]] | None = None,
        *,
        price_snapshot_fetcher: Callable[[list[str]], StockPriceSnapshot] | None = None,
        max_universe_size: int = 150,
        max_items: int = 12,
        price_snapshot_batch_size: int = 8,
    ) -> None:
        self._constituent_fetchers = list(
            constituent_fetchers
            or (
                (
                    "CSI300",
                    lambda: ak.index_stock_cons_csindex(symbol="000300"),
                ),
                (
                    "Dividend",
                    lambda: ak.index_stock_cons_csindex(symbol="000922"),
                ),
            )
        )
        self._price_snapshot_fetcher = price_snapshot_fetcher or self._fetch_default_price_snapshot
        self._max_universe_size = max_universe_size
        self._max_items = max_items
        self._price_snapshot_batch_size = price_snapshot_batch_size

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        universe = self._build_universe()
        if not universe:
            return []

        symbols = [_to_stock_symbol(entry.code) for entry in universe]
        snapshot = self._fetch_price_snapshot(symbols)
        ranked: list[tuple[tuple[float, float, float], ProductDetailSnapshot]] = []
        for entry in universe:
            symbol = _to_stock_symbol(entry.code)
            latest_price = snapshot.latest_prices.get(symbol)
            previous_price = snapshot.previous_prices.get(symbol)
            latest_amount = snapshot.latest_amounts.get(symbol)
            recent_closes = snapshot.recent_closes.get(symbol, [])
            if (
                latest_price is None
                or previous_price in (None, 0)
                or latest_amount is None
                or len(recent_closes) < 2
            ):
                continue

            change_percent = ((latest_price - previous_price) / previous_price) * 100
            weekly_values = [close for _, close in recent_closes]
            min_close = min(weekly_values)
            max_close = max(weekly_values)
            weekly_range_percent = (
                ((max_close - min_close) / min_close) * 100 if min_close > 0 else 0.0
            )
            if not all(isfinite(value) for value in (change_percent, weekly_range_percent)):
                continue

            trend_points = [
                ProductChartPoint(date=trade_date, value=close)
                for trade_date, close in recent_closes
            ]
            tags_zh = ["指数成分", "动态精选", entry.sector]
            tags_en = ["Index constituent", "Dynamically selected", entry.sector_en]
            detail = ProductDetailSnapshot(
                id=f"stock-{entry.code}",
                category="stock",
                code=entry.code,
                provider_name=entry.provider_name,
                name_zh=entry.name_zh,
                name_en=entry.name_en,
                as_of_date=snapshot.as_of_date,
                generated_at=datetime.now().astimezone().isoformat(),
                fresh_until=datetime.now().astimezone().isoformat(),
                source="premium_stock_refresh",
                stale=False,
                risk_level="R3",
                liquidity=None,
                tags_zh=[tag for tag in tags_zh if tag],
                tags_en=[tag for tag in tags_en if tag],
                summary_zh="基于精品股票池和动态行情事实生成的股票候选。",
                summary_en="Stock candidate built from the premium stock universe and dynamic market facts.",
                recommendation_rationale_zh="综合指数成分身份、近期趋势、成交额与波动约束后动态入选。",
                recommendation_rationale_en="Dynamically selected from index-based constituents after combining trend, liquidity, and volatility constraints.",
                chart_label_zh="近7日收盘走势",
                chart_label_en="7-day closing trend",
                chart=trend_points,
                yield_metrics={
                    "latestPrice": f"{latest_price:.2f}",
                    "changePercent": f"{change_percent:+.2f}%",
                },
                fees={},
                drawdown_or_volatility={"weeklyRangePercent": f"{weekly_range_percent:.2f}%"},
                fit_for_profile_zh="适合作为权益增强部分的精品股票候选。",
                fit_for_profile_en="Fits the equity-enhancement sleeve as a premium stock candidate.",
            )
            score = (latest_amount, -abs(change_percent), -weekly_range_percent)
            ranked.append((score, detail))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [detail for _, detail in ranked[: self._max_items]]

    def _fetch_default_price_snapshot(self, symbols: list[str]) -> StockPriceSnapshot:
        return DoltHubClient().fetch_watchlist_prices(symbols)

    def _fetch_price_snapshot(self, symbols: list[str]) -> StockPriceSnapshot:
        if len(symbols) <= self._price_snapshot_batch_size:
            return self._price_snapshot_fetcher(symbols)

        snapshots = [
            self._price_snapshot_fetcher(batch)
            for batch in _chunk_symbols(symbols, self._price_snapshot_batch_size)
        ]
        return _merge_stock_price_snapshots(snapshots)

    def _build_universe(self) -> list["_PremiumUniverseEntry"]:
        by_code: dict[str, _PremiumUniverseEntry] = {}
        for provider_name, fetcher in self._constituent_fetchers:
            try:
                frame = fetcher()
            except Exception:
                continue
            for row in _iter_data_rows(frame):
                code = _to_str(
                    _first_present(row, "品种代码", "成分券代码", "代码", "证券代码")
                )
                name = _to_str(
                    _first_present(row, "品种名称", "成分券名称", "名称", "证券简称")
                )
                if not code or not name or code in by_code:
                    continue
                by_code[code] = _PremiumUniverseEntry(
                    code=code,
                    name_zh=name,
                    name_en=name,
                    provider_name=provider_name,
                    sector="精品股票池",
                    sector_en="Premium universe",
                )
                if len(by_code) >= self._max_universe_size:
                    break
            if len(by_code) >= self._max_universe_size:
                break

        for entry in WATCHLIST:
            if len(by_code) >= self._max_universe_size:
                break
            if entry.code in by_code:
                continue
            by_code[entry.code] = _PremiumUniverseEntry(
                code=entry.code,
                name_zh=entry.name,
                name_en=entry.name,
                provider_name="Watchlist seed",
                sector=entry.sector,
                sector_en=entry.sector,
            )

        return list(by_code.values())


class _PremiumUniverseEntry:
    def __init__(
        self,
        *,
        code: str,
        name_zh: str,
        name_en: str,
        provider_name: str,
        sector: str,
        sector_en: str,
    ) -> None:
        self.code = code
        self.name_zh = name_zh
        self.name_en = name_en
        self.provider_name = provider_name
        self.sector = sector
        self.sector_en = sector_en
