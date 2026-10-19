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

## Reproduce one case

Install Git, Python 3, and Docker, then run from the repository root:

```bash
python3 -I repro/tools/gorepro.py /tmp/osv-repro \
  GO-2026-6142 https://github.com/kube-logging/logging-operator cf437d7f1e05
```

The harness clones the repo, runs the changed test on the fix commit and on its
parent, prints a JSON verdict, and writes both logs under the work directory.
Compare them against the saved pair in `examples/`.

A full run over every high/critical Go advisory is described in the write-up,
not here. Those aggregate results are not published in this repo; `examples/`
carries only the cases the write-up cites.

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
