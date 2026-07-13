"""Command-line interface for Python literals."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Sequence

from . import __version__, explain


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jsonwhy",
        description="Explain why a Python literal is not JSON serializable.",
    )
    parser.add_argument(
        "literal",
        nargs="?",
        help="Python literal to inspect. Reads standard input when omitted.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reject NaN and infinity, matching allow_nan=False.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable diagnostic JSON.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""

    args = _parser().parse_args(argv)
    source = args.literal if args.literal is not None else sys.stdin.read()
    if not source.strip():
        print(
            "jsonwhy: provide a Python literal or pipe one on standard input",
            file=sys.stderr,
        )
        return 2
    try:
        value = ast.literal_eval(source)
    except (SyntaxError, ValueError) as exc:
        print(f"jsonwhy: invalid Python literal: {exc}", file=sys.stderr)
        return 2

    issues = explain(value, allow_nan=not args.strict)
    if args.json_output:
        print(json.dumps([issue.as_dict() for issue in issues], indent=2))
    elif issues:
        for issue in issues:
            print(f"{issue.path}: {issue.message}")
            if issue.suggestion:
                print(f"  Fix: {issue.suggestion}")
    else:
        print("No JSON serialization issues found.")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
