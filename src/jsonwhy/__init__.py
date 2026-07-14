"""Explain exactly why and where Python objects fail JSON serialization."""

from ._api import assert_serializable, check, dump, dumps, explain, inspect, iter_issues
from ._errors import JsonWhyError
from ._model import JsonIssue, JsonReport
from ._registry import register_suggestion, unregister_suggestion

__all__ = [
    "JsonIssue",
    "JsonReport",
    "JsonWhyError",
    "assert_serializable",
    "check",
    "dump",
    "dumps",
    "explain",
    "inspect",
    "iter_issues",
    "register_suggestion",
    "unregister_suggestion",
]

__version__ = "0.4.0"
