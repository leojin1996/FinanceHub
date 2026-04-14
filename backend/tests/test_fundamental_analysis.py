from __future__ import annotations

import math

import pandas as pd

from financehub_market_api.fundamental_analysis import (
    FundamentalAnalysisService,
    build_fundamental_analysis_service_from_env,
    normalize_a_share_symbol,
    simple_dcf,
)


class _FakeFundamentalClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def search_a_share_code_name(self) -> pd.DataFrame:
        self.calls.append(("search_a_share_code_name", None))
        return pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "300750", "name": "宁德时代"},
                {"code": "000858", "name": "五粮液"},
            ]
        )

    def stock_individual_info(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_individual_info", symbol))
        return pd.DataFrame(
            [
                {"item": "股票代码", "value": "600519"},
                {"item": "股票简称", "value": "贵州茅台"},
                {"item": "行业", "value": "酿酒行业"},
                {"item": "总市值", "value": "1810000000000"},
                {"item": "市盈率", "value": "22.5"},
                {"item": "市净率", "value": "8.1"},
            ]
        )

    def stock_financial_analysis_indicator(
        self,
        symbol: str,
        *,
        start_year: str,
    ) -> pd.DataFrame:
        self.calls.append(("stock_financial_analysis_indicator", (symbol, start_year)))
        return pd.DataFrame(
            [
                {
                    "日期": "2025-09-30",
                    "销售毛利率(%)": "91.2",
                    "销售净利率(%)": "52.1",
                    "净资产收益率(%)": "24.8",
                    "资产负债率(%)": "19.5",
                    "每股经营性现金流(元)": "41.5",
                },
                {
                    "日期": "2025-06-30",
                    "销售毛利率(%)": "90.4",
                    "销售净利率(%)": "51.0",
                    "净资产收益率(%)": "18.2",
                    "资产负债率(%)": "20.0",
                    "每股经营性现金流(元)": "27.1",
                },
            ]
        )

    def stock_financial_abstract(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_financial_abstract", symbol))
        return pd.DataFrame(
            [
                {
                    "选项": "常用指标",
                    "指标": "营业总收入",
                    "20250930": 130.0,
                    "20250630": 90.0,
                    "20250331": 45.0,
                    "20241231": 170.0,
                },
                {
                    "选项": "常用指标",
                    "指标": "归母净利润",
                    "20250930": 65.0,
                    "20250630": 45.0,
                    "20250331": 22.0,
                    "20241231": 85.0,
                },
                {
                    "选项": "常用指标",
                    "指标": "扣非净利润",
                    "20250930": 62.0,
                    "20250630": 43.0,
                    "20250331": 21.0,
                    "20241231": 80.0,
                },
            ]
        )

    def stock_profit_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_profit_sheet_by_report", symbol))
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "TOTAL_OPERATE_INCOME": 130.0,
                    "PARENT_NETPROFIT": 65.0,
                },
                {
                    "REPORT_DATE": "2024-09-30",
                    "TOTAL_OPERATE_INCOME": 100.0,
                    "PARENT_NETPROFIT": 50.0,
                },
            ]
        )

    def stock_balance_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_balance_sheet_by_report", symbol))
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "TOTAL_ASSETS": 300.0,
                    "TOTAL_LIABILITIES": 58.5,
                    "ACCOUNTS_RECE": 4.0,
                    "INVENTORY": 38.0,
                    "GOODWILL": 0.0,
                },
                {
                    "REPORT_DATE": "2024-09-30",
                    "TOTAL_ASSETS": 280.0,
                    "TOTAL_LIABILITIES": 62.0,
                    "ACCOUNTS_RECE": 3.5,
                    "INVENTORY": 35.0,
                    "GOODWILL": 0.0,
                },
            ]
        )

    def stock_cash_flow_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_cash_flow_sheet_by_report", symbol))
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "NETCASH_OPERATE": 72.0,
                    "CONSTRUCT_LONG_ASSET": 6.0,
                },
                {
                    "REPORT_DATE": "2024-09-30",
                    "NETCASH_OPERATE": 54.0,
                    "CONSTRUCT_LONG_ASSET": 5.0,
                },
            ]
        )

    def stock_board_industry_cons(self, industry: str) -> pd.DataFrame:
        self.calls.append(("stock_board_industry_cons", industry))
        return pd.DataFrame(
            [
                {"代码": "600519", "名称": "贵州茅台", "总市值": 1810000000000},
                {"代码": "000858", "名称": "五粮液", "总市值": 520000000000},
                {"代码": "000568", "名称": "泸州老窖", "总市值": 220000000000},
                {"代码": "600809", "名称": "山西汾酒", "总市值": 190000000000},
            ]
        )


