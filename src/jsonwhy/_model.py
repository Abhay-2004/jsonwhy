"""Public diagnostic data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PathSegment = str | int


@dataclass(frozen=True, slots=True)
class JsonIssue:
    """One reason a Python value cannot be encoded as JSON.

    Attributes:
        path: A JSONPath-like location beginning with ``$``.
        kind: A stable, machine-readable issue identifier.
        value_type: The fully-qualified Python type name.
        message: A concise explanation for humans.
        suggestion: A likely fix, when one can be offered safely.
        value_repr: A bounded, best-effort representation, or ``<redacted>``.
        json_pointer: The RFC 6901 location, or ``None`` when the location
            cannot exist in a JSON document.
        path_segments: Object keys and array indexes as structured components,
            or ``None`` when the location cannot exist in a JSON document.
    """

    path: str
    kind: str
    value_type: str
    message: str
    suggestion: str | None
    value_repr: str
    json_pointer: str | None = None
    path_segments: tuple[PathSegment, ...] | None = field(
        default=None,
        compare=False,
    )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this issue."""

        return {
            "path": self.path,
            "kind": self.kind,
            "value_type": self.value_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "value_repr": self.value_repr,
            "json_pointer": self.json_pointer,
            "path_segments": (
                list(self.path_segments) if self.path_segments is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class JsonReport:
    """A complete or bounded JSON compatibility inspection."""

    issues: tuple[JsonIssue, ...]
    nodes_visited: int
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Return ``True`` only when the completed inspection found no issues."""

        return not self.issues and not self.truncated

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this report."""

        return {
            "ok": self.ok,
            "nodes_visited": self.nodes_visited,
            "truncated": self.truncated,
            "truncation_reasons": list(self.truncation_reasons),
            "issues": [issue.as_dict() for issue in self.issues],
        }


def qualified_type_name(value: object) -> str:
    """Return a useful, stable name for ``type(value)``."""

    try:
        value_type = type(value)
        if value_type.__module__ == "builtins":
            return value_type.__qualname__
        return f"{value_type.__module__}.{value_type.__qualname__}"
    except Exception:
        return "<unknown type>"
