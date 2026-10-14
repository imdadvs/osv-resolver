"""Produce an enriched OSV record: the input, plus our resolution, in-schema.

Enrichment keys are dropped straight into `database_specific` as plain
snake_case keys, exactly how OSV source databases (VulDB, etc.) do it:
    fix_status   direct | indirect | none
    decision     process | skip
    diff         {available: bool}
    resolved_via the upstream ID a fix was found through (indirect only)
    missing      core fields we wanted but the record did not supply
A resolved fix commit is also added as a standard FIX reference.
"""

import copy

from .classify import classify


def _compute_missing(record: dict, cls: dict):
    missing = []
    has_cwe = "cwe_ids" in record.get("database_specific", {})
    if not has_cwe:
        missing.append("cwe_ids")
    has_fixed = any(
        "fixed" in ev
        for aff in record.get("affected", [])
        for rng in aff.get("ranges", [])
        for ev in rng.get("events", [])
    )
    if not has_fixed and cls["fix_status"] != "direct":
        missing.append("fixed_version")
    return missing


def resolve(record: dict, fetch_fn=None) -> dict:
    """Return a schema-valid OSV record enriched under database_specific."""
    cls = classify(record, fetch_fn)
    out = copy.deepcopy(record)

    ds = dict(out.get("database_specific", {}))
    ds["fix_status"] = cls["fix_status"]
    ds["decision"] = (
        "process" if cls["fix_status"] in ("direct", "indirect", "version_only") else "skip"
    )
    ds["diff"] = {"available": "fix_commit" in cls}
    if cls.get("fix_commit"):
        ds["fix_commit"] = cls["fix_commit"]
    if cls.get("resolved_via"):
        ds["resolved_via"] = cls["resolved_via"]
    missing = _compute_missing(out, cls)
    if missing:
        ds["missing"] = missing
    out["database_specific"] = ds

    # Record the resolved fix commit as a standard FIX reference if absent.
    if cls.get("fix_commit"):
        refs = out.setdefault("references", [])
        if not any(r.get("type") == "FIX" for r in refs):
            refs.append({"type": "FIX", "url": cls["fix_commit"]})

    return out
