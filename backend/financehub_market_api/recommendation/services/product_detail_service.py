from __future__ import annotations

import logging
from datetime import date, datetime

from financehub_market_api.cache import SnapshotCache, build_snapshot_cache
from financehub_market_api.models import (
    LocalizedText,
    RecommendationEvidenceReference,
    RecommendationProductDetailResponse,
    TrendPoint,
)
from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.refresh import (
    RecommendationCandidatePoolRefresher,
)
from financehub_market_api.recommendation.candidate_pool.schemas import ProductChartPoint, ProductDetailSnapshot
from financehub_market_api.recommendation.product_knowledge import (
    ProductKnowledgeRetrievalService,
    build_product_knowledge_retrieval_service_from_env,
)
from financehub_market_api.recommendation.rules.product_catalog import FUNDS, STOCKS, WEALTH_MANAGEMENT
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.recommendation.services.evidence_projection import (
    project_public_evidence_references,
)

logger = logging.getLogger(__name__)

_PRODUCT_LOOKUP = {
    product.id: product
    for product in [*FUNDS, *WEALTH_MANAGEMENT, *STOCKS]
}


class ProductDetailService:
    def __init__(
        self,
        *,
        cache: ProductDetailSnapshotCache,
        refresher: RecommendationCandidatePoolRefresher | None = None,
        product_knowledge_service: ProductKnowledgeRetrievalService | None = None,
    ) -> None:
        self._cache = cache
        self._refresher = refresher
        self._product_knowledge_service = product_knowledge_service

    @classmethod
    def with_default_cache(
        cls,
        *,
        snapshot_cache: SnapshotCache | None = None,
    ) -> "ProductDetailService":
        cache_backend = snapshot_cache or build_snapshot_cache()
        product_detail_cache = ProductDetailSnapshotCache(cache_backend)
        refresher = RecommendationCandidatePoolRefresher.with_default_providers(
            candidate_pool_cache=CandidatePoolSnapshotCache(cache_backend),
            product_detail_cache=product_detail_cache,
        )
        return cls(
            cache=product_detail_cache,
            refresher=refresher,
            product_knowledge_service=build_product_knowledge_retrieval_service_from_env(),
        )

    def get_product_detail(self, product_id: str) -> RecommendationProductDetailResponse | None:
        snapshot = self._cache.get_product_detail(product_id)
        if snapshot is not None:
            return self._attach_public_evidence(
                _snapshot_to_response(snapshot),
                snapshot=snapshot,
            )

        stale_snapshot = self._cache.peek_product_detail(product_id)
        if stale_snapshot is not None:
            stale_response = _snapshot_to_response(stale_snapshot.model_copy(update={"stale": True}))
            return self._attach_public_evidence(
                stale_response,
                snapshot=stale_snapshot,
            )

        fallback_product = _PRODUCT_LOOKUP.get(product_id)
        if fallback_product is None:
            return None
        fallback_snapshot = _catalog_product_to_snapshot(fallback_product)
        return self._attach_public_evidence(
            _snapshot_to_response(fallback_snapshot),
            snapshot=fallback_snapshot,
        )

    def refresh_product_detail(self, product_id: str) -> None:
        category = _category_for_product_id(product_id)
        if category is None or self._refresher is None:
            return
        try:
            self._refresher.refresh_category(category)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "failed to refresh recommendation detail for %s via category %s: %s",
                product_id,
                category,
                exc,
            )

    def _attach_public_evidence(
        self,
        response: RecommendationProductDetailResponse,
        *,
        snapshot: ProductDetailSnapshot,
    ) -> RecommendationProductDetailResponse:
        return response.model_copy(
            update={
                "evidence": _public_evidence_for_product(
                    product_knowledge_service=self._product_knowledge_service,
                    query_text=_detail_evidence_query_text(snapshot),
                    product_id=snapshot.id,
                )
            }
        )


def _detail_evidence_query_text(snapshot: ProductDetailSnapshot) -> str:
    return " ".join(
        part
        for part in (
            snapshot.name_zh,
            snapshot.name_en,
            snapshot.recommendation_rationale_zh,
            snapshot.recommendation_rationale_en,
        )
        if part
    )


