# Evidence map and audit status

This maps the **local, uncommitted** evidence for the draft “Advisories assert. Tests demonstrate.” Paths are relative to this repro directory unless noted. This audit was performed on 2026-10-16 against the files in this working tree; it did not rerun the Docker experiment. The map is not a publication certificate.

## Read this before citing the headline

The strongest aggregate run-state subset is **338 direct cases with archived old=fail and fixed=pass logs**. This verifies those two run states, not that the failing test matched the advisory. The merged **results/go-critical-high.jsonl** has 1,525 unique advisory rows and the pipeline marks **477** reproduced: 364 direct, 108 partial_revert, and 5 rung5_other_commit. **477 is a pipeline verdict count, not 477 independently verified fail-before/pass-after proofs.** All 477 need advisory attribution; the other 139 do not have the archived direct aggregate transition, and one has no supporting attempt or patch.

| Method | Rows | Evidence present here | Audit qualification |
| --- | ---: | --- | --- |
| Direct (missing method also means direct) | 364 | Original old/fixed logs and row metadata | 338 rows have aggregate old=fail, fixed=pass; 26 have other aggregate states. The direct classifier can accept a package-level transition without establishing that the changed test failed. Test attribution and environment failures need review. |
| Partial revert | 108 | Original old/fixed logs; 107 winning patches and attempts.jsonl records with recorded candidate-fail/fixed-pass confirmations | The original old run generally failed to build. The 107 records reference candidate and confirmation logs, but those raw logs are absent from both archives. **GO-2026-4924** has no attempt record or patch and is unverified. |
| Retry/search (rung5_other_commit) | 5 | results/rung5.jsonl and archived logs | Three winners used a different candidate; two succeeded on the original candidate under a later attempt. The merged rows retain stale original-run metadata. Three winning references are PR-number forms rather than immutable SHAs. Resolve each exact winner and replay before treating these as direct-equivalent evidence. |

The repository's committed HEAD, **b71c0ba** (documentation and figure update), still contains the earlier **364** direct-method flags in its committed result. The additional 113 verdicts, merged manifest, evidence map, server dump, and rung-5 driver are local working-tree changes or untracked files. A link to main does **not** substantiate the 477 figure.

Snapshot SHA-256 values for the audited local artifacts:

~~~text
011fd6cbc192b3a8f84ffcf915b420bc256b5cc056538fb040bafcb4548d40f9  results/go-critical-high.jsonl
b889e35364deefdff9482784d2997c3db04a51d589e5901ab4b58a93a76cd4d6  results/go-critical-high-logs.tgz
bd7bc93c4d8d5eeb75a95ef6e80c65444cf6ecf786d6febc40b975338bbd79f8  server-dump/hetzner-full.tgz
2cabe7be6f9ba6a16f713615fc3d2c87722cc9f01b7427c0c931c467b1ba0881  results/rung5.jsonl
1be007435a6092bdcadef8612cd13ec32798fa2f305f5b2a2d278a4ea6c30741  figs/fig2_funnel.png
ea32bed0613d467e317dbf8fc62b41dd2314b6c1d65ef59775a4f6fd48929344  figs/measured-flow.png
~~~

## Dataset and how to recalculate it

- **results/go_vulns.json** — retained cohort index with 5,074 alias-grouped Go advisory records. `tools/gosev.py` excludes withdrawn and `MAL-` records, groups IDs using aliases and upstream links, takes a severity label from `database_specific.severity`, and marks a GitHub fix reference when a group has a GitHub commit/PR URL or GitHub GIT range. Filtering this index to `severity in {HIGH, CRITICAL}` and `github_fix == true` yields 1,525 groups (347 critical, 1,178 high). The original raw OSV JSON snapshot, acquisition command, and snapshot date are not retained here; current live OSV data may produce different counts.
- **results/go-critical-high.jsonl** — merged 1,525-row result, one row per advisory. Inspect id, severity, verdict, method, repo, fix_commit, fix_sha, before, tests, pkgs, go_image, old, fixed, old_failed, and method-specific fields. Method is absent for direct rows.
- **server-dump/hetzner-full.tgz → results/go-critical-high.jsonl** — server baseline. It has the same 1,525 IDs, but 108 rows that were inconclusive_build there were later changed to partial_revert/reproduced in the local merged result. The exact merge command and revision have not been recorded here.
- **results/failure_reasons.json** — 510 *historical first-pass* failure-reason entries, not 510 final unresolved cases. Of these, 394 remain unresolved in the merged test-path result; 113 were later recovered and 3 are script errors.

From the repro directory:

~~~sh
python3 - <<'PY'
import collections, json
rows = [json.loads(line) for line in open('results/go-critical-high.jsonl')]
rep = [row for row in rows if row['verdict'] == 'reproduced']
print('rows, unique IDs:', len(rows), len({row['id'] for row in rows}))
print('verdicts:', collections.Counter(row['verdict'] for row in rows))
print('reproduced methods:', collections.Counter(row.get('method', 'direct') for row in rep))
print('distinct selected fix_commit fields:', len({row['fix_commit'] for row in rep}))
print('repositories, case-normalized:', len({row['repo'].lower() for row in rep}))
PY
~~~

The case-normalized repository count is 241; there are 242 distinct literal URL strings because 0xJacky/nginx-ui and 0xjacky/nginx-ui refer to the same GitHub repository. The 450 figure counts distinct *selected* fix_commit fields in the 477 rows; it is not a count of validated winning commit SHAs. Excluding GO-2026-4924 gives 476 flagged rows with some method-specific artifact and 449 distinct selected fix_commit fields. That still does not validate all 476.

