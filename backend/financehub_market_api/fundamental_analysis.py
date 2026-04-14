from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import akshare as ak
import pandas as pd
from pydantic import BaseModel, Field

from financehub_market_api.env import build_env_values, read_env

LOGGER = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "akshare"
_DEFAULT_MAX_PEERS = 5
_DEFAULT_REPORT_QUARTERS = 8
_DISCLAIMER = "本分析仅供参考，不构成任何投资建议。"


class FundamentalDataClient(Protocol):
    def search_a_share_code_name(self) -> pd.DataFrame: ...

    def stock_individual_info(self, symbol: str) -> pd.DataFrame: ...

    def stock_financial_analysis_indicator(
        self,
        symbol: str,
        *,
        start_year: str,
    ) -> pd.DataFrame: ...

    def stock_financial_abstract(self, symbol: str) -> pd.DataFrame: ...

    def stock_profit_sheet_by_report(self, symbol: str) -> pd.DataFrame: ...

    def stock_balance_sheet_by_report(self, symbol: str) -> pd.DataFrame: ...

    def stock_cash_flow_sheet_by_report(self, symbol: str) -> pd.DataFrame: ...

    def stock_board_industry_cons(self, industry: str) -> pd.DataFrame: ...


class FundamentalAnalysisReport(BaseModel):
    symbol: str
    name: str
    asOf: str
    industry: str | None = None
    dataCoverage: dict[str, Any] = Field(default_factory=dict)
    scorecard: dict[str, dict[str, Any]] = Field(default_factory=dict)
    companyProfile: dict[str, Any] = Field(default_factory=dict)
    financialQuality: dict[str, Any] = Field(default_factory=dict)
    profitability: dict[str, Any] = Field(default_factory=dict)
    growth: dict[str, Any] = Field(default_factory=dict)
    valuation: dict[str, Any] = Field(default_factory=dict)
    peerComparison: dict[str, Any] = Field(default_factory=dict)
    dcf: dict[str, Any] = Field(default_factory=dict)
    riskFlags: list[dict[str, Any]] = Field(default_factory=list)
    conclusionZh: str
    followUpWatchlist: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = _DISCLAIMER


class AkShareFundamentalDataClient:
    def search_a_share_code_name(self) -> pd.DataFrame:
        return ak.stock_info_a_code_name()

    def stock_individual_info(self, symbol: str) -> pd.DataFrame:
        return ak.stock_individual_info_em(symbol=_symbol_code(symbol))

    def stock_financial_analysis_indicator(
        self,
        symbol: str,
        *,
        start_year: str,
    ) -> pd.DataFrame:
        return ak.stock_financial_analysis_indicator(
            symbol=_symbol_code(symbol),
            start_year=start_year,
        )

    def stock_financial_abstract(self, symbol: str) -> pd.DataFrame:
        return ak.stock_financial_abstract(symbol=_symbol_code(symbol))

    def stock_profit_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        return ak.stock_profit_sheet_by_report_em(symbol=_em_symbol(symbol))

    def stock_balance_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        return ak.stock_balance_sheet_by_report_em(symbol=_em_symbol(symbol))

    def stock_cash_flow_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        return ak.stock_cash_flow_sheet_by_report_em(symbol=_em_symbol(symbol))

    def stock_board_industry_cons(self, industry: str) -> pd.DataFrame:
        return ak.stock_board_industry_cons_em(symbol=industry)


