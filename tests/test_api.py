from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import math
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import jsonwhy
from jsonwhy import JsonIssue


class ApiTests(unittest.TestCase):
    def test_dumps_matches_stdlib_for_valid_data(self) -> None:
        value = {"message": "héllo", "items": [3, 1, None, True]}
        options = {"ensure_ascii": False, "sort_keys": True, "indent": 2}
        self.assertEqual(
            jsonwhy.dumps(value, **options),
            json.dumps(value, **options),
        )

    def test_dump_writes_to_file_object(self) -> None:
        stream = io.StringIO()
        jsonwhy.dump({"ok": True}, stream, sort_keys=True)
        self.assertEqual(stream.getvalue(), '{"ok": true}')

    def test_dump_failure_raises_diagnostic(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dump({"bad": object()}, stream)
        self.assertEqual(caught.exception.issues[0].path, "$.bad")

    def test_dump_accepts_diagnostic_controls(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dump(
                [object(), object()],
                stream,
                diagnostic_max_issues=1,
                diagnostic_include_value_repr=False,
            )
        self.assertEqual(len(caught.exception.issues), 1)
        self.assertEqual(caught.exception.issues[0].value_repr, "<redacted>")

    def test_explain_finds_multiple_nested_issues(self) -> None:
        value = {
            "users": [{"joined": dt.datetime(2026, 7, 12)}],
            "tags": {"python", "json"},
        }
        issues = jsonwhy.explain(value)
        self.assertEqual(
            [issue.path for issue in issues], ["$.users[0].joined", "$.tags"]
        )
        self.assertEqual(
            [issue.kind for issue in issues],
            ["unsupported_type", "unsupported_type"],
        )
        self.assertIn("isoformat", issues[0].suggestion or "")
        self.assertIn("list", issues[1].suggestion or "")
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(value)
        self.assertIn("2 issues", str(caught.exception))

    def test_jsonwhy_error_contains_issues_and_original(self) -> None:
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps({"price": Decimal("1.20")})
        error = caught.exception
        self.assertIsInstance(error, TypeError)
        self.assertIsInstance(error.original, TypeError)
        self.assertEqual(error.issues[0].path, "$.price")
        self.assertIn("preserve precision", str(error))
        self.assertIn("Original error", str(error))

    def test_check_and_assert_serializable(self) -> None:
        self.assertTrue(jsonwhy.check({"valid": [1, 2, 3]}))
        self.assertFalse(jsonwhy.check({"path": Path("data.json")}))
        jsonwhy.assert_serializable({"valid": True})
        with self.assertRaises(jsonwhy.JsonWhyError):
            jsonwhy.assert_serializable({"invalid": object()})

    def test_non_identifier_key_path_is_unambiguous(self) -> None:
        issue = jsonwhy.explain({"user name": {"a.b": object()}})[0]
        self.assertEqual(issue.path, '$["user name"]["a.b"]')

    def test_json_pointer_escapes_nested_keys(self) -> None:
        issue = jsonwhy.explain({"a/b": [{"~key": object()}]})[0]
        self.assertEqual(issue.json_pointer, "/a~1b/0/~0key")

    def test_root_json_pointer_is_empty(self) -> None:
        issue = jsonwhy.explain(object())[0]
        self.assertEqual(issue.path, "$")
        self.assertEqual(issue.json_pointer, "")

    def test_valid_non_string_keys_have_json_pointers(self) -> None:
        class LabeledInt(int):
            def __str__(self) -> str:
                return "label"

            def __repr__(self) -> str:
                return "labeled-int"

        class LabeledFloat(float):
            def __repr__(self) -> str:
                return "labeled-float"

        values_and_pointers = [
            ({None: object()}, "/null"),
            ({False: object()}, "/false"),
            ({2: object()}, "/2"),
            ({1.5: object()}, "/1.5"),
            ({math.nan: object()}, "/NaN"),
            ({math.inf: object()}, "/Infinity"),
            ({-math.inf: object()}, "/-Infinity"),
            ({LabeledInt(3): object()}, "/3"),
            ({LabeledFloat(2.5): object()}, "/2.5"),
        ]
        for value, pointer in values_and_pointers:
            with self.subTest(pointer=pointer):
                self.assertEqual(jsonwhy.explain(value)[0].json_pointer, pointer)

    def test_valid_non_string_key_paths(self) -> None:
        issues = jsonwhy.explain(
            {None: object(), False: object(), 2: object(), 1.5: object()}
        )
        self.assertEqual(
            [issue.path for issue in issues],
            ["$[null]", "$[false]", "$[2]", "$[1.5]"],
        )

    def test_unsupported_dictionary_key(self) -> None:
        key = ("region", 1)
        issue = jsonwhy.explain({key: "value"})[0]
        self.assertEqual(issue.kind, "unsupported_key")
        self.assertIn("<key", issue.path)
        self.assertIsNone(issue.json_pointer)

        issues = jsonwhy.explain({key: object()})
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(item.json_pointer is None for item in issues))

    def test_tuple_items_have_json_pointers(self) -> None:
        issue = jsonwhy.explain(("ok", object()))[0]
        self.assertEqual(issue.json_pointer, "/1")

    def test_skipkeys_matches_json_behavior(self) -> None:
        value = {("bad",): object(), "good": 1}
        self.assertEqual(jsonwhy.explain(value, skipkeys=True), ())
        self.assertEqual(jsonwhy.dumps(value, skipkeys=True), '{"good": 1}')

    def test_strict_non_finite_float(self) -> None:
        issues = jsonwhy.explain(
            {"nan": math.nan, math.inf: "key"},
            allow_nan=False,
        )
        self.assertEqual(
            [issue.kind for issue in issues],
            ["non_finite_float", "non_finite_float_key"],
        )
        with self.assertRaises(jsonwhy.JsonWhyError):
            jsonwhy.dumps({"nan": math.nan}, allow_nan=False)

    def test_cycle_is_reported_but_shared_reference_is_valid(self) -> None:
        cyclic: list[object] = []
        cyclic.append(cyclic)
        issue = jsonwhy.explain(cyclic)[0]
        self.assertEqual(issue.kind, "circular_reference")
        self.assertEqual(issue.path, "$[0]")
        with self.assertRaises(jsonwhy.JsonWhyError):
            jsonwhy.dumps(cyclic)

        shared = [1, 2]
        self.assertTrue(jsonwhy.check({"a": shared, "b": shared}))

    def test_default_handler_is_followed(self) -> None:
        value = {"when": dt.date(2026, 7, 12)}

        def default(item: dt.date) -> str:
            return item.isoformat()

        self.assertEqual(jsonwhy.explain(value, default=default), ())
        self.assertEqual(
            jsonwhy.dumps(value, default=default),
            '{"when": "2026-07-12"}',
        )

    def test_default_handler_failure_is_reported(self) -> None:
        def broken_default(value: object) -> object:
            raise RuntimeError("conversion exploded")

        issue = jsonwhy.explain({"value": object()}, default=broken_default)[0]
        self.assertEqual(issue.kind, "default_handler_failed")
        self.assertIn("conversion exploded", issue.message)

    def test_default_handler_returning_original_is_reported(self) -> None:
        value = object()
        issue = jsonwhy.explain(value, default=lambda item: item)[0]
        self.assertEqual(issue.kind, "default_handler_cycle")

    def test_default_handler_nested_cycle_is_reported(self) -> None:
        value = object()
        issue = jsonwhy.explain(value, default=lambda item: [item])[0]
        self.assertEqual(issue.kind, "circular_reference")

    def test_custom_encoder_is_respected_during_failure_diagnosis(self) -> None:
        class DateEncoder(json.JSONEncoder):
            def default(self, value: object) -> object:
                if isinstance(value, dt.date):
                    return value.isoformat()
                return super().default(value)

        value = {"date": dt.date(2026, 7, 12), "bad": {1, 2}}
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(value, cls=DateEncoder)
        self.assertEqual(len(caught.exception.issues), 1)
        self.assertEqual(caught.exception.issues[0].path, "$.bad")

    def test_encoder_construction_failure_gets_fallback_issue(self) -> None:
        class BrokenEncoder(json.JSONEncoder):
            def __init__(self, *args: object, **kwargs: object) -> None:
                raise TypeError("encoder setup failed")

        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps({"otherwise": "valid"}, cls=BrokenEncoder)
        issue = caught.exception.issues[0]
        self.assertEqual(issue.kind, "serialization_error")
        self.assertIn("encoder setup failed", issue.message)

    def test_encoder_default_property_failure_does_not_mask_original(self) -> None:
        class BrokenDefaultPropertyEncoder(json.JSONEncoder):
            @property
            def default(self) -> object:
                raise RuntimeError("default property failed")

            def encode(self, value: object) -> str:
                raise TypeError("encode failed")

        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(object(), cls=BrokenDefaultPropertyEncoder)
        self.assertIsInstance(caught.exception.original, TypeError)
        self.assertIn("encode failed", str(caught.exception))

    def test_diagnostic_failure_falls_back_to_original_error(self) -> None:
        with patch(
            "jsonwhy._api.explain", side_effect=RuntimeError("diagnosis failed")
        ):
            with self.assertRaises(jsonwhy.JsonWhyError) as caught:
                jsonwhy.dumps(object())
        self.assertEqual(caught.exception.issues[0].kind, "serialization_error")
        self.assertIsInstance(caught.exception.original, TypeError)

        with patch(
            "jsonwhy._api.explain", side_effect=RuntimeError("diagnosis failed")
        ):
            with self.assertRaises(jsonwhy.JsonWhyError) as redacted:
                jsonwhy.dumps(object(), diagnostic_include_value_repr=False)
        self.assertEqual(redacted.exception.issues[0].value_repr, "<redacted>")

    def test_overridden_container_iteration_does_not_mask_original(self) -> None:
        class HostileDict(dict[str, object]):
            calls = 0

            def items(self) -> object:
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("items failed")
                return super().items()

        class HostileList(list[object]):
            calls = 0

            def __iter__(self) -> object:
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("iteration failed")
                return super().__iter__()

        dict_value = HostileDict(bad=object())
        list_value = HostileList([object()])

        with self.assertRaises(jsonwhy.JsonWhyError) as dict_error:
            jsonwhy.dumps(dict_value)
        self.assertEqual(dict_error.exception.issues[0].path, "$.bad")

        with self.assertRaises(jsonwhy.JsonWhyError) as list_error:
            jsonwhy.dumps(list_value)
        self.assertEqual(list_error.exception.issues[0].path, "$[0]")

    def test_hostile_exception_message_does_not_mask_original(self) -> None:
        class HostileTypeError(TypeError):
            def __str__(self) -> str:
                raise RuntimeError("str failed")

        def broken_default(value: object) -> object:
            raise HostileTypeError

        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(object(), default=broken_default)
        self.assertIsInstance(caught.exception.original, HostileTypeError)
        self.assertIn("<exception message unavailable>", str(caught.exception))

    def test_max_issues_and_max_depth(self) -> None:
        issues = jsonwhy.explain([object(), object(), object()], max_issues=2)
        self.assertEqual(len(issues), 2)

        issue = jsonwhy.explain([[[1]]], max_depth=1)[0]
        self.assertEqual(issue.kind, "maximum_depth")
        self.assertEqual(issue.path, "$[0][0]")

    def test_dumps_accepts_diagnostic_controls(self) -> None:
        self.assertEqual(
            jsonwhy.dumps(
                {"ok": True},
                diagnostic_max_issues=1,
                diagnostic_max_depth=0,
                diagnostic_include_value_repr=False,
            ),
            '{"ok": true}',
        )
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(
                [object(), object()],
                diagnostic_max_issues=1,
                diagnostic_max_depth=10,
                diagnostic_include_value_repr=False,
            )
        self.assertEqual(len(caught.exception.issues), 1)
        self.assertEqual(caught.exception.issues[0].value_repr, "<redacted>")
        self.assertIn("<redacted>", str(caught.exception))

    def test_invalid_limits_raise(self) -> None:
        with self.assertRaises(ValueError):
            jsonwhy.explain({}, max_issues=0)
        with self.assertRaises(ValueError):
            jsonwhy.explain({}, max_depth=-1)
        with self.assertRaises(ValueError):
            jsonwhy.dumps({}, diagnostic_max_issues=0)
        with self.assertRaises(ValueError):
            jsonwhy.dump({}, io.StringIO(), diagnostic_max_depth=-1)

    def test_value_repr_can_be_redacted_without_calling_repr(self) -> None:
        class SensitiveValue:
            repr_calls = 0

            def __repr__(self) -> str:
                self.repr_calls += 1
                return "secret-token"

        value = SensitiveValue()
        issue = jsonwhy.explain(value, include_value_repr=False)[0]
        self.assertEqual(issue.value_repr, "<redacted>")
        self.assertEqual(value.repr_calls, 0)
        self.assertNotIn("secret-token", json.dumps(issue.as_dict()))

        issue = jsonwhy.explain({value: "item"}, include_value_repr=False)[0]
        self.assertEqual(issue.path, "$[<unsupported key>]")
        self.assertEqual(value.repr_calls, 0)

    def test_interpreter_recursion_limit_becomes_an_issue(self) -> None:
        value: list[object] = []
        cursor = value
        for _ in range(2000):
            child: list[object] = []
            cursor.append(child)
            cursor = child
        cursor.append(object())

        issues = jsonwhy.explain(value, max_depth=10_000)
        self.assertEqual(issues[-1].kind, "diagnostic_recursion_limit")
        with self.assertRaises(jsonwhy.JsonWhyError) as caught:
            jsonwhy.dumps(value)
        self.assertEqual(
            caught.exception.issues[-1].kind,
            "diagnostic_recursion_limit",
        )

    def test_dataclass_suggestion(self) -> None:
        @dataclasses.dataclass
        class User:
            name: str

        issue = jsonwhy.explain(User("Ada"))[0]
        self.assertIn("dataclasses.asdict", issue.suggestion or "")

    def test_issue_as_dict_is_json_serializable(self) -> None:
        issue = jsonwhy.explain({"bad": object()})[0]
        encoded = json.dumps(issue.as_dict())
        self.assertIn('"path": "$.bad"', encoded)
        self.assertIn('"json_pointer": "/bad"', encoded)

    def test_error_can_format_issue_without_suggestion(self) -> None:
        issue = JsonIssue(
            path="$",
            kind="example",
            value_type="object",
            message="Example problem.",
            suggestion=None,
            value_repr="<object>",
        )
        message = str(jsonwhy.JsonWhyError([issue]))
        self.assertNotIn("Fix:", message)

    def test_hostile_repr_is_safely_bounded(self) -> None:
        class Hostile:
            def __repr__(self) -> str:
                raise RuntimeError("no repr")

        issue = jsonwhy.explain(Hostile())[0]
        self.assertIn("Hostile instance", issue.value_repr)


if __name__ == "__main__":
    unittest.main()
