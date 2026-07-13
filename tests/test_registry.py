from __future__ import annotations

import datetime as dt
import enum
import unittest
import uuid
from pathlib import Path
from typing import Any

import jsonwhy


class RegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        jsonwhy.unregister_suggestion(Token)

    def test_string_suggestion(self) -> None:
        jsonwhy.register_suggestion(Token, "Use token.public_id.")
        issue = jsonwhy.explain({"token": Token()})[0]
        self.assertEqual(issue.suggestion, "Use token.public_id.")

    def test_callable_suggestion_receives_value(self) -> None:
        jsonwhy.register_suggestion(
            Token,
            lambda value: f"Convert token {value.label!r} to a string.",
        )
        issue = jsonwhy.explain(Token("abc"))[0]
        self.assertIn("'abc'", issue.suggestion or "")

    def test_empty_callable_suggestion_falls_back(self) -> None:
        jsonwhy.register_suggestion(Token, lambda value: None)
        issue = jsonwhy.explain(Token())[0]
        self.assertIn("default=", issue.suggestion or "")

    def test_raising_callable_suggestion_falls_back(self) -> None:
        def broken_suggestion(value: object) -> str:
            raise RuntimeError("suggestion failed")

        jsonwhy.register_suggestion(Token, broken_suggestion)
        issue = jsonwhy.explain(Token())[0]
        self.assertIn("default=", issue.suggestion or "")

        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(Token())
        self.assertIsInstance(caught.exception.original, TypeError)

    def test_suggestion_does_not_swallow_base_exceptions(self) -> None:
        def interrupted_suggestion(value: object) -> str:
            raise KeyboardInterrupt

        jsonwhy.register_suggestion(Token, interrupted_suggestion)
        with self.assertRaises(KeyboardInterrupt):
            jsonwhy.explain(Token())

    def test_registration_applies_to_subclasses(self) -> None:
        jsonwhy.register_suggestion(Token, "Token fix")
        self.assertEqual(jsonwhy.explain(SpecialToken())[0].suggestion, "Token fix")

    def test_unregister_returns_status(self) -> None:
        self.assertFalse(jsonwhy.unregister_suggestion(Token))
        jsonwhy.register_suggestion(Token, "fix")
        self.assertTrue(jsonwhy.unregister_suggestion(Token))
        self.assertFalse(jsonwhy.unregister_suggestion(Token))

    def test_invalid_registration(self) -> None:
        invalid_type: Any = "Token"
        invalid_suggestion: Any = 42
        with self.assertRaises(TypeError):
            jsonwhy.register_suggestion(invalid_type, "fix")
        with self.assertRaises(TypeError):
            jsonwhy.register_suggestion(Token, invalid_suggestion)

    def test_standard_library_suggestions(self) -> None:
        class Color(enum.Enum):
            RED = "red"

        values_and_fragments = [
            (dt.time(12, 30), "isoformat"),
            (uuid.UUID(int=0), "str(value)"),
            (Path("file.txt"), "str(value)"),
            (Color.RED, "value.value"),
            (frozenset({1}), "list"),
            (b"data", "base64"),
            (2 + 3j, "'real'"),
        ]
        for value, fragment in values_and_fragments:
            with self.subTest(value=value):
                issue = jsonwhy.explain(value)[0]
                self.assertIn(fragment, issue.suggestion or "")

    def test_optional_ecosystem_suggestions_without_dependencies(self) -> None:
        numpy_array_type = type("ndarray", (), {"__module__": "numpy"})
        numpy_scalar_type = type("int64", (), {"__module__": "numpy"})
        dataframe_type = type("DataFrame", (), {"__module__": "pandas.core"})
        timestamp_type = type("Timestamp", (), {"__module__": "pandas"})
        pandas_other_type = type("Categorical", (), {"__module__": "pandas"})

        values_and_fragments = [
            (numpy_array_type(), "tolist"),
            (numpy_scalar_type(), "item"),
            (dataframe_type(), "to_dict"),
            (timestamp_type(), "isoformat"),
            (pandas_other_type(), "default="),
        ]
        for value, fragment in values_and_fragments:
            with self.subTest(value=type(value).__name__):
                issue = jsonwhy.explain(value)[0]
                self.assertIn(fragment, issue.suggestion or "")


class Token:
    def __init__(self, label: str = "token") -> None:
        self.label = label


class SpecialToken(Token):
    pass


if __name__ == "__main__":
    unittest.main()
