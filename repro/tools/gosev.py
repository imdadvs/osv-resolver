"""Group Go advisories into unique vulnerabilities (GO-, GHSA-, CVE- aliases
merged), give each the GitHub severity label, and count GitHub fix links."""
import json, os, re, sys, collections
D = sys.argv[1]
recs = {}
for f in os.listdir(D):
    r = json.load(open(os.path.join(D, f)))
    if r.get("withdrawn") or r["id"].startswith("MAL-"):
        continue
    recs[r["id"]] = r
# union-find over ids and aliases
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
for r in recs.values():
    for a in r.get("aliases", []) + r.get("upstream", []):
        parent[find(a)] = find(r["id"])
groups = collections.defaultdict(list)
for i in recs:
    groups[find(i)].append(recs[i])
GH = re.compile(r"https?://github\.com/[^/]+/[^/]+/(commit|pull)/")
def label(r):
    ds = r.get("database_specific") or {}
    return ds.get("severity") if isinstance(ds.get("severity"), str) else None
c = collections.Counter(); out = []
for g in groups.values():
    sev = next((label(r).upper() for r in g if label(r)), "NONE")
    fix = any(GH.match(ref.get("url", "")) for r in g for ref in r.get("references", [])) or \
          any(rg.get("type") == "GIT" and "github.com" in rg.get("repo", "") for r in g for a in r.get("affected", []) for rg in a.get("ranges", []))
    c[(sev, fix)] += 1
    out.append({"ids": sorted(r["id"] for r in g), "severity": sev, "github_fix": fix})
for sev in ["CRITICAL", "HIGH", "MODERATE", "LOW", "NONE"]:
    print(f"{sev:9} unique={c[(sev,True)]+c[(sev,False)]:5}  with_github_fix={c[(sev,True)]}")
print("unique total", len(groups))
json.dump(out, open(sys.argv[2], "w"))
