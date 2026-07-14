"""JSON compatibility diagnostics."""

from __future__ import annotations

import json
import math
import reprlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TypeAlias

from ._errors import _exception_message, _exception_type_name
from ._model import JsonIssue, JsonReport, PathSegment, qualified_type_name
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


def _path_for_key(
    parent: str,
    key: object,
    *,
    include_value_repr: bool,
) -> str:
    if isinstance(key, str):
        if key.isidentifier():
            return f"{parent}.{key}"
        return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"
    if key is None:
        return f"{parent}[null]"
    if isinstance(key, bool):
        return f"{parent}[{str(key).lower()}]"
    if isinstance(key, int):
        return f"{parent}[{int.__repr__(key)}]"
    if isinstance(key, float):
        return f"{parent}[{float.__repr__(key)}]"
    if not include_value_repr:
        return f"{parent}[<unsupported key>]"
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


def _segments_child(
    parent: tuple[PathSegment, ...] | None,
    segment: PathSegment | None,
) -> tuple[PathSegment, ...] | None:
    if parent is None or segment is None:
        return None
    return (*parent, segment)


@dataclass(slots=True)
class _VisitFrame:
    value: object
    path: str
    json_pointer: str | None
    path_segments: tuple[PathSegment, ...] | None
    depth: int


@dataclass(slots=True)
class _LeaveFrame:
    identity: int


@dataclass(slots=True)
class _SequenceFrame:
    iterator: Iterator[object]
    path: str
    json_pointer: str | None
    path_segments: tuple[PathSegment, ...] | None
    depth: int
    index: int = 0


@dataclass(slots=True)
class _MappingFrame:
    iterator: Iterator[tuple[object, object]]
    path: str
    json_pointer: str | None
    path_segments: tuple[PathSegment, ...] | None
    depth: int


