from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypedDict, TypeVar, cast

from pydantic import BaseModel

from financehub_market_api.models import (
    IndexCard,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    RecommendationGenerationRequest,
    RecommendationResponse,
    TrendPoint,
)
from financehub_market_api.recommendation.agents import provider as provider_module
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider
from financehub_market_api.recommendation.agents.live_runtime import (
    AnthropicRecommendationAgentRuntime,
)
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
    LLM_CAPTURE_RAW_RESPONSES_ENV,
    build_provider,
)
from financehub_market_api.recommendation.compliance import ComplianceFactsService
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.recommendation.services import RecommendationService
from financehub_market_api.recommendation.rules import map_user_profile

_UNSTABLE_CAPTURE_KEYS = frozenset({"id", "created_at", "request_id"})
_T = TypeVar("_T")


class CaptureSummary(TypedDict):
    request_name: str
    phase: str | None
    fixture_path: str | None
    error: str | None


class LiveSmokeSummary(TypedDict):
    request_name: str
    model_name: str
    output_summary: str


class CaptureRunError(RuntimeError):
    def __init__(self, summary: list[CaptureSummary]) -> None:
        self.summary = summary
        failures = [
            f"{item['request_name']}: {item['error']}"
            for item in summary
            if item["error"] is not None
        ]
        super().__init__("Capture completed with failures: " + "; ".join(failures))


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["memory:capital_preservation", "memory:one_year_horizon"][:limit]


class _GrowthMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["memory:accepts_equity_volatility", "memory:seeks_growth_upside"][:limit]


class _OrderedVectorStore:
    def __init__(self, candidates: list[CandidateProduct]) -> None:
        self._candidates = list(candidates)

    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": candidate.id, "score": 1.0 - index * 0.05}
            for index, candidate in enumerate(self._candidates[:limit])
        ]


class _StaticRuleSnapshotSource:
    def fetch_snapshot(self) -> Mapping[str, object]:
        return {
            "version": "2026-04-10",
            "generated_at": "2026-04-10T08:00:00Z",
            "risk_tiers": {
                "R1": {
                    "max_risk_level": "R1",
                    "max_lockup_days": 90,
                    "max_drawdown_percent": 2.0,
                    "blocked_categories": ["stock"],
                },
                "R2": {
                    "max_risk_level": "R2",
                    "max_lockup_days": 365,
                    "max_drawdown_percent": 4.0,
                    "blocked_categories": ["stock"],
                },
            },
            "unknown_risk_policy": "block",
            "missing_rules_policy": "block",
            "missing_required_metric_policy": "block",
        }


class _GrowthRuleSnapshotSource:
    def fetch_snapshot(self) -> Mapping[str, object]:
        return {
            "version": "2026-04-10-growth",
            "generated_at": "2026-04-10T08:00:00Z",
            "risk_tiers": {
                "R3": {
                    "max_risk_level": "R3",
                    "max_lockup_days": 540,
                    "max_drawdown_percent": 12.0,
                    "blocked_categories": [],
                },
                "R4": {
                    "max_risk_level": "R4",
                    "max_lockup_days": 720,
                    "max_drawdown_percent": 18.0,
                    "blocked_categories": [],
                },
                "R5": {
                    "max_risk_level": "R5",
                    "max_lockup_days": 1080,
                    "max_drawdown_percent": 25.0,
                    "blocked_categories": [],
                },
            },
            "unknown_risk_policy": "block",
            "missing_rules_policy": "block",
            "missing_required_metric_policy": "block",
        }


class _DefensiveMarketDataSource:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-10",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3966.17",
                    delta="-0.7%",
                    changeValue=-27.8,
                    changePercent=-0.7,
                    tone="negative",
                ),
                MetricCard(
                    label="深证成指",
                    value="13996.27",
                    delta="-0.3%",
                    changeValue=-42.1,
                    changePercent=-0.3,
                    tone="negative",
                ),
            ],
            chartLabel="近20日走势",
            trendSeries=[TrendPoint(date="2026-04-10", value=3966.17)],
            topGainers=[],
            topLosers=[],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-10",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="CN",
                    description="soft session",
                    value="3966.17",
                    valueNumber=3966.17,
                    changeValue=-27.8,
                    changePercent=-0.7,
                    tone="negative",
                    trendSeries=[TrendPoint(date="2026-04-10", value=3966.17)],
                ),
                IndexCard(
                    name="深证成指",
                    code="399001",
                    market="CN",
                    description="soft session",
                    value="13996.27",
                    valueNumber=13996.27,
                    changeValue=-42.1,
                    changePercent=-0.3,
                    tone="negative",
                    trendSeries=[TrendPoint(date="2026-04-10", value=13996.27)],
                ),
            ],
        )


