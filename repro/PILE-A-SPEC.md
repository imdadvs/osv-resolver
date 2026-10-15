# Pile A — reproducing fixes whose test needs the new code (design spec)

**Status: specification only, not yet implemented.**

## The problem

245 advisories fail with a compile error like `undefined: sanitizePath`. The
reason: the fix added a new symbol (function, field, argument) *and* a test that
uses it, in the same commit. The default method (parent code + fix's test) can't
compile, because on the parent that symbol does not exist.

## The method: partial revert

Approach from the fixed side, which always compiles, and undo only the fix.

1. Check out the **fixed** commit. Confirm the fix's test **passes**. (If it
   doesn't, this is not a pile-A case — fall back to the normal diagnosis.)
2. Split the fix's diff into hunks. Separate them into:
   - **test hunks** — changes to `_test.go` files and `testdata`. Keep these.
   - **code hunks** — everything else (the actual fix).
3. For the code hunks, revert them in increasing scope, re-running the test
   after each attempt, and stop at the first attempt where the test **fails**
   for a real reason (assertion/panic/timeout), not a compile error:
   a. Revert **one code hunk** at a time, newest-looking security hunk first
      (heuristic: hunks touching the files the test imports, smallest first).
   b. If no single hunk does it, revert **pairs**, then the **whole set of code
      hunks at once** as the last attempt.
4. A revert that still **compiles** (the added symbols are kept because they live
   in the test hunks or in kept code) and makes the test **fail** is the proof.
   Record the hunk(s) reverted — those lines are the actual fix.

## Why it stays honest

- The test is the developer's own; we never write the assertion.
- The verdict is still fail-before (reverted) / pass-after (fixed), decided by
  running the code, not by judgement.
- If reverting the code hunks will not compile (the symbol the test needs lives
  in a code hunk that must be reverted), this case is **not** mechanically
  reproducible — mark it `needs_test_adaptation` and route it to the
  LLM-assisted step, where the LLM adapts the test to the old API and the same
  fail/pass check still decides.

## Expected yield

Partial revert should reach the subset where the fix *adds a check inside a path
the test already reaches*. Where the fix *refactored* the code, the test cannot
map back and the case goes to `needs_test_adaptation`. Split unknown until run;
estimate half of the 245.

## Inputs available per case

From `results/go-critical-high.jsonl`: `fix_commit`, `fix_sha`, `before`,
`tests`, `pkgs`, `go_image`. The harness in `tools/gorepro.py` already clones,
picks the Go version, and runs tests per module — the revert loop slots in
between steps 3 (fixed run) and 4 (old run) there.