_Frame: TypeAlias = _VisitFrame | _LeaveFrame | _SequenceFrame | _MappingFrame


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
        max_nodes: int | None,
        include_value_repr: bool,
    ) -> None:
        self.skipkeys = skipkeys
        self.allow_nan = allow_nan
        self.check_circular = check_circular
        self.default = default
        self.max_issues = max_issues
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.include_value_repr = include_value_repr
        self.nodes_visited = 0
        self.truncated = False
        self.truncation_reasons: list[str] = []
        self._issues_yielded = 0
        self._ancestors: set[int] = set()

    def _mark_truncated(self, reason: str) -> None:
        self.truncated = True
        if reason not in self.truncation_reasons:
            self.truncation_reasons.append(reason)

    def _issue(
        self,
        *,
        path: str,
        json_pointer: str | None,
        path_segments: tuple[PathSegment, ...] | None,
        kind: str,
        value: object,
        message: str,
        suggestion: str | None,
    ) -> JsonIssue:
        self._issues_yielded += 1
        return JsonIssue(
            path=path,
            kind=kind,
            value_type=qualified_type_name(value),
            message=message,
            suggestion=suggestion,
            value_repr=(_safe_repr(value) if self.include_value_repr else "<redacted>"),
            json_pointer=json_pointer,
            path_segments=path_segments,
        )

    def iter_issues(self, value: object) -> Iterator[JsonIssue]:
        stack: list[_Frame] = [_VisitFrame(value, "$", "", (), 0)]

        while stack:
            if self._issues_yielded >= self.max_issues:
                self._mark_truncated("max_issues")
                return

            frame = stack.pop()
            if isinstance(frame, _LeaveFrame):
                self._ancestors.remove(frame.identity)
                continue

            if isinstance(frame, _SequenceFrame):
                try:
                    item = next(frame.iterator)
                except StopIteration:
                    continue
                index = frame.index
                frame.index += 1
                stack.append(frame)
                stack.append(
                    _VisitFrame(
                        item,
                        f"{frame.path}[{index}]",
                        _pointer_child(frame.json_pointer, str(index)),
                        _segments_child(frame.path_segments, index),
                        frame.depth + 1,
                    )
                )
                continue

            if isinstance(frame, _MappingFrame):
                try:
                    key, item = next(frame.iterator)
                except StopIteration:
                    continue
                stack.append(frame)
                item_path = _path_for_key(
                    frame.path,
                    key,
                    include_value_repr=self.include_value_repr,
                )
                token = _pointer_token(key)
                item_pointer = _pointer_child(frame.json_pointer, token)
                item_segments = _segments_child(frame.path_segments, token)
                valid_key = key is None or isinstance(key, (str, int, float, bool))
                if not valid_key and self.skipkeys:
                    continue
                stack.append(
                    _VisitFrame(
                        item,
                        item_path,
                        item_pointer,
                        item_segments,
                        frame.depth + 1,
                    )
                )
                if not valid_key:
                    yield self._issue(
                        path=item_path,
                        json_pointer=item_pointer,
                        path_segments=item_segments,
                        kind="unsupported_key",
                        value=key,
                        message=(
                            "JSON object keys must be str, int, float, bool, or None."
                        ),
                        suggestion=(
                            "Convert the key to a string, or use skipkeys=True to "
                            "omit it."
                        ),
                    )
                elif (
                    isinstance(key, float)
                    and not self.allow_nan
                    and not math.isfinite(key)
                ):
                    yield self._issue(
                        path=item_path,
                        json_pointer=item_pointer,
                        path_segments=item_segments,
                        kind="non_finite_float_key",
                        value=key,
                        message=(
                            "A non-finite float key is forbidden when allow_nan=False."
                        ),
                        suggestion="Replace the key with a finite number or string.",
                    )
                continue

            if self.max_nodes is not None and self.nodes_visited >= self.max_nodes:
                self._mark_truncated("max_nodes")
                stack.clear()
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="maximum_nodes",
                    value=frame.value,
                    message=(
                        f"Diagnostic traversal reached max_nodes={self.max_nodes}."
                    ),
                    suggestion="Increase max_nodes, or inspect a smaller subtree.",
                )
                return

            self.nodes_visited += 1
            if frame.depth > self.max_depth:
                self._mark_truncated("max_depth")
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="maximum_depth",
                    value=frame.value,
                    message=(
                        f"Diagnostic traversal exceeded max_depth={self.max_depth}."
                    ),
                    suggestion="Increase max_depth, or flatten the nested structure.",
                )
                continue

            value = frame.value
            if value is None or isinstance(value, (str, int, bool)):
                continue
            if isinstance(value, float):
                if not self.allow_nan and not math.isfinite(value):
                    yield self._issue(
                        path=frame.path,
                        json_pointer=frame.json_pointer,
                        path_segments=frame.path_segments,
                        kind="non_finite_float",
                        value=value,
                        message=(
                            "Non-finite floats are forbidden when allow_nan=False."
                        ),
                        suggestion=(
                            "Replace NaN or infinity with None, a string, or a finite "
                            "number."
                        ),
                    )
                continue
            if isinstance(value, dict):
                identity = id(value)
                if identity in self._ancestors:
                    yield self._issue(
                        path=frame.path,
                        json_pointer=frame.json_pointer,
                        path_segments=frame.path_segments,
                        kind="circular_reference",
                        value=value,
                        message="This container creates a circular reference.",
                        suggestion=(
                            "Remove the cycle or replace the repeated reference with "
                            "an identifier."
                        ),
                    )
                    continue
                self._ancestors.add(identity)
                stack.append(_LeaveFrame(identity))
                stack.append(
                    _MappingFrame(
                        iter(dict.items(value)),
                        frame.path,
                        frame.json_pointer,
                        frame.path_segments,
                        frame.depth,
                    )
                )
                continue
            if isinstance(value, (list, tuple)):
                identity = id(value)
                if identity in self._ancestors:
                    yield self._issue(
                        path=frame.path,
                        json_pointer=frame.json_pointer,
                        path_segments=frame.path_segments,
                        kind="circular_reference",
                        value=value,
                        message="This container creates a circular reference.",
                        suggestion=(
                            "Remove the cycle or replace the repeated reference with "
                            "an identifier."
                        ),
                    )
                    continue
                self._ancestors.add(identity)
                stack.append(_LeaveFrame(identity))
                iterator = (
                    list.__iter__(value)
                    if isinstance(value, list)
                    else tuple.__iter__(value)
                )
                stack.append(
                    _SequenceFrame(
                        iterator,
                        frame.path,
                        frame.json_pointer,
                        frame.path_segments,
                        frame.depth,
                    )
                )
                continue

            if self.default is None:
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="unsupported_type",
                    value=value,
                    message=(
                        f"Object of type {type(value).__name__} is not JSON "
                        "serializable."
                    ),
                    suggestion=suggestion_for(value),
                )
                continue

            identity = id(value)
            if identity in self._ancestors:
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="circular_reference",
                    value=value,
                    message="The default encoder produced a circular reference.",
                    suggestion=(
                        "Return a new JSON-compatible value from the default encoder."
                    ),
                )
                continue

            self._ancestors.add(identity)
            try:
                replacement = self.default(value)
            except Exception as exc:
                self._ancestors.remove(identity)
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="default_handler_failed",
                    value=value,
                    message=(
                        f"The default encoder raised {_exception_type_name(exc)}: "
                        f"{_exception_message(exc)}"
                    ),
                    suggestion=suggestion_for(value),
                )
                continue
            if replacement is value:
                self._ancestors.remove(identity)
                yield self._issue(
                    path=frame.path,
                    json_pointer=frame.json_pointer,
                    path_segments=frame.path_segments,
                    kind="default_handler_cycle",
                    value=value,
                    message=(
                        "The default encoder returned the original unsupported object."
                    ),
                    suggestion=(
                        "Return a new JSON-compatible value from the default encoder."
                    ),
                )
                continue
            stack.append(_LeaveFrame(identity))
            stack.append(
                _VisitFrame(
                    replacement,
                    frame.path,
                    frame.json_pointer,
                    frame.path_segments,
                    frame.depth + 1,
                )
            )


