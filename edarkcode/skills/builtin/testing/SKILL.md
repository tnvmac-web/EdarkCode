---
name: testing
description: Use when writing or running tests. Discover the project's test setup before adding anything.
tags: [testing, quality]
---

# Testing

## First, find out how this project tests
Never invent a test command. Look:
- `pyproject.toml` / `setup.cfg` / `pytest.ini` / `tox.ini` for configuration
- `package.json` scripts, `Makefile`, `.github/workflows/*` for the real command
- The existing `tests/` layout and naming conventions

Then run the existing suite once, so you know the baseline before you change it.

## Writing a good test
- One behaviour per test. The name should state the behaviour:
  `test_rejects_path_that_escapes_workspace`.
- Arrange / act / assert, visibly separated.
- Assert on the specific thing that matters, not just "no exception".
- Cover the failure path, not only the happy path.
- Do not mock the thing you are trying to test.

## Python specifics
- `pytest` fixtures for setup; `tmp_path` for filesystem work.
- `pytest.raises(ValueError, match="...")` to assert on error messages.
- Async tests need `pytest-asyncio` and `asyncio_mode = "auto"` (or a marker).

## Verifying a fix
A fix is only proven by a test that **fails before** the fix and **passes after**.
If you cannot demonstrate that, say the fix is unverified.

## Report honestly
State the exact command you ran and its real result. "Tests pass" is only
acceptable if you ran them and saw them pass. Otherwise say you did not run them.
