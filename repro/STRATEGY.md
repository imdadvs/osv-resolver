# The reproduction ladder — one method for every advisory

A single ordered sequence runs for every advisory. Each rung handles one class
of failure. Anything that falls through lands in a **named bucket**, never
"unknown". New failure types get a new rung or a new bucket — the shape does not
change. Rungs 1–5 use no LLM; rung 6 is the only one that does, and even then a
plain test run is the judge.

| Rung | When it runs | What it does | LLM? | Status |
|---|---|---|---|---|
| 1. Baseline | always | run the fix's own test on the parent (want fail) and the fix (want pass) | no | built |
| 2. Build-setup rescue | build failed | add `-tags`, drop old `-mod`, stub an unbuilt frontend, sqlite tags, widen `-run`, install the named C header, set the named env var; retry | no | partly built |
| 3. Provide infrastructure | test needs a service | start a database/sidecar beside the test; a cluster/Docker daemon → bucket `needs_cluster` | no | spec |
| 4. Partial revert | test won't compile on the parent (needs a symbol the fix added) | start from the fixed code, undo only the fix's own hunks, re-run; can't isolate → bucket `needs_test_adaptation` | no | built (`gorepro.py --pile-a`; PILE-A-SPEC.md) |
| 5. Try other commits | test passes on the parent too | the picked commit may be wrong — try the other candidate commits; run 3× to rule out a flaky test | no | spec |
| 6. Generate/adapt a test | no usable test exists | an LLM writes or adapts a test; the same fail-before/pass-after run decides | yes | later |
| 7. Verdict | end | `PROVEN(rung N)` or `NOT_PROVEN(reason)` — every advisory, no "unknown" | — | — |

## Principles

- **One entry point, one order.** The same ladder runs for the 1,525 today and
  for any advisory added tomorrow.
- **Deterministic first.** Rungs 1–5 are plain code. The LLM (rung 6) is the
  last resort, only for advisories whose fix shipped no usable test.
- **The run is always the judge.** Even in rung 6 the LLM only proposes a test;
  fail-before/pass-after decides. No model opinion is ever the verdict.
- **Every case is categorized.** Proven by a rung, or parked in a named bucket
  with the log line that put it there.

## Failure buckets (from the first full run, results/failure_reasons.json)

| Bucket | Count | Rung that targets it |
|---|---|---|
| test needs a symbol the fix added | 245 | 4 |
| our harness can do better | 69 | 2 |
| needs infrastructure | 71 | 3 |
| passes on old code / weak test | 78 | 5 |
| unclassified | 47 | read, then 2–5 or 6 |
| no test in the fix | 630 | 6 |

## No-LLM ceiling

Rungs 1–5 can reach, at best, the cases where a usable test exists and can be
run or mapped to the parent. That is the 871 "has a test" set minus the
refactored pile-A cases that only rung 6 can adapt. Everything past that — the
630 no-test cases especially — needs rung 6. State the no-LLM number and the
with-LLM number separately; do not blend them.