def _new_inspector(
    *,
    skipkeys: bool,
    allow_nan: bool,
    check_circular: bool,
    default: DefaultHandler | None,
    max_issues: int,
    max_depth: int,
    max_nodes: int | None,
    include_value_repr: bool,
) -> _Inspector:
    _validate_limits(max_issues, max_depth, max_nodes)
    return _Inspector(
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )


def iter_diagnostics(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: DefaultHandler | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> Iterator[JsonIssue]:
    """Yield JSON compatibility issues as they are discovered."""

    inspector = _new_inspector(
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )
    return inspector.iter_issues(value)


def inspect_diagnostics(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: DefaultHandler | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> JsonReport:
    """Return a structured report for a JSON compatibility inspection."""

    inspector = _new_inspector(
        skipkeys=skipkeys,
        allow_nan=allow_nan,
        check_circular=check_circular,
        default=default,
        max_issues=max_issues,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_value_repr=include_value_repr,
    )
    issues = tuple(inspector.iter_issues(value))
    return JsonReport(
        issues=issues,
        nodes_visited=inspector.nodes_visited,
        truncated=inspector.truncated,
        truncation_reasons=tuple(inspector.truncation_reasons),
    )


def diagnose(
    value: object,
    *,
    skipkeys: bool = False,
    allow_nan: bool = True,
    check_circular: bool = True,
    default: DefaultHandler | None = None,
    max_issues: int = 100,
    max_depth: int = 1000,
    max_nodes: int | None = None,
    include_value_repr: bool = True,
) -> tuple[JsonIssue, ...]:
    """Return all discoverable JSON serialization issues in ``value``."""

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
    ).issues


def _validate_limits(
    max_issues: int,
    max_depth: int,
    max_nodes: int | None = None,
) -> None:
    if max_issues < 1:
        raise ValueError("max_issues must be at least 1")
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_nodes is not None and max_nodes < 1:
        raise ValueError("max_nodes must be at least 1")
