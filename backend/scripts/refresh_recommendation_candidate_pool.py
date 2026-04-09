from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from financehub_market_api.cache import build_snapshot_cache
from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.refresh import (
    RefreshResult,
    RecommendationCandidatePoolRefresher,
)

_CATEGORIES = ("fund", "wealth_management", "stock")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh prefetched recommendation candidate pools.",
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=_CATEGORIES,
        help="Only refresh the selected category. Repeat to refresh multiple categories.",
    )
    return parser.parse_args(argv)


def _default_refresher_factory() -> RecommendationCandidatePoolRefresher:
    cache = build_snapshot_cache()
    return RecommendationCandidatePoolRefresher.with_default_providers(
        candidate_pool_cache=CandidatePoolSnapshotCache(cache),
        product_detail_cache=ProductDetailSnapshotCache(cache),
    )


def _print_result(category: str, result: RefreshResult, *, out: TextIO) -> None:
    line = f"{category}: {result.status} items={result.item_count}"
    if result.error_message:
        line = f"{line} error={result.error_message}"
    print(line, file=out)


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO | None = None,
    refresher_factory: Callable[[], RecommendationCandidatePoolRefresher] | None = None,
) -> int:
    args = _parse_args(argv)
    selected_categories = list(args.category or _CATEGORIES)
    target = out or sys.stdout
    refresher = (
        refresher_factory() if refresher_factory is not None else _default_refresher_factory()
    )

    exit_code = 0
    for category in selected_categories:
        result = refresher.refresh_category(category)
        _print_result(category, result, out=target)
        if result.status == "error":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
