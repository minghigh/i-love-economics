from __future__ import annotations

from pathlib import Path

from .io import parse_target_date, run_dir
from .pipeline import apply_card as apply_card_impl
from .pipeline import rewrite_candidate, run_daily
from .wechat import WeChatAPIError, add_day_drafts, add_draft


def daily(date_value: str, force: bool, limit: int) -> None:
    run_daily(parse_target_date(date_value), force, limit)


def rewrite(candidate_dir: str) -> None:
    rewrite_candidate(Path(candidate_dir))


def apply_card(candidate_dir: str) -> None:
    path = apply_card_impl(Path(candidate_dir))
    print(path)


def draft(candidate_dir: str) -> None:
    try:
        path = add_draft(Path(candidate_dir))
    except WeChatAPIError as exc:
        raise SystemExit(str(exc)) from exc
    print(path)


def draft_day(day: str) -> None:
    path = Path(day) if "/" in day else run_dir(parse_target_date(day))
    try:
        for draft_path in add_day_drafts(path):
            print(draft_path)
    except WeChatAPIError as exc:
        raise SystemExit(str(exc)) from exc
