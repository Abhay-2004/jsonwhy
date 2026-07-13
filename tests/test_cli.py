from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from jsonwhy.__main__ import main


class CliTests(unittest.TestCase):
    def test_valid_literal(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["{'ok': [1, 2]}"])
        self.assertEqual(result, 0)
        self.assertIn("No JSON serialization issues", output.getvalue())

    def test_invalid_value_and_json_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--json", "{'tags': {1, 2}}"])
        self.assertEqual(result, 1)
        issues = json.loads(output.getvalue())
        self.assertEqual(issues[0]["path"], "$.tags")
        self.assertEqual(issues[0]["json_pointer"], "/tags")

    def test_pointer_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--path-style", "pointer", "{'a/b': {1, 2}}"])
        self.assertEqual(result, 1)
        self.assertIn("/a~1b:", output.getvalue())

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--path-style", "pointer", "{1, 2}"])
        self.assertEqual(result, 1)
        self.assertIn("<root>:", output.getvalue())

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--path-style", "pointer", "{('bad',): 1}"])
        self.assertEqual(result, 1)
        self.assertIn("<no JSON Pointer>:", output.getvalue())

    def test_cli_diagnostic_limits(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--max-issues", "1", "[{1}, {2}]"])
        self.assertEqual(result, 1)
        self.assertIn("$[0]", output.getvalue())
        self.assertNotIn("$[1]", output.getvalue())

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--max-depth", "0", "[[1]]"])
        self.assertEqual(result, 1)
        self.assertIn("max_depth=0", output.getvalue())

    def test_invalid_cli_diagnostic_limits(self) -> None:
        for option, value in (("--max-issues", "0"), ("--max-depth", "-1")):
            with self.subTest(option=option):
                errors = io.StringIO()
                with redirect_stderr(errors), self.assertRaises(SystemExit) as caught:
                    main([option, value, "{}"])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("error:", errors.getvalue())

    def test_strict_flag_is_accepted(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--strict", "{'ok': 1.0}"])
        self.assertEqual(result, 0)

    def test_reads_standard_input(self) -> None:
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO("{'payload': b'bytes'}")):
            with redirect_stdout(output):
                result = main([])
        self.assertEqual(result, 1)
        self.assertIn("$.payload", output.getvalue())

    def test_empty_and_invalid_input(self) -> None:
        errors = io.StringIO()
        with patch("sys.stdin", io.StringIO("")):
            with redirect_stderr(errors):
                self.assertEqual(main([]), 2)
        self.assertIn("provide a Python literal", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors):
            self.assertEqual(main(["not valid("]), 2)
        self.assertIn("invalid Python literal", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
