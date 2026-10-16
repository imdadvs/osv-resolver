"""Rung 5: when the picked commit's test also passes on the parent, the pick
was probably wrong. Try the advisory's OTHER candidate commits with the same
check, and keep the first that shows fail-before/pass-after.

Reuses gorepro.py unchanged — it only calls it with each candidate in turn.
Usage: rung5.py WORKDIR IDS_JSON OUT_JSONL
"""
import json, os, re, subprocess, sys

WORK, IDS, OUT = sys.argv[1:4]
TOOLS = os.path.dirname(os.path.abspath(__file__))
RESOLVER = os.environ.get("RESOLVER", os.path.join(os.path.dirname(TOOLS), "osv-resolver"))
LINK = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/(commit|pull)/([0-9a-fA-F]+|\d+)")


def candidates(vid):
    """Every GitHub commit/PR the resolver associated with the advisory, the
    accepted picks first, then the rejected ones."""
    out = []
    r = subprocess.run([RESOLVER, vid], capture_output=True, text=True, timeout=300)
    try:
        ds = json.loads(r.stdout).get("database_specific", {})
    except ValueError:
        return out
    urls = list(ds.get("fix_commits") or [])
    urls += [x.get("url", "") for x in ds.get("rejected", [])]
    seen = set()
    for u in urls:
        m = LINK.match(u or "")
        if m and u not in seen:
            seen.add(u)
            out.append((f"https://github.com/{m[1]}/{m[2]}", m[4]))
    return out


done = {json.loads(l)["id"] for l in open(OUT)} if os.path.exists(OUT) else set()
for vid in json.load(open(IDS)):
    if vid in done:
        continue
    row = {"id": vid, "verdict": "no_alternative_reproduced", "tried": []}
    for repo, ident in candidates(vid):
        p = subprocess.run(["python3", "-I", os.path.join(TOOLS, "gorepro.py"),
                            WORK, vid, repo, ident], capture_output=True, text=True, timeout=3600)
        last = (p.stdout.strip().splitlines() or [""])[-1]
        try:
            res = json.loads(last) if last.startswith("{") else {}
        except ValueError:
            res = {}
        row["tried"].append({"commit": f"{repo}@{ident}", "verdict": res.get("verdict")})
        if res.get("verdict") == "reproduced":
            row.update(verdict="reproduced", winning_commit=f"{repo}@{ident}",
                       old_failed=res.get("old_failed"))
            break
    with open(OUT, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(vid, row["verdict"], flush=True)
