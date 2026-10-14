"""Normalize any OSV reference to an ID and fetch the record from osv.dev."""

import json
import re
import urllib.request

OSV_API = "https://api.osv.dev/v1/vulns/"


def normalize_id(ref: str) -> str:
    """Accept an osv.dev URL, an api.osv.dev URL, or a bare ID (CVE-*, GHSA-*, ...)."""
    ref = ref.strip()
    for pattern in (r"/vulnerability/([^/?#]+)", r"/vulns/([^/?#]+)"):
        m = re.search(pattern, ref)
        if m:
            return m.group(1)
    return ref


def fetch(ref: str, timeout: int = 30) -> dict:
    """Fetch an OSV record by URL or ID. Raises on network/HTTP error."""
    vid = normalize_id(ref)
    with urllib.request.urlopen(OSV_API + vid, timeout=timeout) as resp:
        return json.load(resp)
