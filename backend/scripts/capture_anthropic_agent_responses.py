from __future__ import annotations

import argparse
from pathlib import Path

from financehub_market_api.recommendation.agents.sample_capture import capture_all_agents


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "anthropic_responses"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Anthropic responses for all recommendation agents.")
    parser.add_argument(
        "--risk-profile",
        default="balanced",
        choices=("conservative", "stable", "balanced", "growth", "aggressive"),
        help="Risk profile used for running the six-stage capture flow.",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=_default_fixtures_dir(),
        help="Directory where sanitized fixture payloads are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = capture_all_agents(
        risk_profile=args.risk_profile,
        fixtures_dir=args.fixtures_dir,
    )
    for item in summary:
        print(
            f"{item['request_name']}: phase={item['phase']}, "
            f"fixture_path={item['fixture_path'] or '-'}"
        )


if __name__ == "__main__":
    main()
