"""Triage an OSV record to a fix state, deterministically.

    direct        - the record names the fixing commit (FIX ref or GIT fixed event)
    indirect      - no local fix, but an upstream/alias record resolves to one
    version_only  - a fixed *version* exists but no commit (common for PyPI/GHSA);
                    diffable once the version is mapped to a tag/commit (later rung)
    none          - no accepted fix anywhere (skip: unpatched, PR pending, ...)

No LLM. Every rung is a plain lookup; the result degrades to "none" rather
than guessing.
"""


def find_fix_commit(record: dict):
    """A fixing commit named in the record.

    A GIT range's `fixed` event is always a real commit, so it is preferred
    over a FIX reference, which OSV sometimes points at an advisory page rather
    than a commit.
    """
    for aff in record.get("affected", []):
        for rng in aff.get("ranges", []):
            if rng.get("type") == "GIT":
                repo = rng.get("repo", "").rstrip("/")
                for ev in rng.get("events", []):
                    if "fixed" in ev and repo:
                        return f"{repo}/commit/{ev['fixed']}", "range"
    for ref in record.get("references", []):
        if ref.get("type") == "FIX":
            return ref["url"], "references"
    return None, None


def find_fixed_version(record: dict) -> bool:
    """A non-GIT range carrying a `fixed` event: a fix exists as a version."""
    for aff in record.get("affected", []):
        for rng in aff.get("ranges", []):
            if rng.get("type") != "GIT":
                if any("fixed" in ev for ev in rng.get("events", [])):
                    return True
    return False


def upstream_ids(record: dict):
    """Rung 4 candidates: other records that may carry the fix (dedup, drop self)."""
    ids = list(record.get("upstream", [])) + list(record.get("aliases", []))
    return [i for i in dict.fromkeys(ids) if i != record.get("id")]


def classify(record: dict, fetch_fn=None, _depth: int = 0, _seen=None) -> dict:
    """Return {fix_status, [fix_commit], [fix_source], [resolved_via]}."""
    if _seen is None:
        _seen = set()
    _seen.add(record.get("id"))

    # Rung 2+3: a fixing commit named in this record.
    url, src = find_fix_commit(record)
    if url:
        return {"fix_status": "direct", "fix_commit": url, "fix_source": src}

    # Rung 4: follow upstream/alias records; an upstream commit beats a local
    # package version, so this is tried before settling for version_only.
    if fetch_fn and _depth < 3:
        for uid in upstream_ids(record):
            if uid in _seen:
                continue
            try:
                upstream = fetch_fn(uid)
            except Exception:
                continue
            result = classify(upstream, fetch_fn, _depth + 1, _seen)
            if result["fix_status"] in ("direct", "indirect"):
                result["fix_status"] = "indirect"
                result["resolved_via"] = uid
                return result

    # Rung 5: a fixed version exists locally but no commit is linked.
    if find_fixed_version(record):
        return {"fix_status": "version_only"}

    return {"fix_status": "none"}