class _RiskyFundamentalClient(_FakeFundamentalClient):
    def stock_financial_analysis_indicator(
        self,
        symbol: str,
        *,
        start_year: str,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2025-09-30",
                    "销售毛利率(%)": "18.0",
                    "销售净利率(%)": "3.0",
                    "净资产收益率(%)": "4.0",
                    "资产负债率(%)": "72.0",
                }
            ]
        )

    def stock_balance_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "TOTAL_ASSETS": 300.0,
                    "TOTAL_LIABILITIES": 216.0,
                    "ACCOUNTS_RECE": 80.0,
                    "INVENTORY": 90.0,
                    "GOODWILL": 70.0,
                },
                {
                    "REPORT_DATE": "2024-09-30",
                    "TOTAL_ASSETS": 260.0,
                    "TOTAL_LIABILITIES": 180.0,
                    "ACCOUNTS_RECE": 20.0,
                    "INVENTORY": 30.0,
                    "GOODWILL": 60.0,
                },
            ]
        )

    def stock_cash_flow_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "NETCASH_OPERATE": -6.0,
                    "CONSTRUCT_LONG_ASSET": 10.0,
                }
            ]
        )


class _MissingProfileFundamentalClient(_FakeFundamentalClient):
    def stock_individual_info(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_individual_info", symbol))
        return pd.DataFrame()


class _QuarterTrendFundamentalClient(_FakeFundamentalClient):
    def stock_profit_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_profit_sheet_by_report", symbol))
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "TOTAL_OPERATE_INCOME": 130.0,
                    "PARENT_NETPROFIT": 65.0,
                },
                {
                    "REPORT_DATE": "2025-06-30",
                    "TOTAL_OPERATE_INCOME": 125.0,
                    "PARENT_NETPROFIT": 61.0,
                },
                {
                    "REPORT_DATE": "2024-09-30",
                    "TOTAL_OPERATE_INCOME": 100.0,
                    "PARENT_NETPROFIT": 50.0,
                },
                {
                    "REPORT_DATE": "2024-06-30",
                    "TOTAL_OPERATE_INCOME": 90.0,
                    "PARENT_NETPROFIT": 42.0,
                },
            ]
        )


class _YoYOnlyCashFlowClient(_FakeFundamentalClient):
    def stock_cash_flow_sheet_by_report(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_cash_flow_sheet_by_report", symbol))
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-09-30",
                    "NETCASH_OPERATE_YOY": "50%",
                    "CONSTRUCT_LONG_ASSET": 6.0,
                }
            ]
        )


