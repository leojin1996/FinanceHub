from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from financehub_market_api.cache import SnapshotCache, build_snapshot_cache
from financehub_market_api.env import build_env_values, read_env
from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.refresh import (
    RecommendationCandidatePoolRefresher,
    RefreshResult,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_STOCK_INTERVAL_SECONDS = 600.0
DEFAULT_FUND_INTERVAL_SECONDS = 3600.0
DEFAULT_WEALTH_INTERVAL_SECONDS = 3600.0

_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class CategoryRefreshSchedule:
    category: str
    interval_seconds: float


@dataclass(frozen=True)
class RecommendationRefreshSchedulerSettings:
    enabled: bool = True
    run_on_startup: bool = True
    schedules: tuple[CategoryRefreshSchedule, ...] = (
        CategoryRefreshSchedule(
            category="stock",
            interval_seconds=DEFAULT_STOCK_INTERVAL_SECONDS,
        ),
        CategoryRefreshSchedule(
            category="fund",
            interval_seconds=DEFAULT_FUND_INTERVAL_SECONDS,
        ),
        CategoryRefreshSchedule(
            category="wealth_management",
            interval_seconds=DEFAULT_WEALTH_INTERVAL_SECONDS,
        ),
    )

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> RecommendationRefreshSchedulerSettings:
        env = build_env_values(environ=environ)
        return cls(
            enabled=_parse_bool_env(
                read_env(env, "FINANCEHUB_RECOMMENDATION_REFRESH_ENABLED"),
                default=True,
            ),
            run_on_startup=_parse_bool_env(
                read_env(env, "FINANCEHUB_RECOMMENDATION_REFRESH_RUN_ON_STARTUP"),
                default=True,
            ),
            schedules=(
                CategoryRefreshSchedule(
                    category="stock",
                    interval_seconds=_parse_positive_float_env(
                        "FINANCEHUB_RECOMMENDATION_REFRESH_STOCK_INTERVAL_SECONDS",
                        read_env(
                            env,
                            "FINANCEHUB_RECOMMENDATION_REFRESH_STOCK_INTERVAL_SECONDS",
                        ),
                        default=DEFAULT_STOCK_INTERVAL_SECONDS,
                    ),
                ),
                CategoryRefreshSchedule(
                    category="fund",
                    interval_seconds=_parse_positive_float_env(
                        "FINANCEHUB_RECOMMENDATION_REFRESH_FUND_INTERVAL_SECONDS",
                        read_env(
                            env,
                            "FINANCEHUB_RECOMMENDATION_REFRESH_FUND_INTERVAL_SECONDS",
                        ),
                        default=DEFAULT_FUND_INTERVAL_SECONDS,
                    ),
                ),
                CategoryRefreshSchedule(
                    category="wealth_management",
                    interval_seconds=_parse_positive_float_env(
                        "FINANCEHUB_RECOMMENDATION_REFRESH_WEALTH_INTERVAL_SECONDS",
                        read_env(
                            env,
                            "FINANCEHUB_RECOMMENDATION_REFRESH_WEALTH_INTERVAL_SECONDS",
                        ),
                        default=DEFAULT_WEALTH_INTERVAL_SECONDS,
                    ),
                ),
            ),
        )


def build_candidate_pool_refresher(
    *,
    snapshot_cache: SnapshotCache | None = None,
) -> RecommendationCandidatePoolRefresher:
    cache_backend = snapshot_cache or build_snapshot_cache()
    return RecommendationCandidatePoolRefresher.with_default_providers(
        candidate_pool_cache=CandidatePoolSnapshotCache(cache_backend),
        product_detail_cache=ProductDetailSnapshotCache(cache_backend),
    )


RefreshRunner = Callable[[str], Awaitable[RefreshResult]]
SleepFunction = Callable[[float], Awaitable[None]]


class RecommendationCandidatePoolScheduler:
    def __init__(
        self,
        *,
        refresher: RecommendationCandidatePoolRefresher,
        settings: RecommendationRefreshSchedulerSettings,
        run_refresh: RefreshRunner | None = None,
        sleep: SleepFunction | None = None,
    ) -> None:
        self._refresher = refresher
        self._settings = settings
        self._run_refresh = run_refresh or self._run_refresh_in_daemon_thread
        self._sleep = sleep or asyncio.sleep
        self._ticker_tasks: dict[str, asyncio.Task[None]] = {}
        self._inflight_tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        self._started = True
        if not self._settings.enabled:
            LOGGER.info("Recommendation candidate refresh scheduler is disabled.")
            return

        for schedule in self._settings.schedules:
            task = asyncio.create_task(
                self._run_schedule_loop(schedule),
                name=f"recommendation-refresh-ticker:{schedule.category}",
            )
            self._ticker_tasks[schedule.category] = task

        LOGGER.info(
            "Recommendation candidate refresh scheduler started for categories=%s.",
            ",".join(schedule.category for schedule in self._settings.schedules),
        )

    async def stop(self) -> None:
        if not self._started:
            return

        self._started = False
        tasks = [
            *self._ticker_tasks.values(),
            *self._inflight_tasks.values(),
        ]
        self._ticker_tasks = {}
        self._inflight_tasks = {}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        LOGGER.info("Recommendation candidate refresh scheduler stopped.")

    async def _run_schedule_loop(self, schedule: CategoryRefreshSchedule) -> None:
        try:
            if self._settings.run_on_startup:
                self._trigger_refresh(schedule.category)

            while True:
                await self._sleep(schedule.interval_seconds)
                self._trigger_refresh(schedule.category)
        except asyncio.CancelledError:
            raise

    def _trigger_refresh(self, category: str) -> None:
        inflight = self._inflight_tasks.get(category)
        if inflight is not None and not inflight.done():
            LOGGER.warning(
                "Skipping recommendation candidate refresh for %s because the previous run is still in progress.",
                category,
            )
            return

        task = asyncio.create_task(
            self._execute_refresh(category),
            name=f"recommendation-refresh-run:{category}",
        )
        self._inflight_tasks[category] = task

    async def _execute_refresh(self, category: str) -> None:
        try:
            result = await self._run_refresh(category)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "Recommendation candidate refresh crashed for %s.",
                category,
            )
        else:
            if result.status == "error":
                LOGGER.warning(
                    "Recommendation candidate refresh failed for %s: items=%s error=%s",
                    category,
                    result.item_count,
                    result.error_message,
                )
            else:
                LOGGER.info(
                    "Recommendation candidate refresh completed for %s: items=%s status=%s",
                    category,
                    result.item_count,
                    result.status,
                )
        finally:
            current_task = asyncio.current_task()
            if self._inflight_tasks.get(category) is current_task:
                self._inflight_tasks.pop(category, None)

    async def _run_refresh_in_daemon_thread(self, category: str) -> RefreshResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[RefreshResult] = loop.create_future()

        def worker() -> None:
            try:
                result = self._refresher.refresh_category(category)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(_settle_future_exception, future, exc)
            else:
                loop.call_soon_threadsafe(_settle_future_result, future, result)

        thread = threading.Thread(
            target=worker,
            name=f"recommendation-refresh-{category}",
            daemon=True,
        )
        thread.start()
        return await future


