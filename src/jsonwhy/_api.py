"""Public API and standard-library-compatible wrappers."""

from __future__ import annotations

import json as _json
from collections.abc import Callable, Iterator
from typing import IO, Any, NoReturn

from ._diagnose import (
    _validate_limits,
    diagnose,
    inspect_diagnostics,
    iter_diagnostics,
)
from ._errors import JsonWhyError, _exception_message
from ._model import JsonIssue, JsonReport, qualified_type_name

_SERIALIZATION_ERRORS = (TypeError, ValueError, OverflowError, RecursionError)


def explain(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: Callable[[object], object] | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> tuple[JsonIssue, ...]:
    """Return structured explanations without raising ``JsonWhyError``.

    Set ``include_value_repr=False`` to replace each issue's ``value_repr``
    with ``<redacted>`` without calling ``repr()`` on that value.
    """

    return diagnose(
        value,
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )


def iter_issues(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: Callable[[object], object] | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> Iterator[JsonIssue]:
    """Yield structured explanations as they are discovered."""

    return iter_diagnostics(
        value,
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )


def inspect(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: Callable[[object], object] | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> JsonReport:
    """Return a structured report for a JSON compatibility inspection."""

    return inspect_diagnostics(
        value,
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )


def check(value: object, **options: Any) -> bool:
    """Return ``True`` when no JSON compatibility issues are found."""

    return inspect(value, **options).ok


def assert_serializable(value: object, **options: Any) -> None:
    """Raise ``JsonWhyError`` if ``value`` is not JSON serializable."""

    report = inspect(value, **options)
    if not report.ok:
        raise JsonWhyError(report.issues, report=report)


def _fallback_issue(
    value: object,
    original: BaseException,
    *,
    include_value_repr: bool,
) -> JsonIssue:
    return JsonIssue(
        path="$",
        json_pointer="",
        path_segments=(),
        kind="serialization_error",
        value_type=qualified_type_name(value),
        message=_exception_message(original),
        suggestion=(
            "Inspect custom encoder options or reduce this to a smaller reproduction."
        ),
        value_repr=(
            f"<{qualified_type_name(value)}>" if include_value_repr else "<redacted>"
        ),
    )


def _raise_diagnostic(
    value: object,
    original: BaseException,
    *,
    skipkeys: bool,
    allow_nan: bool,
    check_circular: bool,
    default: Callable[[object], object] | None,
    max_issues: int,
    max_depth: int,
    max_nodes: int | None,
    include_value_repr: bool,
) -> NoReturn:
    try:
        report = inspect(
            value,
            skipkeys=skipkeys,
            allow_nan=allow_nan,
            check_circular=check_circular,
            default=default,
            max_issues=max_issues,
            max_depth=max_depth,
            max_nodes=max_nodes,
            include_value_repr=include_value_repr,
        )
    except Exception:
        report = JsonReport((), nodes_visited=0)
    if not report.issues:
        issues = (
            _fallback_issue(
                value,
                original,
                include_value_repr=include_value_repr,
            ),
        )
        report = JsonReport(issues, nodes_visited=report.nodes_visited)
    raise JsonWhyError(report.issues, original=original, report=report) from original


def _custom_encoder_default(
    cls: type[_json.JSONEncoder] | None,
    *,
    skipkeys: bool,
    ensure_ascii: bool,
    check_circular: bool,
    allow_nan: bool,
    indent: int | str | None,
    separators: tuple[str, str] | None,
    default: Callable[[object], object] | None,
    sort_keys: bool,
    extra: dict[str, Any],
) -> Callable[[object], object] | None:
    """Resolve the effective fallback used by a custom JSON encoder."""

    if default is not None or cls is None or cls is _json.JSONEncoder:
        return default
    try:
        encoder = cls(
            skipkeys=skipkeys,
            ensure_ascii=ensure_ascii,
            check_circular=check_circular,
            allow_nan=allow_nan,
            indent=indent,
            separators=separators,
            default=default,
            sort_keys=sort_keys,
            **extra,
        )
        return encoder.default
    except Exception:
        return default


def dumps(
    obj: Any,
    *,
    skipkeys: bool = False,
    ensure_ascii: bool = True,
    check_circular: bool = True,
    allow_nan: bool = True,
    cls: type[_json.JSONEncoder] | None = None,
    indent: int | str | None = None,
    separators: tuple[str, str] | None = None,
    default: Callable[[object], object] | None = None,
    sort_keys: bool = False,
    diagnostic_max_issues: int = 100,
    diagnostic_max_depth: int = 1000,
    diagnostic_max_nodes: int | None = None,
    diagnostic_include_value_repr: bool = True,
    **kw: Any,
) -> str:
    """Serialize like ``json.dumps``, but explain failures with exact paths."""

    _validate_limits(
        diagnostic_max_issues,
        diagnostic_max_depth,
        diagnostic_max_nodes,
    )
    try:
        return _json.dumps(
            obj,
            skipkeys=skipkeys,
            ensure_ascii=ensure_ascii,
            check_circular=check_circular,
            allow_nan=allow_nan,
            cls=cls,
            indent=indent,
            separators=separators,
            default=default,
            sort_keys=sort_keys,
            **kw,
        )
    except _SERIALIZATION_ERRORS as exc:
        diagnostic_default = _custom_encoder_default(
            cls,
            skipkeys=skipkeys,
            ensure_ascii=ensure_ascii,
            check_circular=check_circular,
            allow_nan=allow_nan,
            indent=indent,
            separators=separators,
            default=default,
            sort_keys=sort_keys,
            extra=kw,
        )
        _raise_diagnostic(
            obj,
            exc,
            skipkeys=skipkeys,
            allow_nan=allow_nan,
            check_circular=check_circular,
            default=diagnostic_default,
            max_issues=diagnostic_max_issues,
            max_depth=diagnostic_max_depth,
            max_nodes=diagnostic_max_nodes,
            include_value_repr=diagnostic_include_value_repr,
        )


def dump(
    obj: Any,
    fp: IO[str],
    *,
    skipkeys: bool = False,
    ensure_ascii: bool = True,
    check_circular: bool = True,
    allow_nan: bool = True,
    cls: type[_json.JSONEncoder] | None = None,
    indent: int | str | None = None,
    separators: tuple[str, str] | None = None,
    default: Callable[[object], object] | None = None,
    sort_keys: bool = False,
    diagnostic_max_issues: int = 100,
    diagnostic_max_depth: int = 1000,
    diagnostic_max_nodes: int | None = None,
    diagnostic_include_value_repr: bool = True,
    **kw: Any,
) -> None:
    """Serialize like ``json.dump``, but explain failures with exact paths."""

    _validate_limits(
        diagnostic_max_issues,
        diagnostic_max_depth,
        diagnostic_max_nodes,
    )
    try:
        _json.dump(
            obj,
            fp,
            skipkeys=skipkeys,
            ensure_ascii=ensure_ascii,
            check_circular=check_circular,
            allow_nan=allow_nan,
            cls=cls,
            indent=indent,
            separators=separators,
            default=default,
            sort_keys=sort_keys,
            **kw,
        )
    except _SERIALIZATION_ERRORS as exc:
        diagnostic_default = _custom_encoder_default(
            cls,
            skipkeys=skipkeys,
            ensure_ascii=ensure_ascii,
            check_circular=check_circular,
            allow_nan=allow_nan,
            indent=indent,
            separators=separators,
            default=default,
            sort_keys=sort_keys,
            extra=kw,
        )
        _raise_diagnostic(
            obj,
            exc,
            skipkeys=skipkeys,
            allow_nan=allow_nan,
            check_circular=check_circular,
            default=diagnostic_default,
            max_issues=diagnostic_max_issues,
            max_depth=diagnostic_max_depth,
            max_nodes=diagnostic_max_nodes,
            include_value_repr=diagnostic_include_value_repr,
        )