class _NoValuationClient(_FakeFundamentalClient):
    def stock_individual_info(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_individual_info", symbol))
        return pd.DataFrame(
            [
                {"item": "股票代码", "value": "600519"},
                {"item": "股票简称", "value": "贵州茅台"},
                {"item": "行业", "value": "酿酒行业"},
            ]
        )


class _EmptyAbstractClient(_FakeFundamentalClient):
    def stock_financial_abstract(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_financial_abstract", symbol))
        return pd.DataFrame()


class _SensitiveExceptionClient(_FakeFundamentalClient):
    def stock_individual_info(self, symbol: str) -> pd.DataFrame:
        self.calls.append(("stock_individual_info", symbol))
        raise RuntimeError("https://internal.proxy.example/token=secret")


def test_normalize_a_share_symbol_accepts_common_code_formats() -> None:
    assert normalize_a_share_symbol("600519") == "600519.SH"
    assert normalize_a_share_symbol("600519.SH") == "600519.SH"
    assert normalize_a_share_symbol("SH600519") == "600519.SH"
    assert normalize_a_share_symbol("300750") == "300750.SZ"


def test_fundamental_analysis_service_resolves_chinese_name_and_builds_full_report() -> None:
    client = _FakeFundamentalClient()
    service = FundamentalAnalysisService(client=client, max_peers=3, report_quarters=8)

    report = service.analyze(symbol="贵州茅台")

    assert report.symbol == "600519.SH"
    assert report.name == "贵州茅台"
    assert report.industry == "酿酒行业"
    assert report.dataCoverage["quarters"] == 2
    assert report.companyProfile["businessModel"] == "A股上市公司，行业归属：酿酒行业"
    assert report.financialQuality["operatingCashFlowToNetProfit"] == 1.11
    assert report.financialQuality["debtToAsset"] == 0.2
    assert report.profitability["grossMargin"] == 91.2
    assert report.profitability["roe"] == 24.8
    assert report.growth["revenueGrowth"] == 0.3
    assert report.valuation["pe"] == 22.5
    assert report.peerComparison["peers"][0]["symbol"] == "000858.SZ"
    assert report.peerComparison["inferred"] is True
    assert report.dcf["calculated"] is True
    assert report.dcf["fairValue"] > 0
    assert report.scorecard["综合"]["score"] >= 4
    assert "贵州茅台" in report.conclusionZh
    assert report.followUpWatchlist
    assert "仅供参考" in report.disclaimer


def test_fundamental_analysis_service_uses_explicit_peer_symbols() -> None:
    service = FundamentalAnalysisService(client=_FakeFundamentalClient(), max_peers=5)

    report = service.analyze(symbol="600519", peer_symbols=["000858", "300750.SZ"])

    assert report.peerComparison["inferred"] is False
    assert [peer["symbol"] for peer in report.peerComparison["peers"]] == [
        "000858.SZ",
        "300750.SZ",
    ]


def test_fundamental_analysis_service_uses_code_lookup_when_profile_name_missing() -> None:
    report = FundamentalAnalysisService(client=_MissingProfileFundamentalClient()).analyze(
        symbol="600519",
        peer_symbols=["000858"],
    )

    assert report.name == "贵州茅台"
    assert report.companyProfile["name"] == "贵州茅台"


def test_fundamental_analysis_service_prefers_same_quarter_yoy_growth() -> None:
    report = FundamentalAnalysisService(
        client=_QuarterTrendFundamentalClient(),
        report_quarters=4,
    ).analyze(symbol="600519", peer_symbols=["000858"])

    assert report.growth["revenueGrowth"] == 0.3
    assert report.growth["netProfitGrowth"] == 0.3
    assert report.growth["quartersReviewed"] == 4
    assert report.growth["trend"][0] == {
        "period": "2025-09-30",
        "revenue": 130.0,
        "netProfit": 65.0,
    }


def test_fundamental_analysis_service_does_not_treat_cash_flow_yoy_as_amount() -> None:
    report = FundamentalAnalysisService(client=_YoYOnlyCashFlowClient()).analyze(
        symbol="600519",
        peer_symbols=["000858"],
    )

    assert report.financialQuality["operatingCashFlowToNetProfit"] is None
    assert report.financialQuality["freeCashFlow"] is None
    assert report.dcf["calculated"] is False
    assert any("现金流" in warning for warning in report.warnings)


def test_fundamental_analysis_service_skips_invalid_peer_symbols_with_warning() -> None:
    report = FundamentalAnalysisService(client=_FakeFundamentalClient()).analyze(
        symbol="600519",
        peer_symbols=["000858", "BAD"],
    )

    assert report.peerComparison["peers"] == [{"symbol": "000858.SZ"}]
    assert any("同行标的无效" in warning for warning in report.warnings)


def test_fundamental_analysis_service_warns_when_valuation_data_is_missing() -> None:
    report = FundamentalAnalysisService(client=_NoValuationClient()).analyze(
        symbol="600519",
        peer_symbols=["000858"],
    )

    assert all(value is None for value in report.valuation.values())
    assert any("估值数据不足" in warning for warning in report.warnings)


def test_fundamental_analysis_service_warns_on_empty_source_payloads() -> None:
    report = FundamentalAnalysisService(client=_EmptyAbstractClient()).analyze(
        symbol="600519",
        peer_symbols=["000858"],
    )

    assert any("财务摘要数据为空" in warning for warning in report.warnings)


def test_fundamental_analysis_service_sanitizes_provider_exception_warnings() -> None:
    report = FundamentalAnalysisService(client=_SensitiveExceptionClient()).analyze(
        symbol="600519",
        peer_symbols=["000858"],
    )

    warning_text = "\n".join(report.warnings)
    assert "公司画像数据暂不可用" in warning_text
    assert "internal.proxy" not in warning_text
    assert "secret" not in warning_text


def test_fundamental_analysis_service_flags_financial_risks_and_skips_missing_dcf() -> None:
    report = FundamentalAnalysisService(client=_RiskyFundamentalClient()).analyze(
        symbol="600519"
    )

    risk_codes = {item["code"] for item in report.riskFlags}

    assert "weak_operating_cash_flow" in risk_codes
    assert "high_debt_to_asset" in risk_codes
    assert "receivables_growth_outpaces_revenue" in risk_codes
    assert "goodwill_pressure" in risk_codes
    assert "inventory_pressure" in risk_codes
    assert "low_profit_cash_conversion" in risk_codes
    assert report.dcf["calculated"] is False
    assert any("现金流" in warning for warning in report.warnings)


def test_simple_dcf_rejects_invalid_discount_assumptions() -> None:
    result = simple_dcf(
        fcf_base=100.0,
        growth_rate=0.05,
        terminal_growth=0.1,
        wacc=0.08,
    )

    assert result["calculated"] is False
    assert "wacc" in result["warning"]


def test_build_fundamental_analysis_service_from_env_uses_defaults() -> None:
    service = build_fundamental_analysis_service_from_env(
        environ={
            "FINANCEHUB_FUNDAMENTAL_ANALYSIS_PROVIDER": "akshare",
            "FINANCEHUB_FUNDAMENTAL_ANALYSIS_MAX_PEERS": "3",
            "FINANCEHUB_FUNDAMENTAL_ANALYSIS_REPORT_QUARTERS": "6",
        }
    )

    assert service._max_peers == 3
    assert service._report_quarters == 6
