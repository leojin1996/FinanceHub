from __future__ import annotations

from financehub_market_api.models import RiskProfile
from financehub_market_api.recommendation.schemas import AllocationPlan

PROFILE_LABELS_ZH: dict[RiskProfile, str] = {
    "conservative": "保守型",
    "stable": "稳健型",
    "balanced": "平衡型",
    "growth": "成长型",
    "aggressive": "进取型",
}

PROFILE_LABELS_EN: dict[RiskProfile, str] = {
    "conservative": "Conservative",
    "stable": "Stable",
    "balanced": "Balanced",
    "growth": "Growth",
    "aggressive": "Aggressive",
}

PROFILE_MARKET_SUMMARY_ZH: dict[RiskProfile, str] = {
    "conservative": "当前市场更适合以低波动资产打底，权益类只适合作为非常轻的补充。",
    "stable": "当前市场适合以稳健资产打底，并用少量权益提升收益弹性。",
    "balanced": "当前市场更适合稳健资产与权益增强搭配，控制整体波动。",
    "growth": "当前市场可适度提高权益参与度，但仍应保留稳健资产缓冲。",
    "aggressive": "当前市场允许更高权益参与度，但仍需保留一定防守仓位。",
}

PROFILE_MARKET_SUMMARY_EN: dict[RiskProfile, str] = {
    "conservative": "Current conditions favor low-volatility assets as the core, with only a very light equity sleeve.",
    "stable": "Current conditions favor stable assets as the base, with a small equity sleeve for added upside.",
    "balanced": "Current conditions support a mix of steady assets and selective equity exposure while controlling overall volatility.",
    "growth": "Current conditions allow moderately higher equity participation, while keeping defensive assets as ballast.",
    "aggressive": "Current conditions allow a higher equity weight, but still call for some defensive ballast.",
}

BASE_ALLOCATIONS: dict[RiskProfile, AllocationPlan] = {
    "conservative": AllocationPlan(fund=25, wealth_management=70, stock=5),
    "stable": AllocationPlan(fund=35, wealth_management=50, stock=15),
    "balanced": AllocationPlan(fund=45, wealth_management=35, stock=20),
    "growth": AllocationPlan(fund=45, wealth_management=20, stock=35),
    "aggressive": AllocationPlan(fund=35, wealth_management=15, stock=50),
}

AGGRESSIVE_ALLOCATIONS: dict[RiskProfile, AllocationPlan] = {
    "conservative": AllocationPlan(fund=30, wealth_management=55, stock=15),
    "stable": AllocationPlan(fund=35, wealth_management=35, stock=30),
    "balanced": AllocationPlan(fund=40, wealth_management=25, stock=35),
    "growth": AllocationPlan(fund=35, wealth_management=15, stock=50),
    "aggressive": AllocationPlan(fund=30, wealth_management=10, stock=60),
}
