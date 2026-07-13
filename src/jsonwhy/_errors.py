"""Rich JSON serialization errors."""

from __future__ import annotations

from collections.abc import Sequence

from ._model import JsonIssue


def _exception_message(error: BaseException) -> str:
    try:
        return str(error)
    except Exception:
        return "<exception message unavailable>"


def _exception_type_name(error: BaseException) -> str:
    try:
        return type(error).__name__
    except Exception:
        return "<unknown exception>"


class JsonWhyError(TypeError):
    """Raised when JSON serialization fails with structured diagnostics."""

    def __init__(
        self,
        issues: Sequence[JsonIssue],
        *,
        original: BaseException | None = None,
    ) -> None:
        self.issues = tuple(issues)
        self.original = original
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        count = len(self.issues)
        heading = f"JSON serialization failed with {count} issue"
        if count != 1:
            heading += "s"
        lines = [f"{heading}:"]
        for index, issue in enumerate(self.issues, start=1):
            lines.append(f"{index}. {issue.path}: {issue.message}")
            lines.append(f"   Value: {issue.value_repr} ({issue.value_type})")
            if issue.suggestion:
                lines.append(f"   Fix: {issue.suggestion}")
        if self.original is not None:
            lines.append(
                "Original error: "
                f"{_exception_type_name(self.original)}: "
                f"{_exception_message(self.original)}"
            )
        return "\n".join(lines)
