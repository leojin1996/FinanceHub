from __future__ import annotations

from io import StringIO

from financehub_market_api.recommendation.candidate_pool.refresh import RefreshResult
from scripts.refresh_recommendation_candidate_pool import main


class _FakeRefresher:
    def __init__(self, results: dict[str, RefreshResult]) -> None:
        self._results = results
        self.categories: list[str] = []

    def refresh_category(self, category: str) -> RefreshResult:
        self.categories.append(category)
        return self._results[category]


def test_refresh_script_runs_only_requested_categories() -> None:
    refresher = _FakeRefresher(
        {
            "fund": RefreshResult(status="fresh", item_count=2),
            "wealth_management": RefreshResult(status="fresh", item_count=1),
            "stock": RefreshResult(status="fresh", item_count=12),
        }
    )
    output = StringIO()

    exit_code = main(
        ["--category", "stock", "--category", "fund"],
        out=output,
        refresher_factory=lambda: refresher,
    )

    assert exit_code == 0
    assert refresher.categories == ["stock", "fund"]
    assert output.getvalue().strip().splitlines() == [
        "stock: fresh items=12",
        "fund: fresh items=2",
    ]


def test_refresh_script_returns_nonzero_when_any_requested_category_fails() -> None:
    refresher = _FakeRefresher(
        {
            "fund": RefreshResult(status="fresh", item_count=2),
            "wealth_management": RefreshResult(
                status="error",
                item_count=1,
                error_message="upstream down",
            ),
            "stock": RefreshResult(status="fresh", item_count=12),
        }
    )
    output = StringIO()

    exit_code = main(
        ["--category", "wealth_management"],
        out=output,
        refresher_factory=lambda: refresher,
    )

    assert exit_code == 1
    assert refresher.categories == ["wealth_management"]
    assert "error=upstream down" in output.getvalue()
