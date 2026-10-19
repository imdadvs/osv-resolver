# repro — collecting test signals from candidate Go fixes

`osv-resolver` attempts to select a **candidate** fix commit from an advisory's references.
This folder asks whether changed maintainer tests behave differently on that
commit and its parent. The direct path runs tests on the candidate commit, then
on its parent with the changed test files carried over.

An aggregate fail-before/pass-after run is a **lead**, not proof that the named
security test failed or that the advisory's specific bug was reproduced. A
confirmed advisory-level result requires the same named test to execute, fail
for the expected reason before the fix, pass after it, and match the advisory.
None of these tests establishes deployed reachability or exploitability.

## What was run

The study selected **1,525** alias-deduplicated Go advisory groups labelled high
or critical and containing a GitHub commit or pull-request reference, or a
GitHub Git range. Those links are candidate fix references, not confirmed fixes.
This selected cohort is not all Go vulnerabilities, and the counts below are
not a reproduction rate or an estimate of method sensitivity. The OSV snapshot
and full merge provenance still need to be frozen for independent audit.

## Result

| Observed workflow outcome | Advisory rows |
|---|---:|
| No changed Go test detected in the selected candidate change | 630 |
| Excluded before the test path | 24 |
| Entered the test path | 871 |
| Direct-method pipeline flags within the test path | 364 |
| Archived direct-method aggregate old-fail/fixed-pass transitions | 338 |

The 338 are **run-level transitions**, not 338 confirmed advisory-specific
reproductions. They include 11 rows whose fix-selection status is `indirect` and
span 327 distinct selected fix-commit references. Fourteen have no extracted
test name; a different 14 have no recorded failed-test identifier. The other
26 direct-method flags require run-state review.

Later local analysis added 108 synthetic partial-reversal flags and five
retry/search flags, giving **477 provisional pipeline flags** across the 871
test-path rows; 394 remain unresolved. The 113 later flags, merged manifest,
and full evidence bundle are not released here. Of the 108 partial-reversal
flags, 107 retain a patch and checkpoint summaries but not raw confirmation
logs; one has neither patch nor checkpoint. Of the five retry/search flags,
three used a different candidate and two succeeded on the original candidate
under a later attempt. Their merged rows retain stale original-run metadata;
three winning references are PR-number forms. Resolve immutable winner SHAs
and retain full run records. Keep these methods separate from
the direct aggregate-log tier.

An earlier hand review of 30 direct-method flags found 27 clear advisory/test
matches, one partial match, and two wrong-advisory attributions from shared
commits. Its sampling frame and seed were not recorded, so it is qualitative
evidence rather than a cohort-wide accuracy estimate. Matched controls, a fresh
unique-commit hand-check, and clean-machine replay have not yet run.

## Files

- `tools/gorepro.py` — attempt one test comparison (clone, pick Go version, run the two sides).
- `tools/pile_a_eval.py` — attribute structured Go test failures to the selected test.
- `tools/partial_revert.py` — extract and reverse selected non-test hunks (used by `--pile-a`).
- `tools/gochain.py` — osv-resolver → gorepro for a list of advisories.
- `tools/gosev.py` — list unique Go advisories by severity.
- `examples/` — before/after test logs for the cases in the write-up, one
  `.old.log`/`.fixed.log` pair per advisory, each log headed by the exact
  command that produced it. See `examples/README.md`. The full-ecosystem
  result set is not published in this repo.

## Pile A: tests that need the new API

When the fix's own test needs an API the old code lacks, the direct
comparison can't build. The optional `--pile-a` mode handles that: it starts at
the passing fixed commit, keeps its tests and testdata, and reverses code hunks
(singles, pairs, then all) until the developer test fails the same way twice and
the fixed checkout passes again. Results record `method: partial_revert`.

```bash
python3 -I repro/tools/gorepro.py /tmp/pile-a ADVISORY_ID REPO_URL FIX_SHA \
  --pile-a --max-attempts 25
```

## Limits and runner safety

- No detected changed test in the selected commit is not evidence of safety;
  existing, integration, separate-repository, or otherwise undetected tests
  may still exist.
- Package-level failure, build failure, timeout, or panic alone does not
  establish the advisory-specific bug or the effective fix.
- A confirmed library test still does not establish that a deployed application
  contains the affected code, accepts attacker-controlled input, or is
  exploitable. Review the actual deployed artifact and configuration.
- The harness clones and executes historical third-party tests. Docker is not
  a complete trust boundary; the current command allows network access for
  dependency downloads. Use a throwaway worker with no credentials and
  controlled egress. The original run does not report per-case cost or runtime.
