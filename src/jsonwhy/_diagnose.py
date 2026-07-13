"""Recursive JSON compatibility diagnostics."""

from __future__ import annotations

import json
import math
import reprlib
from collections.abc import Callable
from typing import cast

from ._errors import _exception_message, _exception_type_name
from ._model import JsonIssue, qualified_type_name
from ._registry import suggestion_for

DefaultHandler = Callable[[object], object]


def _safe_repr(value: object) -> str:
    renderer = reprlib.Repr()
    renderer.maxstring = 120
    renderer.maxother = 120
    renderer.maxlist = 6
    renderer.maxtuple = 6
    renderer.maxdict = 4
    renderer.maxset = 6
    try:
        return renderer.repr(value)
    except Exception:
        return f"<{qualified_type_name(value)} instance; repr() failed>"


def _path_for_key(parent: str, key: object) -> str:
    if isinstance(key, str):
        if key.isidentifier():
            return f"{parent}.{key}"
        return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"
    if key is None:
        return f"{parent}[null]"
    if isinstance(key, bool):
        return f"{parent}[{str(key).lower()}]"
    if isinstance(key, (int, float)):
        return f"{parent}[{key!r}]"
    return f"{parent}[<key {_safe_repr(key)}>]"


def _pointer_token(key: object) -> str | None:
    if isinstance(key, str):
        return str.__str__(key)
    if key is None:
        return "null"
    if isinstance(key, bool):
        return str(key).lower()
    if isinstance(key, int):
        return int.__repr__(key)
    if isinstance(key, float):
        if math.isnan(key):
            return "NaN"
        if key == math.inf:
            return "Infinity"
        if key == -math.inf:
            return "-Infinity"
        return float.__repr__(key)
    return None


def _pointer_child(parent: str | None, token: str | None) -> str | None:
    if parent is None or token is None:
        return None
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


