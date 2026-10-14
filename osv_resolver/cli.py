"""CLI: resolve an OSV advisory to an enriched, schema-valid record.

    python -m osv_resolver https://osv.dev/vulnerability/CVE-2026-108955
"""

import json
import sys

from .emit import check_standard
from .fetch import fetch
from .resolve import resolve


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m osv_resolver <osv-url-or-id>", file=sys.stderr)
        return 2
    try:
        record = fetch(argv[0])
    except Exception as exc:  # network / unknown ID
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    out = resolve(record, fetch_fn=fetch)
    check_standard(out)  # the 'no non-standard fields' gate
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