class _OffensiveMarketDataSource:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-10",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="4028.51",
                    delta="+1.1%",
                    changeValue=43.7,
                    changePercent=1.1,
                    tone="positive",
                ),
                MetricCard(
                    label="创业板指",
                    value="2518.40",
                    delta="+2.4%",
                    changeValue=58.9,
                    changePercent=2.4,
                    tone="positive",
                ),
            ],
            chartLabel="近20日走势",
            trendSeries=[TrendPoint(date="2026-04-10", value=4028.51)],
            topGainers=[],
            topLosers=[],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-10",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="CN",
                    description="strong session",
                    value="4028.51",
                    valueNumber=4028.51,
                    changeValue=43.7,
                    changePercent=1.1,
                    tone="positive",
                    trendSeries=[TrendPoint(date="2026-04-10", value=4028.51)],
                ),
                IndexCard(
                    name="创业板指",
                    code="399006",
                    market="CN",
                    description="growth leadership",
                    value="2518.40",
                    valueNumber=2518.40,
                    changeValue=58.9,
                    changePercent=2.4,
                    tone="positive",
                    trendSeries=[TrendPoint(date="2026-04-10", value=2518.40)],
                ),
            ],
        )


def capture_request_names() -> tuple[str, ...]:
    return tuple(provider_module.AGENT_MODEL_ROUTE_ENV_NAMES)


def fixture_filename_for_request_name(request_name: str) -> str:
    if request_name not in capture_request_names():
        raise ValueError(f"unsupported request_name: {request_name}")
    return f"{request_name}.json"


def sanitize_captured_body(body: object) -> object:
    if isinstance(body, Mapping):
        return {
            key: sanitize_captured_body(value)
            for key, value in body.items()
            if key not in _UNSTABLE_CAPTURE_KEYS
        }
    if isinstance(body, list):
        return [sanitize_captured_body(item) for item in body]
    return body


def build_fixture_payload(
    *,
    request_name: str,
    phase: str,
    body: object,
) -> dict[str, object]:
    if request_name not in capture_request_names():
        raise ValueError(f"unsupported request_name: {request_name}")
    return {
        "request_name": request_name,
        "capture_phase": phase,
        "body": sanitize_captured_body(body),
    }


def _build_anthropic_provider_from_env() -> tuple[StructuredOutputProvider, AgentRuntimeConfig]:
    runtime_config = AgentRuntimeConfig.from_env()
    provider_config = runtime_config.providers.get(ANTHROPIC_PROVIDER_NAME)
    if provider_config is None:
        raise RuntimeError(
            "Anthropic provider config is missing. Set FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY "
            "and FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL (or compatible aliases)."
        )
    provider = build_provider(provider_config)
    return cast(StructuredOutputProvider, provider), runtime_config


def _build_runtime_or_raise() -> AnthropicRecommendationAgentRuntime:
    provider, runtime_config = _build_anthropic_provider_from_env()
    return AnthropicRecommendationAgentRuntime(
        provider=provider,
        runtime_config=runtime_config,
    )


def _agent_route_or_raise(
    routes: Mapping[str, AgentModelRoute],
    request_name: str,
) -> AgentModelRoute:
    route = routes.get(request_name)
    if route is None:
        raise RuntimeError(f"Missing model route for request_name={request_name}.")
    if route.provider_name != ANTHROPIC_PROVIDER_NAME:
        raise RuntimeError(
            f"Invalid provider for request_name={request_name}: {route.provider_name}. "
            f"Expected {ANTHROPIC_PROVIDER_NAME}."
        )
    if not route.model_name.strip():
        raise RuntimeError(f"Missing model_name for request_name={request_name}.")
    return route


def _load_capture_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read capture file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Capture file {path} must contain a top-level object.")
    return payload


