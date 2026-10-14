# osv-resolver

Turns a vulnerability advisory into the code change that fixed it.

A security advisory tells you a bug was fixed — rarely what the bug *was*.
`osv-resolver` takes any [OSV](https://osv.dev) record, finds the fixing
commit (following downstream → upstream references when needed), and emits an
enriched record you can diff. The output is itself a **valid OSV record**: every
field is standard, and the resolver's own data lives in `database_specific`,
OSV's sanctioned extension slot.

## What it does

Given an OSV URL or ID, it classifies the record into one fix state and emits a
schema-valid OSV record annotated with the result:

| State | Meaning | Decision |
|-------|---------|----------|
| `direct` | the record names the fixing commit | process |
| `indirect` | no local fix, but an upstream/alias record resolves to one | process |
| `version_only` | a fixed *version* exists but no commit (common for PyPI/GHSA) | process |
| `none` | no accepted fix — unpatched, PR pending | **skip** |

The `none` gate matters: records for unpatched bugs with public PoCs are logged
and skipped, not reconstructed.

## Usage

```bash
python -m osv_resolver https://osv.dev/vulnerability/CVE-2019-7317
```

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

- **Deterministic first.** Classification is plain lookups over standard OSV
  fields — no model, no guessing. The result degrades to `none` rather than
  inventing a fix.
- **No non-standard fields.** The output carries only OSV's 16 top-level fields;
  everything added sits in `database_specific`. `emit.check_standard` enforces
  this and fails loudly otherwise.
- **Absence, not nulls.** A field we can't fill is omitted (OSV convention) and
  listed in `database_specific.missing`.

## Status

Deterministic resolver (rungs 1–5). Next: version→commit resolution for
`version_only`, diff fetch, and an evaluation harness.

## Tests

```bash
pip install pytest
python -m pytest
```

Fixtures are real OSV records, one per fix state.