class FundamentalAnalysisService:
    def __init__(
        self,
        *,
        client: FundamentalDataClient | None = None,
        max_peers: int = _DEFAULT_MAX_PEERS,
        report_quarters: int = _DEFAULT_REPORT_QUARTERS,
    ) -> None:
        self._client = client or AkShareFundamentalDataClient()
        self._max_peers = _clamp_int(max_peers, default=_DEFAULT_MAX_PEERS, minimum=0, maximum=10)
        self._report_quarters = _clamp_int(
            report_quarters,
            default=_DEFAULT_REPORT_QUARTERS,
            minimum=1,
            maximum=16,
        )

    def analyze(
        self,
        *,
        symbol: str,
        peer_symbols: Sequence[str] | None = None,
    ) -> FundamentalAnalysisReport:
        normalized_symbol, resolved_name = self._resolve_symbol(symbol)
        code = _symbol_code(normalized_symbol)

        warnings: list[str] = []
        info = self._safe_frame(
            lambda: self._client.stock_individual_info(normalized_symbol),
            warnings=warnings,
            label="公司画像",
        )
        indicator = self._safe_frame(
            lambda: self._client.stock_financial_analysis_indicator(
                normalized_symbol,
                start_year=str(datetime.now(UTC).year - 4),
            ),
            warnings=warnings,
            label="财务指标",
        )
        abstract = self._safe_frame(
            lambda: self._client.stock_financial_abstract(normalized_symbol),
            warnings=warnings,
            label="财务摘要",
        )
        profit = self._safe_frame(
            lambda: self._client.stock_profit_sheet_by_report(normalized_symbol),
            warnings=warnings,
            label="利润表",
        )
        balance = self._safe_frame(
            lambda: self._client.stock_balance_sheet_by_report(normalized_symbol),
            warnings=warnings,
            label="资产负债表",
        )
        cashflow = self._safe_frame(
            lambda: self._client.stock_cash_flow_sheet_by_report(normalized_symbol),
            warnings=warnings,
            label="现金流量表",
        )

        if all(frame.empty for frame in (info, indicator, abstract, profit, balance, cashflow)):
            raise RuntimeError(f"无法获取 {symbol} 的核心基本面数据")

        info_map = _info_map(info)
        name = (
            resolved_name
            or _read_info(info_map, "股票简称", "名称")
            or self._lookup_name_for_symbol(normalized_symbol, warnings=warnings)
            or code
        )
        industry = _read_info(info_map, "行业", "所属行业")
        latest_indicator = _latest_row(indicator, date_columns=("日期", "REPORT_DATE"))
        profit_rows = _sorted_rows(profit, date_columns=("REPORT_DATE", "日期"))
        latest_profit = profit_rows[0] if profit_rows else {}
        previous_profit = _previous_comparable_row(profit_rows, latest_profit)
        trend = _profit_trend(profit_rows[: self._report_quarters])
        if len(trend) < self._report_quarters:
            warnings.append(
                f"成长性历史数据不足：仅获取到{len(trend)}期，少于配置的{self._report_quarters}期。"
            )
        latest_balance = _latest_row(balance, date_columns=("REPORT_DATE", "日期"))
        previous_balance = _previous_comparable_row(balance, latest_balance)
        latest_cashflow = _latest_row(cashflow, date_columns=("REPORT_DATE", "日期"))

        net_profit = _read_metric(latest_profit, "PARENT_NETPROFIT", "NETPROFIT")
        revenue = _read_metric(latest_profit, "TOTAL_OPERATE_INCOME", "OPERATE_INCOME")
        previous_revenue = _read_metric(
            previous_profit,
            "TOTAL_OPERATE_INCOME",
            "OPERATE_INCOME",
        )
        previous_net_profit = _read_metric(previous_profit, "PARENT_NETPROFIT", "NETPROFIT")
        operating_cashflow = _read_metric(
            latest_cashflow,
            "NETCASH_OPERATE",
            "N_OPERATE_A",
        )
        if operating_cashflow is None:
            warnings.append("经营现金流数据不足，现金流质量和DCF仅能部分评估。")
        capex = abs(_read_metric(latest_cashflow, "CONSTRUCT_LONG_ASSET") or 0.0)
        free_cashflow = (
            operating_cashflow - capex if operating_cashflow is not None else None
        )
        debt_to_asset = _ratio(
            _read_metric(latest_balance, "TOTAL_LIABILITIES"),
            _read_metric(latest_balance, "TOTAL_ASSETS"),
        )
        operating_cashflow_to_net_profit = _ratio(operating_cashflow, net_profit)
        non_recurring_quality = _ratio(
            _latest_abstract_metric(abstract, "扣非净利润"),
            _latest_abstract_metric(abstract, "归母净利润"),
        )
        revenue_growth = _growth_rate(revenue, previous_revenue)
        net_profit_growth = _growth_rate(net_profit, previous_net_profit)

        financial_quality = {
            "operatingCashFlowToNetProfit": _round_optional(operating_cashflow_to_net_profit),
            "debtToAsset": _round_optional(debt_to_asset),
            "nonRecurringProfitQuality": _round_optional(non_recurring_quality),
            "freeCashFlow": _round_optional(free_cashflow),
        }
        profitability = {
            "grossMargin": _round_optional(_read_metric(latest_indicator, "销售毛利率(%)")),
            "netMargin": _round_optional(_read_metric(latest_indicator, "销售净利率(%)")),
            "roe": _round_optional(_read_metric(latest_indicator, "净资产收益率(%)")),
            "roic": _round_optional(_read_metric(latest_indicator, "投入资本回报率(%)", "ROIC")),
        }
        growth = {
            "revenueGrowth": _round_optional(revenue_growth),
            "netProfitGrowth": _round_optional(net_profit_growth),
            "quartersReviewed": len(trend),
            "quartersConfigured": self._report_quarters,
            "trend": trend,
        }
        valuation = {
            "pe": _round_optional(_read_info_number(info_map, "市盈率", "市盈率TTM", "PE")),
            "pb": _round_optional(_read_info_number(info_map, "市净率", "PB")),
            "ps": _round_optional(_read_info_number(info_map, "市销率", "PS")),
            "marketCap": _round_optional(_read_info_number(info_map, "总市值", "总市值(元)")),
        }
        if all(value is None for value in valuation.values()):
            warnings.append("估值数据不足：PE/PB/PS/市值均不可用。")
        risk_flags = _build_risk_flags(
            financial_quality=financial_quality,
            profitability=profitability,
            growth=growth,
            latest_balance=latest_balance,
            previous_balance=previous_balance,
            revenue_growth=revenue_growth,
        )
        dcf = simple_dcf(
            fcf_base=free_cashflow,
            growth_rate=0.05,
            terminal_growth=0.02,
            wacc=0.10,
        )
        if not dcf["calculated"]:
            warnings.append(f"DCF未计算：{dcf['warning']}")

        peer_comparison = self._build_peer_comparison(
            symbol=normalized_symbol,
            industry=industry,
            peer_symbols=peer_symbols,
            warnings=warnings,
        )
        scorecard = _build_scorecard(
            financial_quality=financial_quality,
            profitability=profitability,
            growth=growth,
            valuation=valuation,
            risk_flags=risk_flags,
            dcf=dcf,
        )
        conclusion = _build_conclusion(name=name, scorecard=scorecard, risk_flags=risk_flags)
        as_of = (
            _read_row_string(latest_indicator, "日期")
            or _read_row_string(latest_profit, "REPORT_DATE")
            or datetime.now(UTC).date().isoformat()
        )

        return FundamentalAnalysisReport(
            symbol=normalized_symbol,
            name=name,
            asOf=as_of[:10],
            industry=industry,
            dataCoverage={
                "provider": "akshare",
                "quarters": len(trend),
                "quartersConfigured": self._report_quarters,
                "hasIncomeStatement": not profit.empty,
                "hasBalanceSheet": not balance.empty,
                "hasCashFlowStatement": not cashflow.empty,
            },
            companyProfile={
                "name": name,
                "symbol": normalized_symbol,
                "industry": industry,
                "businessModel": f"A股上市公司，行业归属：{industry or '未知行业'}",
            },
            financialQuality=financial_quality,
            profitability=profitability,
            growth=growth,
            valuation=valuation,
            peerComparison=peer_comparison,
            dcf=dcf,
            riskFlags=risk_flags,
            scorecard=scorecard,
            conclusionZh=conclusion,
            followUpWatchlist=[
                "后续跟踪最新季报中营收、净利润与经营现金流的匹配度",
                "关注估值相对同行和历史区间的变化",
                "结合公告和行业政策变化复核核心风险",
            ],
            warnings=warnings,
            disclaimer=_DISCLAIMER,
        )

    def _resolve_symbol(self, raw_symbol: str) -> tuple[str, str | None]:
        try:
            return normalize_a_share_symbol(raw_symbol), None
        except ValueError:
            lookup = self._client.search_a_share_code_name()
            normalized_query = raw_symbol.strip()
            for _, row in lookup.iterrows():
                name = str(row.get("name") or row.get("名称") or "").strip()
                code = str(row.get("code") or row.get("代码") or "").strip()
                if normalized_query and normalized_query in {name, code}:
                    return normalize_a_share_symbol(code), name
            raise ValueError(f"无法识别 A 股标的：{raw_symbol}") from None

    def _safe_frame(
        self,
        fetcher,
        *,
        warnings: list[str],
        label: str,
    ) -> pd.DataFrame:
        try:
            frame = fetcher()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("%s data fetch failed", label, exc_info=exc)
            warnings.append(f"{label}数据暂不可用。")
            return pd.DataFrame()
        if not isinstance(frame, pd.DataFrame):
            warnings.append(f"{label}数据格式异常。")
            return pd.DataFrame()
        if frame.empty:
            warnings.append(f"{label}数据为空。")
            return pd.DataFrame()
        return frame

    def _lookup_name_for_symbol(
        self,
        symbol: str,
        *,
        warnings: list[str],
    ) -> str | None:
        try:
            lookup = self._client.search_a_share_code_name()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("stock name lookup failed", exc_info=exc)
            warnings.append("股票名称查询暂不可用。")
            return None
        own_code = _symbol_code(symbol)
        for _, row in lookup.iterrows():
            code = str(row.get("code") or row.get("代码") or "").strip()
            name = str(row.get("name") or row.get("名称") or "").strip()
            if code == own_code and name:
                return name
        return None

    def _build_peer_comparison(
        self,
        *,
        symbol: str,
        industry: str | None,
        peer_symbols: Sequence[str] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        if peer_symbols:
            peers: list[dict[str, Any]] = []
            for peer_symbol in peer_symbols[: self._max_peers]:
                try:
                    peers.append({"symbol": normalize_a_share_symbol(peer_symbol)})
                except ValueError:
                    warnings.append(f"同行标的无效，已跳过：{peer_symbol}")
            return {
                "inferred": False,
                "industry": industry,
                "peers": peers,
            }
        if not industry:
            warnings.append("缺少行业信息，无法自动推断同行。")
            return {"inferred": True, "industry": None, "peers": []}
        try:
            frame = self._client.stock_board_industry_cons(industry)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"同行数据不可用：{exc}")
            return {"inferred": True, "industry": industry, "peers": []}
        peers: list[dict[str, Any]] = []
        own_code = _symbol_code(symbol)
        if not frame.empty:
            sort_column = _first_existing_column(frame, ("总市值", "成交额", "最新价"))
            if sort_column:
                frame = frame.assign(
                    _sort_value=frame[sort_column].map(_to_float).fillna(0.0)
                ).sort_values("_sort_value", ascending=False)
            for _, row in frame.iterrows():
                peer_code = str(row.get("代码") or row.get("code") or "").strip()
                if not peer_code or peer_code == own_code:
                    continue
                try:
                    normalized_peer_code = normalize_a_share_symbol(peer_code)
                except ValueError:
                    warnings.append(f"同行成分代码无效，已跳过：{peer_code}")
                    continue
                peers.append(
                    {
                        "symbol": normalized_peer_code,
                        "name": str(row.get("名称") or row.get("name") or "").strip(),
                        "marketCap": _round_optional(_to_float(row.get("总市值"))),
                    }
                )
                if len(peers) >= self._max_peers:
                    break
        if not peers:
            warnings.append("未找到可用同行样本。")
        return {"inferred": True, "industry": industry, "peers": peers}