Funnel: 630 no_test_in_fix; 24 other exclusions (20 no resolvable GitHub fix, 3 script errors, 1 first commit); 871 rows routed to the test path, of which 477 are flagged reproduced and 394 remain unresolved. Only 807 of the 871 have extracted names in tests, so describe the 871 as **test-path classifications**, not named-test matches. Severity labels among the 477: 96/347 critical and 381/1,178 high.

## Archived run output and method-specific evidence

- **results/go-critical-high-logs.tgz** — 1,744 original logs/<id>.old.log / .fixed.log members (872 pairs). There is one extra pair, GHSA-9423-6c93-gpp8, outside the final 1,525-row manifest. These logs are byte-identical to corresponding logs in the full server archive. They are useful for inspecting direct cases and original runs, **not raw proof of every partial-revert or retry/search verdict**.
- **server-dump/hetzner-full.tgz** — 2,304 archive members, of which 2,094 are regular files. It contains the baseline manifest, original logs, partial-revert checkpoints, and 107 winning patch files. It does **not** contain the candidate or confirmation log files referenced by those 107 partial-revert checkpoints (214 referenced confirmation paths are absent).
- **server-dump/unpacked/pa-*/pile-a/<id>/attempts.jsonl** — machine-readable attempt summaries. For 107 of the 108 winning partial-revert rows, these record a proving failure and confirmation candidate=fail, fixed=pass, with a nearby winning .patch. They are evidence summaries, not the missing raw test output. GO-2026-4924 has no checkpoint/patch; its original old log is a build failure and its fixed log runs no selected tests.
- **results/rung5.jsonl** — retry/search trial summaries and winning_commit for five marked successes: three different candidates and two later attempts on the original candidate. Resolve PR references to immutable SHAs and retain each winning run's full metadata and logs before claiming those rows are replayable.

For a strong *direct* illustration, inspect old/fixed log pairs and manifest rows for GO-2026-6207 (Traefik), GO-2026-6142 (logging-operator), and GO-2026-6494 (RabbitMQ amqp091-go). In each, a named regression test fails on the parent and passes on the fix. These examples do not validate the aggregate or deployment reachability.

## Code and manual review

- **tools/gorepro.py** — single-case Go harness. Run python3 -I tools/gorepro.py --help for usage. It clones a repository, carries changed test files to the parent, and runs tests in Docker. --pile-a searches partial code reversions. Direct verdict logic at lines 610–619 currently allows a package-level failure if any touched test name was found in the diff; it does not require the failed test to match that name. Its Docker command permits network access for dependency fetching.
- **tools/partial_revert.py**, **tools/run_pile_a.py**, **tools/pile_a_eval.py**, **tools/gochain.py**, **tools/rung5.py**, **tools/gosev.py**, **tools/run.sh** — supporting drivers. The last stage has no complete immutable winner record in the merged manifest.
- **README.md**, **STRATEGY.md**, **PILE-A-SPEC.md**, **NEGATIVE-CONTROL-PROTOCOL.md** — method and protocol documents. The root README's resolver invocation points to the Go `main.go` entry point. The negative-control protocol is committed; the control experiment has not been run.
- **handcheck-30.md** — 30 manually reviewed *direct-method* rows: 27 clear advisory/test matches, 1 partial match, 2 wrong-advisory attributions from shared commits. This is 90% clear matches (93% if the partial is included). It is not a representative validation of the 113 alternate-method rows. The file calls the selection random, but does not record a seed or sampling script.
- **../tests/fix_truth.json** (54) and **../tests/fix_holdout.json** (50) — cross-ecosystem commit-picker label sets. They are separate from this Go study; do not use them to support a Go-specific wrong-commit rate.
- **figs/measured-flow.png** — current Substack funnel diagram. It shows the 1,525 → 871/630/24 → 477/394 → 338/139 count splits, labels the 477 flags provisional, and distinguishes aggregate raw-log transitions from advisory-level proof. **figs/make_measured_flow.py** generates that PNG. **figs/method-flow-evidence-tiers.png** is the current direct-method diagram; **figs/make_method_flow.py** generates it. The earlier **figs/fig2_funnel.png** and **figs/make_funnel_pil.py** remain as superseded local artifacts; **figs/make_figs.py** has equivalent audited Figure 2 labels for future Matplotlib runs.

## Publication and validation status

The matched negative control, fresh 40-case unique-commit hand-check, and clean-machine 30-case replay have **not** run. No VALIDATION-PLAN.md with the proposed n=40, seed=20261015 exists in this checkout; do not say that plan was committed or frozen in a file. The existing 30-case review does not replace it. A local go build and go test ./... passed; Python pytest was unavailable and no Docker reproduction was rerun in this audit.

The claimed **US$11.39** compute charge was written in the earlier evidence map but no invoice, billing export, or rate/time calculation is present here. Older drafts state roughly US$9. Omit a precise cost from the article until source billing evidence is retained and checked.

Before publishing a 477-case claim as verified: resolve GO-2026-4924; recover or rerun and archive partial-revert confirmation logs; record immutable winning SHAs and full retry/search run data; audit all 364 direct flags at package, test, and advisory level, including the 26 without aggregate fail/pass states; publish a frozen, versioned manifest/method revision with an honest outcome funnel; then run the controls, unique-commit hand-check, and independent replay. A passing library-level regression test does not establish application reachability, exploitability, or a patch-priority change.
