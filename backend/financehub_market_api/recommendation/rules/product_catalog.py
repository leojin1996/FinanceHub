from __future__ import annotations

from financehub_market_api.recommendation.schemas import CandidateProduct

FUNDS: list[CandidateProduct] = [
    CandidateProduct(
        id="fund-001",
        category="fund",
        name_zh="中欧稳利债券A",
        name_en="Zhongou Steady Bond A",
        risk_level="R2",
        tags_zh=["低回撤", "债券底仓", "适合稳健增值"],
        tags_en=["Low drawdown", "Bond core", "Fits steady growth"],
        rationale_zh="作为组合底仓，波动较低，更适合用来承接稳健增值目标。",
        rationale_en="Works well as the portfolio core thanks to lower volatility and steadier return expectations.",
        liquidity="T+1",
    ),
    CandidateProduct(
        id="fund-002",
        category="fund",
        name_zh="交银双息平衡混合",
        name_en="BOCOM Dual Income Balanced",
        risk_level="R3",
        tags_zh=["股债平衡", "回撤可控", "增强收益弹性"],
        tags_en=["Balanced mix", "Controlled drawdown", "Adds upside"],
        rationale_zh="兼顾债券防守与权益增强，适合作为中间层配置。",
        rationale_en="Balances bond defense with equity upside and fits well as a middle-layer allocation.",
        liquidity="T+1",
    ),
]

WEALTH_MANAGEMENT: list[CandidateProduct] = [
    CandidateProduct(
        id="wm-001",
        category="wealth_management",
        name_zh="招银理财稳享90天",
        name_en="CMB Wealth Stable 90D",
        risk_level="R2",
        tags_zh=["短期限", "流动性友好", "稳健打底"],
        tags_en=["Short tenor", "Liquidity-friendly", "Stable base"],
        rationale_zh="适合承担组合的稳定底仓角色，同时兼顾一定流动性。",
        rationale_en="Fits the role of a stable base allocation while preserving reasonable liquidity.",
        liquidity="90天",
    ),
    CandidateProduct(
        id="wm-002",
        category="wealth_management",
        name_zh="工银理财安鑫固收增强",
        name_en="ICBC Wealth Fixed Income Plus",
        risk_level="R2",
        tags_zh=["固收增强", "净值平稳", "适合风险中低用户"],
        tags_en=["Fixed income plus", "Stable NAV", "Fits lower-risk users"],
        rationale_zh="在稳健理财底层上保留适度收益增强，更适合当前中约束推荐。",
        rationale_en="Adds modest upside on top of a stable wealth-management base and fits a moderated recommendation policy.",
        liquidity="开放式",
    ),
]

STOCKS: list[CandidateProduct] = [
    CandidateProduct(
        id="stock-001",
        category="stock",
        code="600036",
        name_zh="招商银行",
        name_en="China Merchants Bank",
        risk_level="R3",
        tags_zh=["高股息", "大盘蓝筹", "增强配置"],
        tags_en=["Dividend quality", "Large cap", "Satellite equity"],
        rationale_zh="作为增强配置，更偏向盈利稳定和股息特征，适合控制波动。",
        rationale_en="As a satellite equity holding, it leans on earnings stability and dividend quality to keep volatility more contained.",
    ),
    CandidateProduct(
        id="stock-002",
        category="stock",
        code="600900",
        name_zh="长江电力",
        name_en="Yangtze Power",
        risk_level="R3",
        tags_zh=["防御属性", "现金流稳健", "增强配置"],
        tags_en=["Defensive", "Stable cash flow", "Satellite equity"],
        rationale_zh="在权益部分里偏防御风格，可作为提高组合韧性的补充。",
        rationale_en="Brings a more defensive style within the equity sleeve and can improve portfolio resilience.",
    ),
]

RISK_NOTICE_ZH = [
    "理财非存款，基金和理财产品净值会随市场波动。",
    "股票部分仅适合作为增强配置，不宜替代稳健底仓。",
]

RISK_NOTICE_EN = [
    "Wealth-management products are not deposits, and fund or product NAVs may fluctuate with markets.",
    "The stock sleeve is intended only as an enhancing allocation and should not replace the stable core.",
]

AGGRESSIVE_OPTION_TITLES = ("进取型备选", "More aggressive option")
AGGRESSIVE_OPTION_SUBTITLES = (
    "如果你愿意承受更高波动，可参考这一增强版配置，但不作为默认推荐。",
    "If you are willing to accept higher volatility, this enhanced allocation can be considered, but it is not the default recommendation.",
)

DEFAULT_SUMMARY_SUBTITLE_ZH = "以稳健资产打底，再配置适量基金与股票增强收益弹性。"
DEFAULT_SUMMARY_SUBTITLE_EN = (
    "Build the base with steadier assets, then add selective funds and equities for measured upside."
)
