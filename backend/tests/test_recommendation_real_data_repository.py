from __future__ import annotations

from financehub_market_api.recommendation.repositories.real_data_adapters import (
    BondFundCandidateAdapter,
    MoneyFundWealthProxyAdapter,
)
from financehub_market_api.recommendation.repositories.real_data_repository import RealDataCandidateRepository
from financehub_market_api.recommendation.agents import AnthropicMultiAgentRuntime
from financehub_market_api.recommendation.orchestration import RecommendationOrchestrator
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.rules.product_catalog import FUNDS, STOCKS, WEALTH_MANAGEMENT
from financehub_market_api.recommendation.services import RecommendationService


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


def test_bond_fund_adapter_maps_public_rows_into_candidate_products() -> None:
    adapter = BondFundCandidateAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                }
            ]
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = adapter.list_candidates(user_profile)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "fund"
    assert candidate.id == "fund-001"
    assert candidate.code == "000001"
    assert candidate.name_zh == "稳健债券A"
    assert candidate.name_en == "稳健债券A"
    assert candidate.risk_level == "R2"


def test_money_fund_proxy_adapter_maps_public_rows_into_candidate_products() -> None:
    adapter = MoneyFundWealthProxyAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                }
            ]
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = adapter.list_candidates(user_profile)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "wealth_management"
    assert candidate.id == "wm-001"
    assert candidate.code == "511990"
    assert candidate.name_zh == "华宝添益"
    assert candidate.name_en == "华宝添益"
    assert candidate.risk_level == "R1"


def test_real_repository_falls_back_to_static_funds_on_adapter_failure() -> None:
    repository = RealDataCandidateRepository(
        fund_adapter=BondFundCandidateAdapter(fetcher=lambda: (_ for _ in ()).throw(RuntimeError("fund upstream down")))
    )

    user_profile = map_user_profile("balanced")
    candidates = repository.list_funds(user_profile)

    assert candidates == FUNDS


def test_real_repository_falls_back_to_static_wealth_on_adapter_failure() -> None:
    repository = RealDataCandidateRepository(
        wealth_adapter=MoneyFundWealthProxyAdapter(
            fetcher=lambda: (_ for _ in ()).throw(RuntimeError("money fund upstream down"))
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = repository.list_wealth_management(user_profile)

    assert candidates == WEALTH_MANAGEMENT


def test_real_repository_keeps_stock_candidate_selection_unchanged() -> None:
    repository = RealDataCandidateRepository()

    user_profile = map_user_profile("balanced")
    candidates = repository.list_stocks(user_profile)

    assert candidates == STOCKS


def test_domain_recommendation_service_keeps_api_compatible_payload_with_real_repository_default(
    monkeypatch,
) -> None:
    from financehub_market_api.recommendation.repositories import real_data_adapters

    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_open_fund_rank_em",
        lambda symbol: FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                },
                {
                    "基金代码": "000002",
                    "基金简称": "稳健债券B",
                    "日期": "2026-04-02",
                    "单位净值": "1.0555",
                    "手续费": "0.20%",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_money_rank_em",
        lambda: FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                },
                {
                    "基金代码": "000009",
                    "基金简称": "现金管理A",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.75%",
                    "手续费": "0.00%",
                },
            ]
        ),
    )

    response = RecommendationService(
        orchestrator=RecommendationOrchestrator(
            multi_agent_runtime=AnthropicMultiAgentRuntime(providers={})
        )
    ).get_recommendation("balanced")

    assert response.allocationDisplay.model_dump() == {
        "fund": 45,
        "wealthManagement": 35,
        "stock": 20,
    }
    assert response.sections.funds.titleZh == "基金推荐"
    assert response.sections.wealthManagement.titleZh == "银行理财推荐"
    assert response.sections.funds.items[0].nameZh == "稳健债券A"
    assert response.sections.wealthManagement.items[0].nameZh == "华宝添益"
