"""Whole chain for a list of Go advisories: osv-resolver picks the fix commit,
gorepro.py tries to prove the bug with the fix's own tests.
Usage: gochain.py WORKDIR SAMPLE_JSON OUT_JSONL"""
import json, os, re, shutil, subprocess, sys

WORK, SAMPLE, OUT = sys.argv[1:4]
TOOLS = os.path.dirname(os.path.abspath(__file__))
RESOLVER = os.environ.get("RESOLVER", os.path.join(os.path.dirname(TOOLS), "osv-resolver"))
LINK = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/(commit|pull)/([0-9a-fA-F]+|\d+)")

done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["id"] for l in open(OUT) if l.strip()}
for item in json.load(open(SAMPLE)):
    vid = item["id"]
    if vid in done:
        continue
    row = {"id": vid, "severity": item["severity"]}
    r = subprocess.run([RESOLVER, vid], capture_output=True, text=True, timeout=600)
    try:
        ds = json.loads(r.stdout).get("database_specific", {})
    except ValueError:
        ds = {}
        row["resolver_error"] = (r.stderr or r.stdout)[-300:]
    commit = ds.get("fix_commit", "")
    row.update(fix_status=ds.get("fix_status"), fix_commit=commit, confidence=ds.get("fix_confidence"))
    m = LINK.match(commit or "")
    if not m:
        row["verdict"] = "no_github_fix_commit"
    else:
        repo = f"https://github.com/{m[1]}/{m[2]}"
        try:
            p = subprocess.run(["python3", "-I", os.path.join(TOOLS, "gorepro.py"), WORK, vid, repo, m[4]],
                               capture_output=True, text=True, timeout=3600)
            last = (p.stdout.strip().splitlines() or [""])[-1]
            res = json.loads(last) if last.startswith("{") else {}
            if "verdict" not in res:  # the script crashed: keep its traceback
                res = {"verdict": "script_error", "err": (p.stderr or p.stdout)[-400:]}
        except subprocess.TimeoutExpired:
            res = {"verdict": "timeout"}
        row.update({k: v for k, v in res.items() if k not in ("id", "fix")})
    # Free the disk: the repo and GOPATH are only needed while testing.
    shutil.rmtree(os.path.join(WORK, "repos", vid), ignore_errors=True)
    shutil.rmtree(os.path.join(WORK, "gopath", vid), ignore_errors=True)
    with open(OUT, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(vid, row.get("confidence"), row["verdict"], flush=True)
