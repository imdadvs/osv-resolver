# repro — proving a fix is real by running its own test

`osv-resolver` finds the commit that fixed an advisory. This folder answers the
next question: **was the bug real, and did that commit actually fix it?**

The method needs no AI and no exploit. A security fix usually ships with a test.
Run that test two ways:

- on the **fixed** commit — it should pass,
- on the **parent** commit with the fix's test files laid on top — it should fail.

Fail-before, pass-after means the bug was real and this commit is the fix. A
crash, a failed assertion, or a timeout all count as "fail". Nothing is sent to
any live system; the test calls the library in a throwaway container.

## What was run

Every critical/high Go advisory in OSV that has a GitHub fix — **1,525** of them
(out of 5,074 unique Go advisories). One rented 16-core server, about a day,
roughly $9. Each advisory is cloned, built with the Go version that was current
on the fix date, and tested twice.

## Result

| Outcome | Count |
|---|---|
| **Proven** (fail-before, pass-after) | **364** |
| Fix shipped no test | 630 |
| Not proven, had a test (see `results/failure_reasons.json`) | 510 |
| No fix commit found / other | 21 |

Of the 871 advisories whose fix shipped a test, 364 (42%) are proven. A hand
check of 30 proven cases (`handcheck-30.md`) found ~93% are about the right bug;
the rest are a single commit fixing several advisories, credited to all of them.

For comparison, the largest hand-built sets are Vul4J (79, Java) and Vul4Py
(100, Python). This is automatic and across a whole ecosystem.

## The 510 "had a test but not proven" cases

`results/failure_reasons.json` gives each one a named reason with the log line
that shows it. Grouped by what it would take to fix:

| Group | Count | What it needs |
|---|---|---|
| A — test calls code the fix added | 245 | partial revert (see `PILE-A-SPEC.md`) |
| B — our harness can do better | 69 | small build-setup rules |
| C — needs real infrastructure | 71 | a database, C library, cluster, etc. |
| D — passes on old code / weak test | 78 | try the other fix commits; run 3× |
| E — unclassified | 47 | read case by case |

## Files

- `tools/gorepro.py` — reproduce one advisory (clone, pick Go version, run twice).
- `tools/gochain.py` — osv-resolver → gorepro for a list of advisories.
- `tools/gosev.py` — list unique Go advisories by severity.
- `tools/run.sh` — six parallel workers.
- `results/go-critical-high.jsonl` — one line per advisory with the verdict.
- `results/failure_reasons.json` — the 510 not-proven cases, each with a reason.
- `results/go-critical-high-logs.tgz` — every test run's output (the evidence).
- `handcheck-30.md` — manual check of 30 proven cases.

## Honest limits

- No-test cases (630) cannot be proven this way; they need a generated test.
- "Not proven" never means "safe" — it means not shown here, for the stated reason.
- A proof shows the bug exists in the library, not that it is reachable in your
  app. That is a separate question (see `govulncheck`).
