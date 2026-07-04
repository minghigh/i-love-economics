from __future__ import annotations

from pathlib import Path

from .io import parse_target_date
from .pipeline import apply_card as apply_card_impl
from .pipeline import rewrite_candidate, run_daily


def daily(date_value: str, force: bool, limit: int) -> None:
    run_daily(parse_target_date(date_value), force, limit)


def rewrite(candidate_dir: str) -> None:
    rewrite_candidate(Path(candidate_dir))


def apply_card(candidate_dir: str) -> None:
    path = apply_card_impl(Path(candidate_dir))
    print(path)
