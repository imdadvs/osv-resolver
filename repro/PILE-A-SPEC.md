# Pile A — reproducing fixes whose test needs the new code (design spec)

**Status: implemented by `tools/gorepro.py --pile-a` and `tools/run_pile_a.py`.**

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

## Running it

From the repository root, run a selected saved case:

```bash
python3 -I repro/tools/run_pile_a.py /tmp/pile-a repro/results/pile-a.jsonl \
  --id GO-2026-6372 --case-budget 50
```

Omit `--id` to process every `symbol_from_fix_missing` case. The runner uses
the recorded Go image and verifies the saved fix/before SHA prefixes before
testing. The 245 labeled cases include 22 whose recorded fixed baseline did
not pass; they must pass a fresh baseline or fall back to normal diagnosis.

Each invocation tries up to `--max-attempts` new candidates (default 25).
Checkpoints under `WORKDIR/pile-a/ID/attempts.jsonl` allow the same command to
resume. `--case-budget` limits candidate attempts during one batch run; it is
optional. A budget or unresolved execution error yields `search_incomplete`,
which is resumable and is not a negative result.

The search uses zero-context Git hunks so nearby changes remain separable.
New/deleted files, binary changes, and mode changes are atomic candidates.
Every attempt starts from a clean fixed checkout. A successful candidate is
run a second time, then the fixed checkout must pass again. The output keeps
`verdict: reproduced` and adds `method: partial_revert`, full commit IDs, hunk
metadata, logs, and a patch. The saved patch is the original fix subset;
apply it with `git apply --reverse` at the fixed commit to reconstruct the
candidate. Assertions and tests are preserved from the developer's commit.

Compile failures, external process timeouts, changed test commands, and
unattributed concurrent panics are not proofs. Where a suite has no touched
top-level `Test` function, the harness selects the package's developer test
entrypoints and records that fallback in the result.