def build_fundamental_analysis_service_from_env(
    *,
    environ: Mapping[str, str] | None = None,
) -> FundamentalAnalysisService:
    env = build_env_values(environ=environ)
    provider = (
        read_env(env, "FINANCEHUB_FUNDAMENTAL_ANALYSIS_PROVIDER")
        or _DEFAULT_PROVIDER
    ).lower()
    if provider != "akshare":
        return FundamentalAnalysisService(client=None)
    return FundamentalAnalysisService(
        client=AkShareFundamentalDataClient(),
        max_peers=_clamp_int(
            read_env(env, "FINANCEHUB_FUNDAMENTAL_ANALYSIS_MAX_PEERS"),
            default=_DEFAULT_MAX_PEERS,
            minimum=0,
            maximum=10,
        ),
        report_quarters=_clamp_int(
            read_env(env, "FINANCEHUB_FUNDAMENTAL_ANALYSIS_REPORT_QUARTERS"),
            default=_DEFAULT_REPORT_QUARTERS,
            minimum=1,
            maximum=16,
        ),
    )


def normalize_a_share_symbol(raw_symbol: str) -> str:
    value = raw_symbol.strip().upper()
    if not value:
        raise ValueError("symbol is required")
    if "." in value:
        code, suffix = value.split(".", 1)
        if len(code) == 6 and code.isdigit() and suffix in {"SH", "SZ"}:
            return f"{code}.{suffix}"
    if value.startswith(("SH", "SZ")) and len(value) == 8 and value[2:].isdigit():
        return f"{value[2:]}.{value[:2]}"
    if len(value) == 6 and value.isdigit():
        suffix = "SH" if value.startswith(("5", "6", "9")) else "SZ"
        return f"{value}.{suffix}"
    raise ValueError(f"invalid A-share symbol: {raw_symbol}")


