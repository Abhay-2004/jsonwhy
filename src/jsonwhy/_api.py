"""Public API and standard-library-compatible wrappers."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import IO, Any, NoReturn

from ._diagnose import _validate_limits, diagnose
from ._errors import JsonWhyError, _exception_message
from ._model import JsonIssue, qualified_type_name

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
        include_value_repr=include_value_repr,
    )


def check(value: object, **options: Any) -> bool:
    """Return ``True`` when no JSON compatibility issues are found."""

    return not explain(value, **options)


def assert_serializable(value: object, **options: Any) -> None:
    """Raise ``JsonWhyError`` if ``value`` is not JSON serializable."""

    issues = explain(value, **options)
    if issues:
        raise JsonWhyError(issues)


def _fallback_issue(
    value: object,
    original: BaseException,
    *,
    include_value_repr: bool,
) -> JsonIssue:
    return JsonIssue(
        path="$",
        json_pointer="",
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
    include_value_repr: bool,
) -> NoReturn:
    try:
        issues = explain(
            value,
            skipkeys=skipkeys,
            allow_nan=allow_nan,
            check_circular=check_circular,
            default=default,
            max_issues=max_issues,
            max_depth=max_depth,
            include_value_repr=include_value_repr,
        )
    except Exception:
        issues = ()
    if not issues:
        issues = (
            _fallback_issue(
                value,
                original,
                include_value_repr=include_value_repr,
            ),
        )
    raise JsonWhyError(issues, original=original) from original


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
    diagnostic_include_value_repr: bool = True,
    **kw: Any,
) -> str:
    """Serialize like ``json.dumps``, but explain failures with exact paths."""

    _validate_limits(diagnostic_max_issues, diagnostic_max_depth)
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
    diagnostic_include_value_repr: bool = True,
    **kw: Any,
) -> None:
    """Serialize like ``json.dump``, but explain failures with exact paths."""

    _validate_limits(diagnostic_max_issues, diagnostic_max_depth)
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
            include_value_repr=diagnostic_include_value_repr,
        )
