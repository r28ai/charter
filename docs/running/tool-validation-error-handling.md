---
title: "Tool validation and error handling"
description: "Where input is validated, the three layers it passes through, and what each raises."
---

## Three input mistakes, fixed

LLMs make three classes of input mistake against a snake_case schema:

| Mistake                          | Example                              | Symptom without a fix                       |
|----------------------------------|--------------------------------------|---------------------------------------------|
| JSON string instead of object    | `"body": '{"requests":[]}'`          | `ValidationError`, then an ugly agent template |
| camelCase keys in nested objects | `"start": {"dateTime": "..."}`       | silently dropped, field stays `None`, 400 from the API |
| genuine wrong type / missing field | `"body": 12345`                    | `ValidationError`, then an ugly agent template |

## The problem: JSON string instead of object

```python
# The model sends:
{"body": '{"requests": [...]}'}   # string  <- wrong

# The tool expects:
{"body": {"requests": [...]}}     # dict    <- correct
```

## Where validation happens

```
your agent
  -> tool.ainvoke(args)
    -> validate_input(llm_schema, args)      <- ValidationError raised HERE
       -> ToolValidationError (formatted)
    -> executor.execute(validated_input)     <- only reached on success
```

The important consequence: anything that tries to coerce or reformat *inside*
the execution step is dead code for the validation case, because the error fires
before execution is entered.

## The three layers

### Layer 1 — alias acceptance

The contract answers to camelCase and PascalCase beside every snake_case field
name, and to the original name. Without that, a camelCase key is unknown:
it is dropped, the field stays `None`, serialization returns `{}`, and the API
400s with no local error to point at.

### Layer 2 — JSON-string coercion

Before any field is type-checked, `LLMBase` parses string values that are
obviously serialized JSON. The mistake is fixed silently; no error is ever
raised.

### Layer 3 — formatted errors

For genuine failures, `validate_input` raises
[`ToolValidationError`](/reference/errors#toolvalidationerror) whose message is
compact markdown naming each field path, the problem, and a truncated view of
what was actually sent.

**Before:**

```
Error invoking tool 'documents_update' with kwargs {...} with error:
body: Input should be a valid dictionary ... Please fix the error and try again.
```

**After:**

```
Validation error:
- **body**: Input should be a valid dictionary or instance of BatchUpdateRequestBody_LLM (got 12345)
```

## Catching it

Every error below derives from
[`CharterError`](/reference/errors#chartererror), so one `except` catches the
whole surface:

```python catching_errors.py
from charter import APIError, CredentialError, CharterError, ToolValidationError

try:
    result = await tool.ainvoke(args)
except ToolValidationError as e:
    feed_back_to_model(str(e))     # written to be read by an LLM
except CredentialError as e:
    refresh_and_retry(e.provider)  # your OAuth flow, your decision
except APIError as e:
    log(e.status_code, e.body)
except CharterError:
    ...                            # everything above derives from this
```

## In the LangChain adapter

`to_langchain` returns a `StructuredTool` with `handle_validation_error` wired to
the same formatter, and returns `ToolValidationError`/[`APIError`](/reference/errors#apierror) text as the tool
*result* rather than raising. Agent frameworks expect a readable result they can
feed back to the model, not an exception that ends the run.

## Related

- [Errors](/reference/errors) — `CharterError`, `DeclarationError`, `ToolValidationError`, `APIError`, `CredentialError`, `TransformError`
- [Catching the surface](/reference/errors#catching-the-surface) — which exception to catch where
- [`Tool.ainvoke`](/reference/tool#tool-ainvoke) — where validation runs, and what it raises
