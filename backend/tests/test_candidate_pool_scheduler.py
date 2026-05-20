from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from financehub_market_api.recommendation.candidate_pool.refresh import RefreshResult
from financehub_market_api.recommendation.candidate_pool.scheduler import (
    CategoryRefreshSchedule,
    RecommendationCandidatePoolScheduler,
    RecommendationRefreshSchedulerSettings,
)


class _UnusedRefresher:
    def refresh_category(self, category: str) -> RefreshResult:
        raise AssertionError(f"unexpected sync refresh for {category}")


class _FakeLifespanScheduler:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def test_scheduler_settings_read_env_overrides() -> None:
    settings = RecommendationRefreshSchedulerSettings.from_env(
        environ={
            "FINANCEHUB_RECOMMENDATION_REFRESH_ENABLED": "false",
            "FINANCEHUB_RECOMMENDATION_REFRESH_RUN_ON_STARTUP": "0",
            "FINANCEHUB_RECOMMENDATION_REFRESH_STOCK_INTERVAL_SECONDS": "30",
            "FINANCEHUB_RECOMMENDATION_REFRESH_FUND_INTERVAL_SECONDS": "120",
            "FINANCEHUB_RECOMMENDATION_REFRESH_WEALTH_INTERVAL_SECONDS": "240",
        }
    )

    assert settings.enabled is False
    assert settings.run_on_startup is False
    assert settings.schedules == (
        CategoryRefreshSchedule(category="stock", interval_seconds=30.0),
        CategoryRefreshSchedule(category="fund", interval_seconds=120.0),
        CategoryRefreshSchedule(category="wealth_management", interval_seconds=240.0),
    )


def test_scheduler_runs_immediately_and_repeats_by_interval() -> None:
    calls: list[str] = []

    async def run_refresh(category: str) -> RefreshResult:
        calls.append(category)
        return RefreshResult(status="fresh", item_count=1)

    scheduler = RecommendationCandidatePoolScheduler(
        refresher=_UnusedRefresher(),
        settings=RecommendationRefreshSchedulerSettings(
            schedules=(CategoryRefreshSchedule(category="stock", interval_seconds=0.01),)
        ),
        run_refresh=run_refresh,
    )

    async def scenario() -> None:
        await scheduler.start()
        await asyncio.sleep(0.035)
        await scheduler.stop()

    asyncio.run(scenario())

    assert len(calls) >= 3
    assert set(calls) == {"stock"}


def test_scheduler_skips_overlapping_category_runs() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def run_refresh(category: str) -> RefreshResult:
        calls.append(category)
        started.set()
        await release.wait()
        return RefreshResult(status="fresh", item_count=1)

    scheduler = RecommendationCandidatePoolScheduler(
        refresher=_UnusedRefresher(),
        settings=RecommendationRefreshSchedulerSettings(
            schedules=(CategoryRefreshSchedule(category="stock", interval_seconds=0.01),)
        ),
        run_refresh=run_refresh,
    )

    async def scenario() -> None:
        await scheduler.start()
        await asyncio.wait_for(started.wait(), timeout=0.2)
        await asyncio.sleep(0.04)
        assert calls == ["stock"]
        release.set()
        await asyncio.sleep(0.02)
        await scheduler.stop()

    asyncio.run(scenario())


def test_api_lifespan_starts_and_stops_recommendation_refresh_scheduler(
    monkeypatch,
) -> None:
    import financehub_market_api.main as main_module

    scheduler = _FakeLifespanScheduler()
    monkeypatch.setattr(main_module, "create_tables", lambda: None)
    monkeypatch.setattr(
        main_module,
        "get_recommendation_refresh_scheduler",
        lambda: scheduler,
    )

    with TestClient(main_module.app):
        pass

    assert scheduler.started == 1
    assert scheduler.stopped == 1
