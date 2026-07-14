"""Command-line interface for Python literals."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Sequence

from . import __version__, inspect


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


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
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable diagnostic JSON.",
    )
    output.add_argument(
        "--json-report",
        action="store_true",
        help="Emit a JSON report with traversal metadata.",
    )
    parser.add_argument(
        "--path-style",
        choices=("jsonpath", "pointer"),
        default="jsonpath",
        help="Location style for text output (default: jsonpath).",
    )
    parser.add_argument(
        "--max-issues",
        type=_positive_int,
        default=100,
        help="Maximum number of issues to report (default: 100).",
    )
    parser.add_argument(
        "--max-depth",
        type=_non_negative_int,
        default=1000,
        help="Maximum diagnostic traversal depth (default: 1000).",
    )
    parser.add_argument(
        "--max-nodes",
        type=_positive_int,
        default=None,
        help="Maximum number of values to inspect (default: unlimited).",
    )
    parser.add_argument(
        "--redact-values",
        action="store_true",
        help="Replace each issue's value_repr with <redacted>.",
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

    report = inspect(
        value,
        allow_nan=not args.strict,
        max_issues=args.max_issues,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        include_value_repr=not args.redact_values,
    )
    if args.json_output:
        print(json.dumps([issue.as_dict() for issue in report.issues], indent=2))
    elif args.json_report:
        print(json.dumps(report.as_dict(), indent=2))
    elif report.issues:
        for issue in report.issues:
            if args.path_style == "pointer":
                location = issue.json_pointer
                if location == "":
                    location = "<root>"
                elif location is None:
                    location = "<no JSON Pointer>"
            else:
                location = issue.path
            print(f"{location}: {issue.message}")
            if issue.suggestion:
                print(f"  Fix: {issue.suggestion}")
        if report.truncated:
            reasons = ", ".join(report.truncation_reasons)
            print(f"Diagnostic traversal was truncated: {reasons}.")
    else:
        print("No JSON serialization issues found.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
