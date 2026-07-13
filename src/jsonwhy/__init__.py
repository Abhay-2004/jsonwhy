"""Explain exactly why and where Python objects fail JSON serialization."""

from ._api import assert_serializable, check, dump, dumps, explain
from ._errors import JsonWhyError
from ._model import JsonIssue
from ._registry import register_suggestion, unregister_suggestion

__all__ = [
    "JsonIssue",
    "JsonWhyError",
    "assert_serializable",
    "check",
    "dump",
    "dumps",
    "explain",
    "register_suggestion",
    "unregister_suggestion",
]

__version__ = "0.2.0"