def simple_dcf(
    *,
    fcf_base: float | None,
    growth_rate: float,
    terminal_growth: float,
    wacc: float,
    years: int = 10,
) -> dict[str, Any]:
    if fcf_base is None or not math_is_finite(fcf_base) or fcf_base <= 0:
        return {
            "calculated": False,
            "fairValue": None,
            "assumptions": {
                "growthRate": growth_rate,
                "terminalGrowth": terminal_growth,
                "wacc": wacc,
                "years": years,
            },
            "warning": "核心自由现金流或经营现金流缺失/为负",
        }
    if wacc <= terminal_growth:
        return {
            "calculated": False,
            "fairValue": None,
            "assumptions": {
                "growthRate": growth_rate,
                "terminalGrowth": terminal_growth,
                "wacc": wacc,
                "years": years,
            },
            "warning": "wacc 必须大于 terminal_growth",
        }
    present_values = [
        fcf_base * (1 + growth_rate) ** year / (1 + wacc) ** year
        for year in range(1, years + 1)
    ]
    terminal_value = (
        fcf_base
        * (1 + growth_rate) ** years
        * (1 + terminal_growth)
        / (wacc - terminal_growth)
    )
    terminal_present_value = terminal_value / (1 + wacc) ** years
    fair_value = sum(present_values) + terminal_present_value
    return {
        "calculated": True,
        "fairValue": round(fair_value, 2),
        "assumptions": {
            "growthRate": growth_rate,
            "terminalGrowth": terminal_growth,
            "wacc": wacc,
            "years": years,
        },
        "summaryZh": "使用简化DCF估算企业价值，结果对增长率和折现率高度敏感。",
    }


