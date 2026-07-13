"""Suggestion lookup and customization."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import enum
import pathlib
import threading
import uuid
from collections.abc import Callable

SuggestionProvider = str | Callable[[object], str | None]

_custom_suggestions: dict[type[object], SuggestionProvider] = {}
_registry_lock = threading.RLock()


def register_suggestion(
    value_type: type[object],
    suggestion: SuggestionProvider,
) -> None:
    """Register a fix suggestion for a type and its subclasses.

    Later registrations replace earlier registrations for the same type.
    The registry is process-local and safe to update from multiple threads.
    """

    if not isinstance(value_type, type):
        raise TypeError("value_type must be a type")
    if not isinstance(suggestion, str) and not callable(suggestion):
        raise TypeError("suggestion must be a string or callable")
    with _registry_lock:
        _custom_suggestions[value_type] = suggestion


def unregister_suggestion(value_type: type[object]) -> bool:
    """Remove a registered suggestion, returning whether it existed."""

    with _registry_lock:
        return _custom_suggestions.pop(value_type, None) is not None


def suggestion_for(value: object) -> str:
    """Return a custom or built-in suggestion for an unsupported value."""

    with _registry_lock:
        registered = tuple(_custom_suggestions.items())
    for value_type, provider in registered:
        if isinstance(value, value_type):
            try:
                result = provider(value) if callable(provider) else provider
                if isinstance(result, str) and result:
                    return str(result)
            except Exception:
                continue

    if isinstance(value, dt.datetime):
        return "Convert it with value.isoformat(); preserve timezone information."
    if isinstance(value, (dt.date, dt.time)):
        return "Convert it with value.isoformat()."
    if isinstance(value, decimal.Decimal):
        return (
            "Use str(value) to preserve precision, or float(value) if loss is "
            "acceptable."
        )
    if isinstance(value, uuid.UUID):
        return "Convert it with str(value)."
    if isinstance(value, pathlib.PurePath):
        return "Convert it with str(value)."
    if isinstance(value, enum.Enum):
        return "Serialize value.value (or value.name if that is your public format)."
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return "Convert it with dataclasses.asdict(value)."
    if isinstance(value, (set, frozenset)):
        return "Convert it to a list; sort first if deterministic output matters."
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "Decode text bytes, or base64-encode arbitrary binary data."
    if isinstance(value, complex):
        return (
            "Represent it explicitly, for example "
            "{'real': value.real, 'imag': value.imag}."
        )

    module = type(value).__module__
    name = type(value).__name__
    if module.startswith("numpy"):
        if name == "ndarray":
            return "Convert the NumPy array with value.tolist()."
        return "Convert the NumPy scalar with value.item()."
    if module.startswith("pandas"):
        if name in {"DataFrame", "Series", "Index"}:
            return (
                "Convert the pandas object explicitly, such as value.to_dict() "
                "or value.tolist()."
            )
        if name == "Timestamp":
            return "Convert the pandas timestamp with value.isoformat()."

    return (
        "Provide json.dumps(default=...), or convert this value to a "
        "JSON-compatible type."
    )
