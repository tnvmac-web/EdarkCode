---
name: systematic-debugging
description: Use when something is broken or a test fails. Find the root cause before changing code.
tags: [debugging, testing]
---

# Systematic debugging

Do not guess. Do not "try things until it works". Find the cause.

## 1. Reproduce it first
Before anything else, get the failure to happen on demand:
- Run the exact failing command and capture the full output and exit code.
- If it is intermittent, note what makes it happen.
- If you cannot reproduce it, you cannot verify a fix. Say so.

## 2. Read the error properly
- Read the whole traceback, bottom-up. The last frame in *your* code is usually
  the interesting one.
- Distinguish the root error from errors it caused. A `ConnectionError` inside a
  `TimeoutError` means fix the connection, not the timeout.

## 3. Narrow it down
- Find the smallest input that still fails.
- Add temporary instrumentation (print/log) around the boundary between working
  and broken code. Remove it afterwards.
- Check your assumptions explicitly: print the actual value, do not assume it.

## 4. Form one hypothesis, test it
State the hypothesis in one sentence: "X fails because Y". Then design the
cheapest check that would prove it wrong. If it survives, you are closer.

## 5. Fix the cause, not the symptom
- Do not wrap the failure in a `try/except` to hide it.
- Do not add a retry to paper over a deterministic bug.

## 6. Verify
- Re-run the original reproduction. It must pass.
- Run the full test suite to prove you did not break anything else.
- Add a regression test that fails without your fix.

## Anti-patterns
- Changing several things at once, then not knowing which fixed it.
- Assuming a library behaves the way you remember instead of reading its code or docs.
- Declaring victory without re-running the original failing case.