def build_recommendation_candidate_pool_scheduler_from_env(
    *,
    snapshot_cache: SnapshotCache | None = None,
    environ: Mapping[str, str] | None = None,
) -> RecommendationCandidatePoolScheduler:
    settings = RecommendationRefreshSchedulerSettings.from_env(environ=environ)
    refresher = build_candidate_pool_refresher(snapshot_cache=snapshot_cache)
    return RecommendationCandidatePoolScheduler(
        refresher=refresher,
        settings=settings,
    )


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUE_ENV_VALUES:
        return True
    if normalized in _FALSE_ENV_VALUES:
        return False

    LOGGER.warning(
        "Invalid boolean env value %r for recommendation refresh scheduler; falling back to default=%s.",
        value,
        default,
    )
    return default


def _parse_positive_float_env(
    key: str,
    value: str | None,
    *,
    default: float,
) -> float:
    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError:
        LOGGER.warning(
            "Invalid numeric env value %r for %s; falling back to default=%s.",
            value,
            key,
            default,
        )
        return default

    if parsed <= 0:
        LOGGER.warning(
            "Non-positive numeric env value %r for %s; falling back to default=%s.",
            value,
            key,
            default,
        )
        return default
    return parsed


def _settle_future_result(
    future: asyncio.Future[RefreshResult],
    result: RefreshResult,
) -> None:
    if future.cancelled() or future.done():
        return
    future.set_result(result)


def _settle_future_exception(
    future: asyncio.Future[RefreshResult],
    exc: Exception,
) -> None:
    if future.cancelled() or future.done():
        return
    future.set_exception(exc)


__all__ = [
    "CategoryRefreshSchedule",
    "RecommendationCandidatePoolScheduler",
    "RecommendationRefreshSchedulerSettings",
    "build_candidate_pool_refresher",
    "build_recommendation_candidate_pool_scheduler_from_env",
]
