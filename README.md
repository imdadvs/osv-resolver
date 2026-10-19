# osv-resolver

Selects a candidate code change for a vulnerability advisory.

A security advisory tells you a bug was fixed — rarely what the bug *was*.
`osv-resolver` takes an [OSV](https://osv.dev) record, selects a likely fixing
commit (following downstream → upstream references when needed), and emits an
enriched record you can diff. The output is itself a **valid OSV record**: every
field is standard, and the resolver's own data lives in `database_specific`,
OSV's sanctioned extension slot.

Commit selection is heuristic. Reading a referenced patch, even with
`fix_confidence: high`, does not prove that the patch fixes the named
vulnerability. The separate reproduction harness tests selected Go cases.

## What it does

Given an OSV URL or ID, it classifies the record into one fix state and emits a
schema-valid OSV record annotated with the result:

| State | Meaning | Decision |
|-------|---------|----------|
| `direct` | the record names a candidate fix commit | process |
| `indirect` | no local fix, but an upstream/alias record resolves to a candidate | process |
| `version_only` | a fixed *version* exists but no commit (common for PyPI/GHSA) | process |
| `none` | no accepted fix candidate for this workflow | **skip** |

The `decision` field is a processing gate, not a patch-priority recommendation.
The `none` gate matters: records with no accepted fix candidate are skipped by
this workflow.

## Usage

```bash
go run . GO-2026-6142
# or: go run . https://osv.dev/vulnerability/GO-2026-6142
```

This Go CLI fetches the advisory and prints annotated OSV JSON. It does not run
regression tests. Use Go 1.27.2 or a compatible toolchain, plus network access
to fetch the advisory and referenced patches.

To reproduce a single Go case end to end, install Git, Python 3, and Docker,
then run from the repository root:

```bash
python3 -I repro/tools/gorepro.py /tmp/osv-repro \
  GO-2026-6142 https://github.com/kube-logging/logging-operator cf437d7f1e05
```

The arguments are work directory, advisory ID, repository URL, and candidate
fix SHA. The harness prints a JSON verdict and writes the parent and fixed logs
under the work directory. Inspect the named test and both logs before trusting
the verdict: a package-level failure alone does not prove the changed security
test failed. `repro/examples/` holds saved logs for this and other cases to
compare against.

Output is the input OSV record plus, under `database_specific`:

```json
"database_specific": {
  "fix_status": "direct",
  "decision": "process",
  "diff": { "available": true },
  "missing": ["cwe_ids"]
}
```

A resolved fix commit is also added as a standard `references` entry of type `FIX`.

## Design

- **Deterministic ranking.** Classification applies fixed heuristics to
  references and patches; it does not use a model. A ranked candidate is not
  behavioral proof of the advisory claim.
- **No non-standard fields.** The output carries only OSV's 16 top-level fields;
  everything added sits in `database_specific`. `emit.check_standard` enforces
  this and fails loudly otherwise.
- **Absence, not nulls.** A field we can't fill is omitted (OSV convention) and
  listed in `database_specific.missing`.

## Status

The Go resolver and an experimental Go reproduction harness are included.
The larger study's merged evidence and independent replay are not yet public.

## Tests

```bash
go test ./...
```

`release_test.go` checks the release-commit classifier; it needs no network or
fixtures.

## License

MIT. See [LICENSE](LICENSE).