def _public_evidence_for_product(
    *,
    product_knowledge_service: ProductKnowledgeRetrievalService | None,
    query_text: str,
    product_id: str,
) -> list[RecommendationEvidenceReference]:
    if product_knowledge_service is None:
        return []

    try:
        bundles = product_knowledge_service.retrieve_evidence(
            query_text=query_text or product_id,
            product_ids=[product_id],
            include_internal=False,
            limit_per_product=6,
            total_limit=6,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to retrieve product evidence for %s: %s", product_id, exc)
        return []

    for bundle in bundles:
        if bundle.product_id != product_id:
            continue
        return project_public_evidence_references(bundle.evidences, limit=6)
    return []


def _catalog_product_to_snapshot(product: CandidateProduct) -> ProductDetailSnapshot:
    timestamp = datetime.now().astimezone().isoformat()
    return ProductDetailSnapshot(
        id=product.id,
        category=product.category,  # type: ignore[arg-type]
        code=product.code,
        provider_name="Static recommendation catalog",
        name_zh=product.name_zh,
        name_en=product.name_en,
        as_of_date=product.as_of_date or date.today().isoformat(),
        generated_at=timestamp,
        fresh_until=timestamp,
        source="static_recommendation_catalog",
        stale=True,
        risk_level=product.risk_level,
        liquidity=product.liquidity,
        tags_zh=list(product.tags_zh),
        tags_en=list(product.tags_en),
        summary_zh="静态推荐目录详情，用于候选池缺失时提供基础产品说明。",
        summary_en="Static catalog detail used as a fallback when prefetched product detail is unavailable.",
        recommendation_rationale_zh=product.rationale_zh,
        recommendation_rationale_en=product.rationale_en,
        chart_label_zh="近期走势",
        chart_label_en="Recent trend",
        chart=[],
        yield_metrics={},
        fees={},
        drawdown_or_volatility={},
        fit_for_profile_zh="适合先查看基础信息，再结合推荐页判断是否进一步关注。",
        fit_for_profile_en="Best used as a baseline product profile before reviewing the recommendation context.",
    )


def _snapshot_to_response(snapshot: ProductDetailSnapshot) -> RecommendationProductDetailResponse:
    return RecommendationProductDetailResponse(
        id=snapshot.id,
        category=snapshot.category,
        code=snapshot.code,
        providerName=snapshot.provider_name,
        nameZh=snapshot.name_zh,
        nameEn=snapshot.name_en,
        asOfDate=snapshot.as_of_date,
        stale=snapshot.stale,
        source=snapshot.source,
        riskLevel=snapshot.risk_level,
        liquidity=snapshot.liquidity,
        tagsZh=list(snapshot.tags_zh),
        tagsEn=list(snapshot.tags_en),
        summary=LocalizedText(
            zh=snapshot.summary_zh,
            en=snapshot.summary_en,
        ),
        recommendationRationale=LocalizedText(
            zh=snapshot.recommendation_rationale_zh,
            en=snapshot.recommendation_rationale_en,
        ),
        chartLabel=LocalizedText(
            zh=snapshot.chart_label_zh,
            en=snapshot.chart_label_en,
        ),
        chart=[_chart_point_to_trend_point(point) for point in snapshot.chart],
        yieldMetrics=dict(snapshot.yield_metrics),
        fees=dict(snapshot.fees),
        drawdownOrVolatility=dict(snapshot.drawdown_or_volatility),
        fitForProfile=LocalizedText(
            zh=snapshot.fit_for_profile_zh,
            en=snapshot.fit_for_profile_en,
        ),
    )


def _chart_point_to_trend_point(point: ProductChartPoint) -> TrendPoint:
    return TrendPoint(date=point.date, value=point.value)


def _category_for_product_id(product_id: str) -> str | None:
    if product_id.startswith("fund-"):
        return "fund"
    if product_id.startswith("wm-"):
        return "wealth_management"
    if product_id.startswith("stock-"):
        return "stock"
    return None