class _Inspector:
    def __init__(
        self,
        *,
        skipkeys: bool,
        allow_nan: bool,
        check_circular: bool,
        default: DefaultHandler | None,
        max_issues: int,
        max_depth: int,
    ) -> None:
        self.skipkeys = skipkeys
        self.allow_nan = allow_nan
        self.check_circular = check_circular
        self.default = default
        self.max_issues = max_issues
        self.max_depth = max_depth
        self.issues: list[JsonIssue] = []
        self.ancestors: set[int] = set()

    def inspect(self, value: object) -> tuple[JsonIssue, ...]:
        self._visit(value, "$", "", 0)
        return tuple(self.issues)

    def _add(
        self,
        *,
        path: str,
        json_pointer: str | None,
        kind: str,
        value: object,
        message: str,
        suggestion: str | None,
    ) -> None:
        if len(self.issues) >= self.max_issues:
            return
        self.issues.append(
            JsonIssue(
                path=path,
                kind=kind,
                value_type=qualified_type_name(value),
                message=message,
                suggestion=suggestion,
                value_repr=_safe_repr(value),
                json_pointer=json_pointer,
            )
        )

    def _visit(
        self,
        value: object,
        path: str,
        json_pointer: str | None,
        depth: int,
    ) -> None:
        if len(self.issues) >= self.max_issues:
            return
        if depth > self.max_depth:
            self._add(
                path=path,
                json_pointer=json_pointer,
                kind="maximum_depth",
                value=value,
                message=f"Diagnostic traversal exceeded max_depth={self.max_depth}.",
                suggestion="Increase max_depth, or flatten the nested structure.",
            )
            return

        if value is None or isinstance(value, (str, int, bool)):
            return
        if isinstance(value, float):
            if not self.allow_nan and not math.isfinite(value):
                self._add(
                    path=path,
                    json_pointer=json_pointer,
                    kind="non_finite_float",
                    value=value,
                    message="Non-finite floats are forbidden when allow_nan=False.",
                    suggestion=(
                        "Replace NaN or infinity with None, a string, or a finite "
                        "number."
                    ),
                )
            return
        if isinstance(value, dict):
            self._visit_container(value, path, json_pointer, depth, is_dict=True)
            return
        if isinstance(value, (list, tuple)):
            self._visit_container(value, path, json_pointer, depth, is_dict=False)
            return

        self._visit_unsupported(value, path, json_pointer, depth)

    def _visit_container(
        self,
        value: dict[object, object] | list[object] | tuple[object, ...],
        path: str,
        json_pointer: str | None,
        depth: int,
        *,
        is_dict: bool,
    ) -> None:
        identity = id(value)
        if identity in self.ancestors:
            self._add(
                path=path,
                json_pointer=json_pointer,
                kind="circular_reference",
                value=value,
                message="This container creates a circular reference.",
                suggestion=(
                    "Remove the cycle or replace the repeated reference with an "
                    "identifier."
                ),
            )
            return

        self.ancestors.add(identity)
        try:
            if is_dict:
                self._visit_dict(
                    cast(dict[object, object], value), path, json_pointer, depth
                )
            elif isinstance(value, list):
                for index, item in enumerate(list.__iter__(value)):
                    self._visit(
                        item,
                        f"{path}[{index}]",
                        _pointer_child(json_pointer, str(index)),
                        depth + 1,
                    )
            else:
                tuple_value = cast(tuple[object, ...], value)
                for index, item in enumerate(tuple.__iter__(tuple_value)):
                    self._visit(
                        item,
                        f"{path}[{index}]",
                        _pointer_child(json_pointer, str(index)),
                        depth + 1,
                    )
        finally:
            self.ancestors.remove(identity)

    def _visit_dict(
        self,
        value: dict[object, object],
        path: str,
        json_pointer: str | None,
        depth: int,
    ) -> None:
        for key, item in dict.items(value):
            item_path = _path_for_key(path, key)
            item_pointer = _pointer_child(json_pointer, _pointer_token(key))
            valid_key = key is None or isinstance(key, (str, int, float, bool))
            if not valid_key:
                if self.skipkeys:
                    continue
                self._add(
                    path=item_path,
                    json_pointer=item_pointer,
                    kind="unsupported_key",
                    value=key,
                    message="JSON object keys must be str, int, float, bool, or None.",
                    suggestion=(
                        "Convert the key to a string, or use skipkeys=True to omit it."
                    ),
                )
            elif (
                isinstance(key, float) and not self.allow_nan and not math.isfinite(key)
            ):
                self._add(
                    path=item_path,
                    json_pointer=item_pointer,
                    kind="non_finite_float_key",
                    value=key,
                    message="A non-finite float key is forbidden when allow_nan=False.",
                    suggestion="Replace the key with a finite number or string.",
                )
            self._visit(item, item_path, item_pointer, depth + 1)

    def _visit_unsupported(
        self,
        value: object,
        path: str,
        json_pointer: str | None,
        depth: int,
    ) -> None:
        if self.default is None:
            self._add(
                path=path,
                json_pointer=json_pointer,
                kind="unsupported_type",
                value=value,
                message=(
                    f"Object of type {type(value).__name__} is not JSON serializable."
                ),
                suggestion=suggestion_for(value),
            )
            return

        identity = id(value)
        if identity in self.ancestors:
            self._add(
                path=path,
                json_pointer=json_pointer,
                kind="circular_reference",
                value=value,
                message="The default encoder produced a circular reference.",
                suggestion=(
                    "Return a new JSON-compatible value from the default encoder."
                ),
            )
            return

        self.ancestors.add(identity)
        try:
            try:
                replacement = self.default(value)
            except Exception as exc:
                self._add(
                    path=path,
                    json_pointer=json_pointer,
                    kind="default_handler_failed",
                    value=value,
                    message=(
                        f"The default encoder raised {_exception_type_name(exc)}: "
                        f"{_exception_message(exc)}"
                    ),
                    suggestion=suggestion_for(value),
                )
                return
            if replacement is value:
                self._add(
                    path=path,
                    json_pointer=json_pointer,
                    kind="default_handler_cycle",
                    value=value,
                    message=(
                        "The default encoder returned the original unsupported object."
                    ),
                    suggestion=(
                        "Return a new JSON-compatible value from the default encoder."
                    ),
                )
                return
            self._visit(replacement, path, json_pointer, depth + 1)
        finally:
            self.ancestors.remove(identity)


def diagnose(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: DefaultHandler | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
) -> tuple[JsonIssue, ...]:
    """Return all discoverable JSON serialization issues in ``value``.

    ``default`` follows the meaning of ``json.dumps(default=...)`` and may be
    called while diagnosing unsupported values. ``check_circular`` is accepted
    for API parity; diagnostics always detect cycles to keep traversal safe.
    """

    if max_issues < 1:
        raise ValueError("max_issues must be at least 1")
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")

    inspector = _Inspector(
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
    )
    try:
        return inspector.inspect(value)
    except RecursionError:
        inspector._add(
            path="$",
            json_pointer="",
            kind="diagnostic_recursion_limit",
            value=value,
            message="Diagnostic traversal reached Python's recursion limit.",
            suggestion=(
                "Reduce max_depth, flatten the structure, or inspect smaller subtrees."
            ),
        )
        return tuple(inspector.issues)