def _symbol_code(symbol: str) -> str:
    return normalize_a_share_symbol(symbol).split(".", 1)[0]


def _em_symbol(symbol: str) -> str:
    normalized = normalize_a_share_symbol(symbol)
    code, suffix = normalized.split(".", 1)
    return f"{suffix}{code}"


def _info_map(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    result: dict[str, Any] = {}
    for _, row in frame.iterrows():
        key = str(row.get("item") or row.get("项目") or row.get("name") or "").strip()
        if key:
            result[key] = row.get("value")
    return result


def _read_info(info: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = info.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _read_info_number(info: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _to_float(info.get(key))
        if value is not None:
            return value
    return None


def _latest_row(frame: pd.DataFrame, *, date_columns: Sequence[str]) -> dict[str, Any]:
    rows = _sorted_rows(frame, date_columns=date_columns)
    return rows[0] if rows else {}


def _sorted_rows(frame: pd.DataFrame, *, date_columns: Sequence[str]) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    date_column = _first_existing_column(frame, date_columns)
    if not date_column:
        return [row.to_dict() for _, row in frame.iterrows()]
    sorted_frame = frame.copy()
    sorted_frame["_date_sort"] = sorted_frame[date_column].astype(str)
    return [
        row.to_dict()
        for _, row in sorted_frame.sort_values("_date_sort", ascending=False).iterrows()
    ]


def _previous_comparable_row(
    rows_or_frame: Sequence[dict[str, Any]] | pd.DataFrame,
    latest_row: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(rows_or_frame, pd.DataFrame):
        rows = _sorted_rows(rows_or_frame, date_columns=("REPORT_DATE", "日期"))
    else:
        rows = list(rows_or_frame)
    if not rows or not latest_row:
        return {}
    latest_date = str(latest_row.get("REPORT_DATE") or latest_row.get("日期") or "")
    same_quarter_row = _same_quarter_prior_year_row(rows, latest_date)
    if same_quarter_row:
        return same_quarter_row
    earlier_rows = [
        row
        for row in rows
        if str(row.get("REPORT_DATE") or row.get("日期") or "") < latest_date
    ]
    return earlier_rows[0] if earlier_rows else {}


def _same_quarter_prior_year_row(
    rows: Sequence[dict[str, Any]],
    latest_date: str,
) -> dict[str, Any]:
    if len(latest_date) < 10 or not latest_date[:4].isdigit():
        return {}
    prior_year_date = f"{int(latest_date[:4]) - 1}{latest_date[4:10]}"
    for row in rows:
        row_date = str(row.get("REPORT_DATE") or row.get("日期") or "")[:10]
        if row_date == prior_year_date:
            return row
    return {}


def _profit_trend(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    trend: list[dict[str, Any]] = []
    for row in rows:
        period = str(row.get("REPORT_DATE") or row.get("日期") or "")[:10]
        if not period:
            continue
        trend.append(
            {
                "period": period,
                "revenue": _round_optional(
                    _read_metric(row, "TOTAL_OPERATE_INCOME", "OPERATE_INCOME")
                ),
                "netProfit": _round_optional(
                    _read_metric(row, "PARENT_NETPROFIT", "NETPROFIT")
                ),
            }
        )
    return trend


def _read_metric(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _latest_abstract_metric(frame: pd.DataFrame, metric_name: str) -> float | None:
    if frame.empty or "指标" not in frame.columns:
        return None
    matching = frame[frame["指标"].astype(str) == metric_name]
    if matching.empty:
        return None
    row = matching.iloc[0].to_dict()
    date_columns = sorted(
        [
            str(column)
            for column in frame.columns
            if str(column).isdigit() and len(str(column)) == 8
        ],
        reverse=True,
    )
    for column in date_columns:
        value = _to_float(row.get(column))
        if value is not None:
            return value
    return None


def _read_row_string(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return str(value) if value not in (None, "") else None


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _build_risk_flags(
    *,
    financial_quality: dict[str, Any],
    profitability: dict[str, Any],
    growth: dict[str, Any],
    latest_balance: dict[str, Any],
    previous_balance: dict[str, Any],
    revenue_growth: float | None,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    ocf_to_profit = financial_quality.get("operatingCashFlowToNetProfit")
    debt_to_asset = financial_quality.get("debtToAsset")
    free_cashflow = financial_quality.get("freeCashFlow")
    if isinstance(ocf_to_profit, (int, float)) and ocf_to_profit < 0.8:
        flags.append({"code": "low_profit_cash_conversion", "message": "经营现金流/净利润低于0.8"})
    if isinstance(free_cashflow, (int, float)) and free_cashflow <= 0:
        flags.append({"code": "weak_operating_cash_flow", "message": "自由现金流为负或偏弱"})
    if isinstance(debt_to_asset, (int, float)) and debt_to_asset > 0.6:
        flags.append({"code": "high_debt_to_asset", "message": "资产负债率高于60%"})
    receivable_growth = _growth_rate(
        _read_metric(latest_balance, "ACCOUNTS_RECE"),
        _read_metric(previous_balance, "ACCOUNTS_RECE"),
    )
    if (
        receivable_growth is not None
        and revenue_growth is not None
        and receivable_growth > revenue_growth + 0.2
    ):
        flags.append(
            {
                "code": "receivables_growth_outpaces_revenue",
                "message": "应收账款增速明显高于营收增速",
            }
        )
    inventory_growth = _growth_rate(
        _read_metric(latest_balance, "INVENTORY"),
        _read_metric(previous_balance, "INVENTORY"),
    )
    if (
        inventory_growth is not None
        and revenue_growth is not None
        and inventory_growth > revenue_growth + 0.2
    ):
        flags.append({"code": "inventory_pressure", "message": "存货增长偏快"})
    goodwill = _read_metric(latest_balance, "GOODWILL")
    net_assets = (
        (_read_metric(latest_balance, "TOTAL_ASSETS") or 0.0)
        - (_read_metric(latest_balance, "TOTAL_LIABILITIES") or 0.0)
    )
    if goodwill is not None and net_assets > 0 and goodwill / net_assets > 0.3:
        flags.append({"code": "goodwill_pressure", "message": "商誉占净资产比例偏高"})
    gross_margin = profitability.get("grossMargin")
    if isinstance(gross_margin, (int, float)) and gross_margin < 20:
        flags.append({"code": "low_gross_margin", "message": "毛利率偏低"})
    return flags


def _build_scorecard(
    *,
    financial_quality: dict[str, Any],
    profitability: dict[str, Any],
    growth: dict[str, Any],
    valuation: dict[str, Any],
    risk_flags: list[dict[str, Any]],
    dcf: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    financial_score = _score_threshold(
        financial_quality.get("operatingCashFlowToNetProfit"),
        high=1.0,
        medium=0.8,
    )
    profitability_score = _score_threshold(profitability.get("roe"), high=20, medium=10)
    growth_score = _score_threshold(growth.get("revenueGrowth"), high=0.15, medium=0.05)
    pe = valuation.get("pe")
    valuation_score = 3 if pe is None else 4 if pe <= 25 else 3 if pe <= 40 else 2
    risk_score = max(1, 5 - min(len(risk_flags), 4))
    dcf_score = 4 if dcf.get("calculated") else 3
    composite = round(
        (
            financial_score
            + profitability_score
            + growth_score
            + valuation_score
            + risk_score
            + dcf_score
        )
        / 6,
        1,
    )
    return {
        "财务质量": {"score": financial_score, "summary": "现金流、负债与利润质量综合评分"},
        "盈利能力": {"score": profitability_score, "summary": "毛利率、净利率与ROE综合评分"},
        "成长性": {"score": growth_score, "summary": "营收和净利润趋势评分"},
        "估值合理性": {"score": valuation_score, "summary": "PE/PB与现金流估值参考评分"},
        "风险水平": {"score": risk_score, "summary": "财报红旗越少得分越高"},
        "综合": {"score": composite, "summary": "基本面综合评分"},
    }


def _score_threshold(value: object, *, high: float, medium: float) -> int:
    if not isinstance(value, (int, float)):
        return 3
    if value >= high:
        return 5
    if value >= medium:
        return 4
    if value >= 0:
        return 3
    return 2


def _build_conclusion(
    *,
    name: str,
    scorecard: dict[str, dict[str, Any]],
    risk_flags: list[dict[str, Any]],
) -> str:
    composite = scorecard["综合"]["score"]
    if composite >= 4 and not risk_flags:
        stance = "基本面质量较强，值得继续重点跟踪"
    elif composite >= 3:
        stance = "基本面具备一定支撑，但需要结合估值和风险继续验证"
    else:
        stance = "基本面压力较多，需谨慎评估"
    return f"{name}：{stance}。本结论基于公开财务数据和简化模型，需结合最新公告复核。"


def _first_existing_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("%", "")
        if not cleaned or cleaned in {"-", "--", "nan", "None"}:
            return None
        value = cleaned
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math_is_finite(number) else None


def _round_optional(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def math_is_finite(value: float) -> bool:
    try:
        return value == value and value not in {float("inf"), float("-inf")}
    except TypeError:
        return False


def _clamp_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
