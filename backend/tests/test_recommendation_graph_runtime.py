from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.runtime import GraphServices, RecommendationGraphRuntime
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.recommendation.services import RecommendationService


def _build_generation_request(
    risk_profile: str,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我希望获得稳健配置建议",
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": include_aggressive_option,
            "questionnaireAnswers": [],
            "riskAssessmentResult": {
                "baseProfile": risk_profile,
                "dimensionLevels": {
                    "capitalStability": "medium",
                    "investmentExperience": "medium",
                    "investmentHorizon": "medium",
                    "returnObjective": "medium",
                    "riskTolerance": "medium",
                },
                "dimensionScores": {
                    "capitalStability": 12,
                    "investmentExperience": 12,
                    "investmentHorizon": 12,
                    "returnObjective": 12,
                    "riskTolerance": 12,
                },
                "finalProfile": risk_profile,
                "totalScore": 60,
            },
        }
    )


def test_graph_runtime_produces_ready_response_with_trace_and_evidence() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.recommendationStatus == "ready"
    assert response.marketEvidence
    assert response.agentTrace


def test_graph_runtime_returns_limited_response_when_compliance_revises() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.recommendationStatus == "limited"
    assert response.reviewStatus == "partial_pass"
    assert response.complianceReview is not None
    assert response.complianceReview.verdict == "revise_conservative"
    assert response.sections.stocks.items == []
    assert all(
        item.riskLevel in {"R1", "R2"}
        for section in (
            response.sections.funds.items,
            response.sections.wealthManagement.items,
            response.sections.stocks.items,
        )
        for item in section
    )


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["runtime-memory"][:limit]


class _SingleVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "fund-001", "score": 0.99}][:limit]


class _FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


def test_graph_runtime_uses_runtime_candidate_metadata_over_static_catalog() -> None:
    runtime_candidate = CandidateProduct(
        id="fund-001",
        category="fund",
        code="900001",
        liquidity="T+0",
        name_zh="运行时自定义基金A",
        name_en="Runtime Custom Fund A",
        rationale_zh="使用实时候选产品元数据。",
        rationale_en="Use runtime candidate metadata.",
        risk_level="R2",
        tags_zh=["实时"],
        tags_en=["runtime"],
    )
    runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(vector_store=_SingleVectorStore()),
            compliance_review=ComplianceReviewService(),
            product_candidates=[runtime_candidate],
        )
    )
    service = RecommendationService(graph_runtime=runtime)

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.sections.funds.items[0].id == "fund-001"
    assert response.sections.funds.items[0].nameZh == "运行时自定义基金A"
    assert response.sections.funds.items[0].nameZh != "中欧稳利债券A"


def test_app_default_graph_runtime_uses_real_repository_candidates(monkeypatch) -> None:
    from financehub_market_api.recommendation.repositories import real_data_adapters

    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_open_fund_rank_em",
        lambda symbol: _FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_money_rank_em",
        lambda: _FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                }
            ]
        ),
    )

    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services()
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.sections.funds.items[0].nameZh == "稳健债券A"
    assert response.sections.wealthManagement.items[0].nameZh == "华宝添益"
