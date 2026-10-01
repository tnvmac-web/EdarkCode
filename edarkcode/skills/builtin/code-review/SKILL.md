---
name: code-review
description: Use when reviewing a diff or before committing. Check correctness, security, and tests.
tags: [review, quality]
---

# Code review

Review the change, not the author. Be specific and cite file:line.

## Order of checks
1. **Does it do what it claims?** Read the diff against the stated intent.
2. **Is it correct?** Edge cases: empty input, one item, many items, unicode,
   negative numbers, concurrent access, network failure.
3. **Is it safe?** Injection, path traversal, secrets in code or logs,
   unvalidated input, shell interpolation, unsafe deserialisation.
4. **Is it tested?** The new behaviour needs a test that fails without the change.
5. **Is it readable?** Names say what things are; no dead code; comments explain
   *why*, not *what*.

## Things that are real problems
- A claim in a docstring/comment that the code does not actually do.
- Error handling that swallows failures silently.
- Off-by-one and inclusive/exclusive boundary mistakes.
- Mutable default arguments in Python.
- Resource leaks: files, sockets, subprocesses not closed on the error path.

## Things that are not problems
- Style the linter already enforces (do not nitpick it by hand).
- Preferences with no functional consequence. Say "optional" if you raise them.

## How to report
- Blocking: will break or is unsafe. State the concrete failure.
- Non-blocking: improvement. Prefix with "nit:".
- If you cannot tell whether something is a bug, say what you would need to check.
