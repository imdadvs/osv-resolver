"""Resolver tests against real OSV fixtures covering all four fix states."""

import json
import pathlib

import pytest

from osv_resolver.classify import classify
from osv_resolver.emit import ALLOWED_TOP, check_standard
from osv_resolver.resolve import resolve

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def fixture_fetch(ref):
    """Offline fetch_fn: serve upstream records from fixtures (no network)."""
    name = ref.rstrip("/").split("/")[-1]
    return load(name)


# (fixture id, expected fix_status, expected decision)
CASES = [
    ("CVE-2019-7317", "direct", "process"),          # FIX ref + GIT fixed commit
    ("CLEANSTART-2026-HQ42098", "indirect", "process"),  # resolves via upstream libpng
    ("GHSA-2qmj-7962-cjq8", "version_only", "process"),  # fixed version, no commit
    ("CVE-2026-108955", "none", "skip"),             # unpatched, PR pending
]


@pytest.mark.parametrize("name,status,decision", CASES)
def test_fix_status(name, status, decision):
    record = load(name)
    cls = classify(record, fetch_fn=fixture_fetch)
    assert cls["fix_status"] == status
    out = resolve(record, fetch_fn=fixture_fetch)
    assert out["database_specific"]["fix_status"] == status
    assert out["database_specific"]["decision"] == decision


@pytest.mark.parametrize("name,status,decision", CASES)
def test_output_is_schema_clean(name, status, decision):
    """Every output is a valid OSV record: no top-level field outside the 16."""
    out = resolve(load(name), fetch_fn=fixture_fetch)
    check_standard(out)
    assert set(out) <= ALLOWED_TOP


def test_direct_gets_fix_reference():
    out = resolve(load("CVE-2019-7317"), fetch_fn=fixture_fetch)
    assert any(r.get("type") == "FIX" for r in out["references"])


def test_unpatched_is_marked_skip_not_crash():
    out = resolve(load("CVE-2026-108955"), fetch_fn=fixture_fetch)
    assert out["database_specific"]["decision"] == "skip"
    assert out["database_specific"]["diff"]["available"] is False
