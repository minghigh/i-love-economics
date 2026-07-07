from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .commands import apply_card, daily, draft, draft_day, rewrite


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = list(sys.argv[1:] if argv is None else argv)
    command = os.environ.get("ECONOMICS_COMMAND")
    if command and (not args or args[0] not in {"daily", "rewrite", "apply-card", "draft", "draft-day"}):
        args.insert(0, command)
    elif not args or args[0].startswith("-"):
        args.insert(0, "daily")

    parser = argparse.ArgumentParser(prog="economics-daily")
    sub = parser.add_subparsers(dest="command", required=True)

    daily_parser = sub.add_parser("daily")
    daily_parser.add_argument("--date", default="yesterday")
    daily_parser.add_argument("--force", action="store_true")
    daily_parser.add_argument("--limit", type=int, default=5)

    rewrite_parser = sub.add_parser("rewrite")
    rewrite_parser.add_argument("candidate_dir")

    card_parser = sub.add_parser("apply-card")
    card_parser.add_argument("candidate_dir")

    draft_parser = sub.add_parser("draft")
    draft_parser.add_argument("candidate_dir")

    draft_day_parser = sub.add_parser("draft-day")
    draft_day_parser.add_argument("day")

    ns = parser.parse_args(args)
    if ns.command == "daily":
        daily(ns.date, ns.force, ns.limit)
    elif ns.command == "rewrite":
        rewrite(ns.candidate_dir)
    elif ns.command == "apply-card":
        apply_card(ns.candidate_dir)
    elif ns.command == "draft":
        draft(ns.candidate_dir)
    elif ns.command == "draft-day":
        draft_day(ns.day)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
