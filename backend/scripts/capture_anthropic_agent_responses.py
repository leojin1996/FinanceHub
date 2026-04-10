from __future__ import annotations

import argparse
from pathlib import Path

from financehub_market_api.recommendation.agents.sample_capture import CaptureRunError, CaptureSummary, capture_all_agents


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "anthropic_responses"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Anthropic responses for all recommendation agents.")
    parser.add_argument(
        "--risk-profile",
        default="balanced",
        choices=("conservative", "stable", "balanced", "growth", "aggressive"),
        help="Risk profile used for running the five-agent capture flow.",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=_default_fixtures_dir(),
        help="Directory where sanitized fixture payloads are written.",
    )
    return parser.parse_args()


def _print_summary(summary: list[CaptureSummary]) -> None:
    for item in summary:
        line = (
            f"{item['request_name']}: phase={item['phase'] or '-'}, "
            f"fixture_path={item['fixture_path'] or '-'}"
        )
        error = item.get("error")
        if error:
            line = f"{line}, error={error}"
        print(line)


def main() -> None:
    args = _parse_args()
    try:
        summary = capture_all_agents(
            risk_profile=args.risk_profile,
            fixtures_dir=args.fixtures_dir,
        )
    except CaptureRunError as exc:
        _print_summary(exc.summary)
        raise SystemExit(1) from exc
    _print_summary(summary)


if __name__ == "__main__":
    main()
