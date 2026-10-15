# Negative-control protocol (frozen before running)

Written and committed **before** any control is run, so the method is fixed and
not tuned to the result. Purpose: measure how often a fail-before/pass-after
"reproduced" verdict could be produced by a change that is *not* the security
fix — i.e. the method's false-positive rate.

## Hypothesis

If the proving test genuinely tracks the security fix, then reverting an
*unrelated* code change while keeping the security fix in place should leave the
test **passing**. A test that fails under that condition is a false positive.

## Sampling

- Draw **100 controls**, stratified: **50 from direct reproductions, 50 from
  partial-revert reproductions**, sampled at random from the frozen reproduced
  set (after pile A completes and quarantined cases are removed).
- Each control is tied to one reproduced advisory.

## Matching criteria (for the unrelated hunk)

For each sampled case, pick one unrelated hunk to revert that is matched to the
real security hunk by, in priority order:
1. **same repository**,
2. **same file type** (e.g. a `.go` non-test file),
3. **approximate diff size** (within ~2× the security hunk's changed-line count),
4. **same time period** (a commit near the fix date, not years apart).
The reverted hunk must **not** be part of the security fix and must **not** be a
test or testdata change.

## Per-control procedure (fixed order)

1. Check out the fixed commit. Confirm the proving test **passes** with the
   security fix present. If it does not, **exclude** the case (it is not a valid
   control) and record the exclusion.
2. Apply **only** the unrelated reversion (security fix still in place).
3. Run the proving test once; re-run once to guard against flakiness.

## Failure definition

- **Control failure (false positive):** the proving test **fails** in step 3
  while the security fix is intact.
- **Control pass (expected):** the test still passes.
- **Excluded:** did not pass step 1, or no matched unrelated hunk exists.

## Reporting

- Report the false-positive rate as `control failures / valid controls`, with
  the exclusion count stated separately.
- Report direct and partial-revert strata separately and combined.
- The number is reported **as measured**, whatever it is. No case is reclassified
  after the fact.

## What this does and does not establish

Establishes an empirical false-positive rate for the fail-before/pass-after
signal under matched, non-security changes. Does **not** establish reachability,
exploitability, or that every reproduced case is correctly attributed to its
advisory (the one-commit-fixes-many attribution issue is tracked separately).
