# jsonwhy

Python's JSON encoder tells you which type failed, but not where that value is
inside a large payload. `jsonwhy` adds the missing path and reports other
problems it finds in the same pass.

```python
from datetime import datetime

import jsonwhy

payload = {
    "users": [{"name": "Ada", "joined": datetime(2026, 7, 12)}],
    "tags": {"python", "json"},
}

jsonwhy.dumps(payload)
```

```text
jsonwhy.JsonWhyError: JSON serialization failed with 2 issues:
1. $.users[0].joined: Object of type datetime is not JSON serializable.
   Fix: Convert it with value.isoformat(); preserve timezone information.
2. $.tags: Object of type set is not JSON serializable.
   Fix: Convert it to a list; sort first if deterministic output matters.
```

## Install

```bash
python -m pip install jsonwhy
```

Python 3.10 or newer is required. The package has no runtime dependencies.

## API

`dumps()` and `dump()` accept the standard `json` options. Valid input is passed
through to the standard library; diagnosis only runs after serialization fails.

```python
encoded = jsonwhy.dumps({"ok": True}, indent=2)

with open("data.json", "w", encoding="utf-8") as output:
    jsonwhy.dump({"ok": True}, output)
```

Use `explain()` when you want structured results without raising an exception:

```python
issues = jsonwhy.explain(payload)

for issue in issues:
    print(issue.path)
    print(issue.kind)
    print(issue.suggestion)
    print(issue.as_dict())
```

Two shorter checks are also available:

```python
jsonwhy.check(payload)                 # bool
jsonwhy.assert_serializable(payload)   # raises JsonWhyError
```

`jsonwhy` detects unsupported values and keys, circular references, non-finite
floats when `allow_nan=False`, failures in custom default handlers, and overly
deep structures.

## Custom suggestions

Applications can register advice for their own types:

```python
class CustomerId:
    pass


jsonwhy.register_suggestion(CustomerId, "Convert it with str(value).")
```

This changes the suggested fix only. `jsonwhy` does not silently convert the
value.

## Command line

The CLI checks Python literals, which is useful for values such as sets, bytes,
complex numbers, and tuple keys.

```bash
jsonwhy "{'payload': b'hello', 'tags': {'a', 'b'}}"
jsonwhy --json "{'payload': b'hello'}"
```

Exit status `0` means compatible, `1` means issues were found, and `2` means the
input or command was invalid.

## Notes

- A failing `dump()` may have written part of its output before the error.
- Diagnosis may call a custom `default` handler or construct a custom encoder
  again after the original failure. These hooks should be safe to repeat.
- Diagnostic text can contain representations of application values. Treat it
  with the same care as logs and tracebacks.
- Custom `repr()` implementations can perform work or have side effects before
  their resulting text is shortened.

Bug reports are welcome on the
[GitHub issue tracker](https://github.com/Abhay-2004/jsonwhy/issues).

## License

MIT