def _path_may_match_request_name(path: Path, request_name: str) -> bool:
    return request_name in path.stem


def _latest_capture_for_request_name(
    capture_dir: Path,
    request_name: str,
) -> tuple[Path, dict[str, object]]:
    paths = sorted(
        capture_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in paths:
        try:
            payload = _load_capture_payload(path)
        except RuntimeError:
            if _path_may_match_request_name(path, request_name):
                raise
            continue
        if payload.get("request_name") != request_name:
            continue
        return path, payload
    raise RuntimeError(
        f"No raw capture found for request_name={request_name} in {capture_dir}. "
        f"Set {LLM_CAPTURE_RAW_RESPONSES_ENV}=true before running capture."
    )


def _write_fixture_payload(
    *,
    fixtures_dir: Path,
    request_name: str,
    phase: str,
    body: object,
) -> Path:
    fixture_path = fixtures_dir / fixture_filename_for_request_name(request_name)
    payload = build_fixture_payload(request_name=request_name, phase=phase, body=body)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return fixture_path


def _build_live_candidates(*, risk_profile: str = "balanced") -> list[CandidateProduct]:
    if risk_profile == "growth":
        return [
            CandidateProduct(
                id="fund-101",
                category="fund",
                code="161725",
                liquidity="T+1",
                lockup_days=7,
                max_drawdown_percent=8.5,
                name_zh="成长行业精选基金",
                name_en="Growth Sector Select Fund",
                rationale_zh="偏成长风格，适合作为权益底仓。",
                rationale_en="Growth-oriented fund suited as an equity core holding.",
                risk_level="R4",
                tags_zh=["成长", "进攻"],
                tags_en=["growth", "offensive"],
            ),
            CandidateProduct(
                id="stock-101",
                category="stock",
                code="300750",
                liquidity="T+1",
                lockup_days=0,
                max_drawdown_percent=11.2,
                name_zh="宁德时代",
                name_en="CATL",
                rationale_zh="景气度与成长性兼具，适合作为进攻型配置。",
                rationale_en="Combines strong momentum and growth potential for an offensive sleeve.",
                risk_level="R4",
                tags_zh=["新能源", "龙头"],
                tags_en=["new-energy", "leader"],
            ),
            CandidateProduct(
                id="stock-102",
                category="stock",
                code="688111",
                liquidity="T+1",
                lockup_days=0,
                max_drawdown_percent=12.8,
                name_zh="金山办公",
                name_en="Kingsoft Office",
                rationale_zh="软件成长弹性较强，可补充科技进攻仓位。",
                rationale_en="High software growth beta that complements the technology sleeve.",
                risk_level="R4",
                tags_zh=["软件", "科技成长"],
                tags_en=["software", "tech-growth"],
            ),
        ]

    return [
        CandidateProduct(
            id="fund-001",
            category="fund",
            code="000001",
            liquidity="T+1",
            lockup_days=7,
            max_drawdown_percent=1.8,
            name_zh="稳健短债增强A",
            name_en="Resilient Short Bond A",
            rationale_zh="短债底仓，强调波动控制。",
            rationale_en="Short-duration bond core with drawdown control.",
            risk_level="R2",
            tags_zh=["短债", "稳健"],
            tags_en=["short-bond", "resilient"],
        ),
        CandidateProduct(
            id="wm-001",
            category="wealth_management",
            code="WM001",
            liquidity="T+1",
            lockup_days=30,
            max_drawdown_percent=0.8,
            name_zh="现金管理理财一号",
            name_en="Cash Management One",
            rationale_zh="流动性较好，适合作为现金管理配置。",
            rationale_en="High-liquidity cash management product.",
            risk_level="R1",
            tags_zh=["现金管理", "高流动性"],
            tags_en=["cash-management", "high-liquidity"],
        ),
    ]


def _build_live_request(
    *,
    risk_profile: str = "balanced",
) -> RecommendationGenerationRequest:
    if risk_profile == "growth":
        return RecommendationGenerationRequest.model_validate(
            {
                "userIntentText": "我有20万预算，计划持有两到三年，能接受波动，想抓住科技成长机会。",
                "conversationMessages": [
                    {
                        "role": "user",
                        "content": "如果市场偏强，我愿意增加股票仓位来争取更高收益。",
                        "occurredAt": "2026-04-10T08:00:00Z",
                    }
                ],
                "historicalHoldings": [],
                "historicalTransactions": [],
                "questionnaireAnswers": [
                    {
                        "questionId": "q1",
                        "answerId": "a5",
                        "dimension": "riskTolerance",
                        "score": 5,
                    }
                ],
                "riskAssessmentResult": {
                    "baseProfile": risk_profile,
                    "dimensionLevels": {
                        "capitalStability": "medium",
                        "investmentExperience": "high",
                        "investmentHorizon": "high",
                        "returnObjective": "high",
                        "riskTolerance": "high",
                    },
                    "dimensionScores": {
                        "capitalStability": 10,
                        "investmentExperience": 18,
                        "investmentHorizon": 18,
                        "returnObjective": 18,
                        "riskTolerance": 18,
                    },
                    "finalProfile": risk_profile,
                    "totalScore": 82,
                },
            }
        )

    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我有10万闲钱，想存一年，不想亏本，最好随时能用。",
            "conversationMessages": [
                {
                    "role": "user",
                    "content": "最近市场波动大，我更在意保本和流动性。",
                    "occurredAt": "2026-04-10T08:00:00Z",
                }
            ],
            "historicalHoldings": [],
            "historicalTransactions": [],
            "questionnaireAnswers": [
                {
                    "questionId": "q1",
                    "answerId": "a1",
                    "dimension": "riskTolerance",
                    "score": 2,
                }
            ],
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


def _build_output_summary(output: BaseModel) -> str:
    return json.dumps(
        output.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _run_core_stage_sequence(
    runtime: AnthropicRecommendationAgentRuntime,
    *,
    risk_profile: str,
) -> list[tuple[str, BaseModel, str]]:
    user_profile = map_user_profile(risk_profile)
    market_service = MarketIntelligenceService(
        market_data_service=(
            _OffensiveMarketDataSource()
            if risk_profile == "growth"
            else _DefensiveMarketDataSource()
        )
    )
    market_snapshot = market_service.build_recommendation_snapshot()
    market_facts = {
        "summary_zh": market_snapshot.summary_zh,
        "summary_en": market_snapshot.summary_en,
        "preferred_categories": list(market_snapshot.preferred_categories),
        "avoided_categories": list(market_snapshot.avoided_categories),
        "evidence": [
            evidence.model_dump(mode="json") for evidence in market_snapshot.evidence
        ],
    }
    candidates = _build_live_candidates(risk_profile=risk_profile)
    compliance_facts = ComplianceFactsService(
        rule_snapshot_source=(
            _GrowthRuleSnapshotSource()
            if risk_profile == "growth"
            else _StaticRuleSnapshotSource()
        )
    ).build_review_facts(
        request_payload=_build_live_request(risk_profile=risk_profile).model_dump(mode="json"),
        selected_candidates=candidates,
    )

    profile_output, profile_metadata = runtime.analyze_user_profile(user_profile)
    market_output, market_metadata = runtime.analyze_market_intelligence(
        user_profile,
        profile_output,
        market_facts,
    )
    product_output, product_metadata = runtime.match_products(
        user_profile,
        user_profile_insights=profile_output,
        market_intelligence=market_output,
        candidates=candidates,
    )
    selected_ids = {
        *product_output.fund_ids,
        *product_output.wealth_management_ids,
        *product_output.stock_ids,
    }
    selected_candidates = [
        candidate for candidate in candidates if candidate.id in selected_ids
    ]
    compliance_output, compliance_metadata = runtime.review_compliance(
        user_profile,
        user_profile_insights=profile_output,
        selected_candidates=selected_candidates,
        compliance_facts=compliance_facts,
    )
    manager_output, manager_metadata = runtime.coordinate_manager(
        user_profile,
        user_profile_insights=profile_output,
        market_intelligence=market_output,
        product_match=product_output,
        compliance_review=compliance_output,
    )
    return [
        ("user_profile_analyst", profile_output, profile_metadata.model_name),
        ("market_intelligence", market_output, market_metadata.model_name),
        ("product_match_expert", product_output, product_metadata.model_name),
        ("compliance_risk_officer", compliance_output, compliance_metadata.model_name),
        ("manager_coordinator", manager_output, manager_metadata.model_name),
    ]


def run_live_agent_smoke(
    *,
    risk_profile: str = "balanced",
) -> list[LiveSmokeSummary]:
    runtime = _build_runtime_or_raise()
    return [
        LiveSmokeSummary(
            request_name=request_name,
            model_name=model_name,
            output_summary=_build_output_summary(output),
        )
        for request_name, output, model_name in _run_core_stage_sequence(
            runtime,
            risk_profile=risk_profile,
        )
    ]


def run_live_agent_e2e(*, risk_profile: str = "balanced") -> RecommendationResponse:
    runtime = AnthropicRecommendationAgentRuntime.from_env()
    if runtime is None:
        raise RuntimeError("No live Anthropic runtime configuration is available.")

    candidates = _build_live_candidates(risk_profile=risk_profile)
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime(
            GraphServices(
                market_intelligence=MarketIntelligenceService(
                    market_data_service=(
                        _OffensiveMarketDataSource()
                        if risk_profile == "growth"
                        else _DefensiveMarketDataSource()
                    )
                ),
                memory_recall=MemoryRecallService(
                    store=(
                        _GrowthMemoryStore()
                        if risk_profile == "growth"
                        else _SingleMemoryStore()
                    )
                ),
                product_retrieval=ProductRetrievalService(
                    vector_store=_OrderedVectorStore(candidates)
                ),
                compliance_facts_service=ComplianceFactsService(
                    rule_snapshot_source=(
                        _GrowthRuleSnapshotSource()
                        if risk_profile == "growth"
                        else _StaticRuleSnapshotSource()
                    )
                ),
                product_candidates=candidates,
                agent_runtime=runtime,
            )
        )
    )
    return service.generate_recommendation(_build_live_request(risk_profile=risk_profile))


def capture_all_agents(
    *,
    risk_profile: str = "balanced",
    fixtures_dir: str | Path | None = None,
) -> list[CaptureSummary]:
    env_values = provider_module._build_env_values()
    provider, runtime_config = _build_anthropic_provider_from_env()
    if not provider_module._is_raw_capture_enabled(env_values):
        raise RuntimeError(
            f"{LLM_CAPTURE_RAW_RESPONSES_ENV} must be set to a truthy value to capture raw responses."
        )

    runtime = AnthropicRecommendationAgentRuntime(
        provider=provider,
        runtime_config=runtime_config,
    )
    routes = runtime_config.agent_routes
    for request_name in capture_request_names():
        _agent_route_or_raise(routes, request_name)

    capture_dir = provider_module._resolve_capture_dir(env_values)
    fixtures_path = Path(fixtures_dir) if fixtures_dir is not None else None
    summary: list[CaptureSummary] = []
    stage_errors: dict[str, str] = {}
    outputs: dict[str, BaseModel] = {}

    def _format_error(exc: Exception) -> str:
        message = str(exc).strip()
        return message or exc.__class__.__name__

    def _record_summary(
        request_name: str,
        error: str | None,
        *,
        attempt_capture: bool,
    ) -> None:
        phase: str | None = None
        fixture_path_value: str | None = None
        summary_error = error
        if attempt_capture:
            try:
                _, capture_payload = _latest_capture_for_request_name(
                    capture_dir,
                    request_name,
                )
            except RuntimeError as exc:
                capture_error = _format_error(exc)
                summary_error = (
                    capture_error
                    if summary_error is None
                    else f"{summary_error}; {capture_error}"
                )
            else:
                phase = str(capture_payload.get("phase", "unknown"))
                if fixtures_path is not None:
                    fixture_path = _write_fixture_payload(
                        fixtures_dir=fixtures_path,
                        request_name=request_name,
                        phase=phase,
                        body=capture_payload.get("body"),
                    )
                    fixture_path_value = str(fixture_path)

        summary.append(
            CaptureSummary(
                request_name=request_name,
                phase=phase,
                fixture_path=fixture_path_value,
                error=summary_error,
            )
        )
        if summary_error is not None:
            stage_errors[request_name] = summary_error

    def _run_stage(
        request_name: str,
        dependencies: tuple[str, ...],
        runner: Callable[[], _T],
    ) -> _T | None:
        for dependency in dependencies:
            if dependency in stage_errors:
                _record_summary(
                    request_name,
                    f"skipped because dependency {dependency} failed",
                    attempt_capture=False,
                )
                return None
        try:
            result = runner()
        except Exception as exc:  # noqa: BLE001
            _record_summary(request_name, _format_error(exc), attempt_capture=True)
            return None
        _record_summary(request_name, None, attempt_capture=True)
        return result

    user_profile = map_user_profile(risk_profile)
    market_service = MarketIntelligenceService(
        market_data_service=(
            _OffensiveMarketDataSource()
            if risk_profile == "growth"
            else _DefensiveMarketDataSource()
        )
    )
    market_snapshot = market_service.build_recommendation_snapshot()
    market_facts = {
        "summary_zh": market_snapshot.summary_zh,
        "summary_en": market_snapshot.summary_en,
        "preferred_categories": list(market_snapshot.preferred_categories),
        "avoided_categories": list(market_snapshot.avoided_categories),
        "evidence": [
            evidence.model_dump(mode="json") for evidence in market_snapshot.evidence
        ],
    }
    candidates = _build_live_candidates(risk_profile=risk_profile)
    compliance_facts = ComplianceFactsService(
        rule_snapshot_source=(
            _GrowthRuleSnapshotSource()
            if risk_profile == "growth"
            else _StaticRuleSnapshotSource()
        )
    ).build_review_facts(
        request_payload=_build_live_request(risk_profile=risk_profile).model_dump(mode="json"),
        selected_candidates=candidates,
    )

    profile_output = _run_stage(
        "user_profile_analyst",
        (),
        lambda: runtime.analyze_user_profile(user_profile)[0],
    )
    if profile_output is not None:
        outputs["user_profile_analyst"] = profile_output

    market_output = _run_stage(
        "market_intelligence",
        ("user_profile_analyst",),
        lambda: runtime.analyze_market_intelligence(
            user_profile,
            cast(UserProfileAgentOutput, outputs["user_profile_analyst"]),
            market_facts,
        )[0],
    )
    if market_output is not None:
        outputs["market_intelligence"] = market_output

    product_output = _run_stage(
        "product_match_expert",
        ("user_profile_analyst", "market_intelligence"),
        lambda: runtime.match_products(
            user_profile,
            user_profile_insights=cast(UserProfileAgentOutput, outputs["user_profile_analyst"]),
            market_intelligence=cast(MarketIntelligenceAgentOutput, outputs["market_intelligence"]),
            candidates=candidates,
        )[0],
    )
    if product_output is not None:
        outputs["product_match_expert"] = product_output

    def _selected_candidates() -> list[CandidateProduct]:
        matched = cast(ProductMatchAgentOutput, outputs["product_match_expert"])
        selected_ids = {
            *matched.fund_ids,
            *matched.wealth_management_ids,
            *matched.stock_ids,
        }
        return [candidate for candidate in candidates if candidate.id in selected_ids]

    compliance_output = _run_stage(
        "compliance_risk_officer",
        ("user_profile_analyst", "product_match_expert"),
        lambda: runtime.review_compliance(
            user_profile,
            user_profile_insights=cast(UserProfileAgentOutput, outputs["user_profile_analyst"]),
            selected_candidates=_selected_candidates(),
            compliance_facts=compliance_facts,
        )[0],
    )
    if compliance_output is not None:
        outputs["compliance_risk_officer"] = compliance_output

    manager_output = _run_stage(
        "manager_coordinator",
        (
            "user_profile_analyst",
            "market_intelligence",
            "product_match_expert",
            "compliance_risk_officer",
        ),
        lambda: runtime.coordinate_manager(
            user_profile,
            user_profile_insights=cast(UserProfileAgentOutput, outputs["user_profile_analyst"]),
            market_intelligence=cast(MarketIntelligenceAgentOutput, outputs["market_intelligence"]),
            product_match=cast(ProductMatchAgentOutput, outputs["product_match_expert"]),
            compliance_review=cast(
                ComplianceReviewAgentOutput,
                outputs["compliance_risk_officer"],
            ),
        )[0],
    )
    if manager_output is not None:
        outputs["manager_coordinator"] = manager_output

    if any(item["error"] is not None for item in summary):
        raise CaptureRunError(summary)
    return summary
