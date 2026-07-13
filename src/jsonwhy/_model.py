"""Public diagnostic data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JsonIssue:
    """One reason a Python value cannot be encoded as JSON.

    Attributes:
        path: A JSONPath-like location beginning with ``$``.
        kind: A stable, machine-readable issue identifier.
        value_type: The fully-qualified Python type name.
        message: A concise explanation for humans.
        suggestion: A likely fix, when one can be offered safely.
        value_repr: A bounded, best-effort representation of the value.
        json_pointer: The RFC 6901 location, or ``None`` when the location
            cannot exist in a JSON document.
    """

    path: str
    kind: str
    value_type: str
    message: str
    suggestion: str | None
    value_repr: str
    json_pointer: str | None = None

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
