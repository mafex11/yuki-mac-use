"""CLI: `python -m yuki.feedback.cli` runs the daily learner for yesterday."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from yuki.feedback.learner import run_for_date


def main() -> None:
    for env in (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ):
        if env.exists():
            load_dotenv(env, override=False)
            break

    yesterday = date.today() - timedelta(days=1)
    updated = run_for_date(yesterday)
    print(
        f"yuki: feedback learner updated {updated} app note(s) for {yesterday}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
