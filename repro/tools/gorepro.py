"""Experiment: reproduce a Go vulnerability with the fix commit's own tests.

For a fix commit F with parent P:
  fixed run: check out F, run the tests F added or changed      -> should pass
  old run:   check out P, lay F's test files on top, run again  -> should fail
A test failure (not a build failure) on P plus a pass on F means reproduced.

Usage: gorepro.py WORKDIR ID REPO_URL FIX(commit sha | pull number)
"""
import json, os, re, subprocess, sys

WORK, VID, REPO, FIX = sys.argv[1:5]
IMAGE = "golang:1.25"
name = VID
repo_dir = os.path.join(WORK, "repos", name)
log_dir = os.path.join(WORK, "logs")


def git(*args, check=True):
    r = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr[-500:]))
    return r.stdout


def result(verdict, **kw):
    out = {"id": VID, "repo": REPO, "fix": FIX, "verdict": verdict, **kw}
    print(json.dumps(out))
    sys.exit(0)


# 1. Get the repo and the fix. A pull request becomes its head commit, and the
#    "before" point is the parent of its first commit.
if not os.path.isdir(repo_dir):
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", REPO, repo_dir], check=True)
if FIX.isdigit():
    # The PR's .patch lists its commits oldest first; "before" is the parent
    # of the first one, "fix" is the last one.
    import urllib.request
    owner_repo = REPO.rstrip("/").split("github.com/")[1]
    patch = urllib.request.urlopen(f"https://github.com/{owner_repo}/pull/{FIX}.patch", timeout=60).read().decode("utf-8", "replace")
    shas = re.findall(r"^From ([0-9a-f]{40}) ", patch, re.M)
    git("fetch", "-q", "origin", f"pull/{FIX}/head:pr{FIX}")
    fix = shas[-1]
    before = git("rev-parse", shas[0] + "^").strip()
else:
    git("fetch", "-q", "origin", FIX, check=False)
    fix = git("rev-parse", FIX + "^{commit}").strip()
    parents = git("log", "-1", "--format=%P", fix).split()
    if not parents:
        result("fix_is_first_commit")
    before = parents[0]  # for a merge, the mainline parent: the state before the merge

changed = git("diff", "--name-only", before, fix).split()
tests = [f for f in changed if f.endswith("_test.go")]
testdata = [f for f in changed if "/testdata/" in "/" + f]
if not tests:
    result("no_test_in_fix", files=changed[:20])

# 2. Which test functions did the fix add or touch? Added "func TestX" lines,
#    plus the function each changed hunk sits in (git prints it after "@@").
diff = git("diff", "-U0", before, fix, "--", *tests)
names = set(re.findall(r"^\+func (Test\w+)\(", diff, re.M))
names |= set(re.findall(r"^@@[^@]*@@ func (Test\w+)\(", diff, re.M))
names |= set(re.findall(r"^@@[^@]*@@ func \([^)]*\) (Test\w+)\(", diff, re.M))  # suite methods
pkgs = sorted({"./" + os.path.dirname(t) if os.path.dirname(t) else "." for t in tests})
# No plain "func TestX" touched (e.g. Ginkgo specs): run every test in the
# packages and compare which ones fail.
run = "^(" + "|".join(sorted(names)) + ")$" if names else "."


# Go releases, (minor, first day). Old code is built with the Go that was
# current when the fix was made; newer Go rejects some old go.mod files.
GO_RELEASES = [(10, "2018-02-16"), (11, "2018-08-24"), (12, "2019-02-25"), (13, "2019-09-03"),
               (14, "2020-02-25"), (15, "2020-08-11"), (16, "2021-02-16"), (17, "2021-08-16"),
               (18, "2022-03-15"), (19, "2022-08-02"), (20, "2023-02-01"), (21, "2023-08-08"),
               (22, "2024-02-06"), (23, "2024-08-13"), (24, "2025-02-11"), (25, "2025-08-12")]


def go_image(commit):
    day = git("log", "-1", "--format=%cs", commit).strip()
    minor = 10
    for m, released in GO_RELEASES:
        if released <= day:
            minor = m
    return f"golang:1.{minor}"


_import_path = None


def import_path():
    """Where a GOPATH-era repo must sit. Usually its GitHub URL, but a renamed
    project keeps its old path (moby/moby imports github.com/docker/docker), so
    read the repo's own imports: the prefix whose remainder names a folder in
    the repo is the real one."""
    global _import_path
    if _import_path is not None:
        return _import_path
    from_url = REPO.rstrip("/").split("://", 1)[1].removesuffix(".git")
    counts, seen = {}, 0
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in ("vendor", ".git", "testdata")]
        for f in files:
            if not f.endswith(".go") or seen > 3000:
                continue
            seen += 1
            try:
                text = open(os.path.join(root, f), errors="replace").read()
            except OSError:
                continue
            for imp in re.findall(r'"([a-z0-9.-]+\.[a-z]+/[^"\s]+)"', text):
                parts = imp.split("/")
                for n in (2, 3):
                    if len(parts) > n and os.path.isdir(os.path.join(repo_dir, *parts[n:])):
                        counts["/".join(parts[:n])] = counts.get("/".join(parts[:n]), 0) + 1
    best = max(counts, key=counts.get) if counts else from_url
    _import_path = best if counts.get(best, 0) >= 3 else from_url
    return _import_path


def in_workspace(root):
    """True when a go.work file governs this module (it rejects -mod=mod)."""
    d = root or "."
    while True:
        if os.path.exists(os.path.join(repo_dir, d, "go.work")):
            return True
        if d in ("", "."):
            return False
        d = os.path.dirname(d)


def package_results(text):
    """Per-package outcome of `go test`: {pkg: (state, [failed tests])} where
    state is pass, fail, build (could not compile) or none (no tests ran)."""
    out, pending = {}, []
    for line in text.split("\n"):
        m = re.match(r"^\s*--- FAIL: (\S+)", line)
        if m:
            pending.append(m[1])
            continue
        m = re.match(r"^(ok|FAIL|\?)\s+(\S+)\s*(.*)$", line)
        if not m:
            continue
        status, pkg, rest = m.groups()
        if status == "ok":
            state = "none" if "no tests to run" in rest else "pass"
        elif status == "FAIL":
            state = "build" if "build failed" in rest or "setup failed" in rest else "fail"
        else:
            state = "none"
        out[pkg] = (state, pending)
        pending = []
    return out


def module_root(path):
    """The nearest folder at or above path that has a go.mod, or None."""
    d = path
    while True:
        if os.path.exists(os.path.join(repo_dir, d, "go.mod")):
            return d
        if d in ("", "."):
            return None
        d = os.path.dirname(d)


def go_test(label, commit):
    """Run the chosen tests. A repo can hold several Go modules (cosmos-sdk's
    x/group, oh-my-posh's src/), so tests are grouped by the module they sit in
    and each group runs from its own module folder."""
    groups = {}
    for p in pkgs:
        rel = p[2:] if p.startswith("./") else ""
        root = module_root(rel)
        if root is None:
            groups.setdefault(None, []).append(p)
        else:
            sub = os.path.relpath(rel or ".", root or ".")
            groups.setdefault(root, []).append("./" + sub if sub != "." else ".")
    texts, rc = [], 0
    for root, group in groups.items():
        code, text = go_test_module(label, commit, root, group)
        rc |= code
        texts.append(text)
    text = "\n".join(texts)
    if rc == 0:
        state = "pass" if re.search(r"^ok\s", text, re.M) else "no_tests_ran"
    elif re.search(r"\[build failed\]|\[setup failed\]|cannot find package|undefined: |could not import|^# ", text, re.M) \
            and not re.search(r"^--- FAIL", text, re.M):
        state = "build_failed"
    elif re.search(r"^--- FAIL|^panic: |DATA RACE|^FAIL\s", text, re.M):
        state = "fail"
    else:
        state = "error"
    failed = re.findall(r"^\s*--- FAIL: (\S+)", text, re.M)
    return state, failed, text


def go_test_module(label, commit, root, group):
    # Not root: some projects (gitea) refuse to run their tests as root.
    cache = os.path.join(WORK, "gocache")
    os.makedirs(cache, exist_ok=True)
    env = ["-e", "HOME=/tmp", "-e", "GOCACHE=/cache/build", "-e", "GOTOOLCHAIN=auto"]
    test = ["go", "test", "-count=1", "-run", run, *group]
    vols = ["-v", f"{cache}:/cache"]
    if root is not None:
        mod_dir = os.path.join(repo_dir, root)
        vendored = os.path.exists(os.path.join(mod_dir, "vendor", "modules.txt"))
        env += ["-e", "GOMODCACHE=/cache/mod"]
        if vendored:
            env += ["-e", "GOFLAGS=-mod=vendor"]
        elif not in_workspace(root):
            env += ["-e", "GOFLAGS=-mod=mod"]
        vols += ["-v", f"{repo_dir}:/src"]
        workdir, script = os.path.normpath(os.path.join("/src", root)), test
    else:
        # Before modules: the repo must sit at its import path in a GOPATH,
        # and `go get` fetches its dependencies first. One GOPATH per
        # advisory, so parallel runs don't fight over `go get`.
        workdir = "/gopath/src/" + import_path()
        gopath = os.path.join(WORK, "gopath", name)
        # Make every folder on the host first: Docker would create the missing
        # ones as root, and `go get` could not write beside them.
        os.makedirs(os.path.join(gopath, "src", import_path()), exist_ok=True)
        vols += ["-v", f"{gopath}:/gopath", "-v", f"{repo_dir}:{workdir}"]
        env += ["-e", "GOPATH=/gopath", "-e", "GO111MODULE=off"]
        # `go get` fetches today's dependencies, which no longer build with a
        # 2017 compiler, so each one is rolled back to its last commit before
        # the fix date. The project itself (also under /gopath/src) is skipped.
        # Older dependencies can need packages not yet fetched: two rounds.
        day = git("log", "-1", "--format=%cs", commit).strip()
        rollback = (f'for d in $(find /gopath/src -name .git -type d -not -path "{workdir}/.git"); do '
                    f'r=${{d%/.git}}; c=$(git -C $r rev-list -1 --before={day} HEAD 2>/dev/null); '
                    f'[ -n "$c" ] && git -C $r checkout -q $c 2>/dev/null; done')
        get = "go get -d -t " + " ".join(group) + " >/dev/null 2>&1"
        script = ["sh", "-c", "; ".join([get, rollback, get, rollback, " ".join("'" + a + "'" for a in test)])]
    text, code = "", 1
    for attempt in range(3):
        cmd = ["docker", "run", "--rm", "--user", "1000:1000", "--memory", "8g", "--cpus", "4", *vols,
               "-w", workdir, *env, go_image(commit), "timeout", "900", *script]
        r = subprocess.run(cmd, capture_output=True, text=True)
        text, code = r.stdout + r.stderr, (1 if r.returncode else 0)
        with open(os.path.join(log_dir, f"{name}.{label}.log"), "a") as fh:
            fh.write(" ".join(cmd) + "\n\n" + text + "\n")
        # "no tests to run" exits 0 but is still a miss we can rescue, so retry
        # whenever a rescue rule fired, not only on a non-zero exit.
        no_tests = bool(re.search(r"no tests to run", text))
        fix = rescue(text, env, test, root)
        if (code == 0 and not no_tests) or not fix:
            break
        with open(os.path.join(log_dir, f"{name}.{label}.log"), "a") as fh:
            fh.write(f"\n### retry: {fix}\n")
        if root is not None:
            script = test
        else:
            script[-1] = "; ".join(script[-1].split("; ")[:-1] + [" ".join("'" + a + "'" for a in test)])
    return code, text


def rescue(text, env, test, root):
    """Read a failed run and adjust the next one. Each rule is a plain
    build-setup problem the output names outright; none touches the code
    under test. Returns what was changed, or "" to give up."""
    # Go 1.13 and older reject -mod=mod.
    if "-mod=mod not supported" in text and "GOFLAGS=-mod=mod" in env:
        del env[env.index("GOFLAGS=-mod=mod") - 1:env.index("GOFLAGS=-mod=mod") + 1]
        return "dropped -mod=mod"
    # "sqlite3 requires: -tags sqlite,sqlite_unlock_notify"
    m = re.search(r"requires: -tags ([\w,]+)", text)
    if m and "-tags" not in test:
        test[1:1] = ["-tags", m[1]]
        return "added -tags " + m[1]
    # A missing sqlite driver ("unknown driver \"sqlite3\"") is the same need
    # stated a different way: the sqlite build tags were not set.
    if re.search(r'unknown driver "sqlite3"', text) and "-tags" not in test:
        test[1:1] = ["-tags", "sqlite,sqlite_unlock_notify"]
        return "added -tags sqlite,sqlite_unlock_notify"
    # Our -run regex matched nothing ("no tests to run"): the touched test is a
    # subtest or renamed, so widen to every test in the package.
    if re.search(r"no tests to run", text) and "-run" in test:
        i = test.index("-run")
        if test[i + 1] != ".":
            test[i + 1] = "."
            return "widened -run to the whole package"
    # A test package guarded by a build tag (//go:build integration).
    m = re.search(r"build constraints exclude all Go files in /src/(\S+)", text)
    if m and "-tags" not in test:
        tags = set()
        folder = os.path.join(repo_dir, m[1])
        for f in os.listdir(folder) if os.path.isdir(folder) else []:
            if f.endswith(".go"):
                head = open(os.path.join(folder, f), errors="replace").read(400)
                for line in re.findall(r"^//(?:go:build|\s*\+build) (.*)$", head, re.M):
                    tags |= {w for w in re.findall(r"\b\w+\b", line) if w not in ("ignore",)
                             and ("!" + w) not in line}
        if tags:
            test[1:1] = ["-tags", ",".join(sorted(tags))]
            return "added -tags " + ",".join(sorted(tags))
    # An embedded frontend that was never built ("pattern all:dist: no
    # matching files found"): a placeholder file lets the backend compile.
    m = re.search(r"pattern (?:all:)?([\w./-]+): no matching files found", text)
    if m and root is not None:
        folder = os.path.join(repo_dir, root, m[1])
        if not os.path.exists(os.path.join(folder, "index.html")):
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, "index.html"), "w").write("<!-- placeholder: frontend not built -->\n")
            return "stubbed embedded folder " + m[1]
    return ""


# 3. Fixed run. Logs are appended per module, so start them empty.
for label in ("fixed", "old"):
    if os.path.exists(os.path.join(log_dir, f"{name}.{label}.log")):
        os.remove(os.path.join(log_dir, f"{name}.{label}.log"))
git("checkout", "-q", "-f", fix)
git("clean", "-qfdx")
fixed_state, fixed_failed, fixed_text = go_test("fixed", fix)

# 4. Old run: code from before the fix, tests from the fix.
git("checkout", "-q", "-f", before)
git("clean", "-qfdx")
# A test file the fix deleted or renamed does not exist at `fix`, so it
# cannot be checked out; it is removed from the old tree instead.
exist = set(git("ls-tree", "-r", "--name-only", fix).split("\n"))
want = [f for f in (*tests, *testdata) if f in exist]
gone = [f for f in (*tests, *testdata) if f not in exist]
if want:
    git("checkout", fix, "--", *want)
for f in gone:
    try:
        os.remove(os.path.join(repo_dir, f))
    except OSError:
        pass
old_state, old_failed, old_text = go_test("old", fix)

# A package whose tests pass on the fixed code and fail on the old code is a
# proof, even when a sibling package (say an end-to-end suite that needs a
# live cluster) could not run at all.
fixed_pk, old_pk = package_results(fixed_text), package_results(old_text)
proving = sorted(p for p, (st, _) in old_pk.items() if st == "fail" and fixed_pk.get(p, ("",))[0] == "pass")
proof_fails = [t for p in proving for t in old_pk[p][1]]
if proving and (names or proof_fails):
    verdict = "reproduced"
    old_failed = proof_fails
elif fixed_state != "pass":
    verdict = "fixed_does_not_pass"
elif old_state == "fail" and (names or old_failed):
    verdict = "reproduced"
elif old_state == "pass":
    verdict = "not_reproduced"  # the new tests pass on the old code too
elif old_state == "build_failed":
    verdict = "inconclusive_build"  # the tests need code the fix added
else:
    verdict = "inconclusive"
result(verdict, before=before[:12], fix_sha=fix[:12], tests=sorted(names), pkgs=pkgs,
       fixed=fixed_state, old=old_state, old_failed=old_failed[:10], proving_pkgs=proving,
       go_image=go_image(fix), import_path=import_path() if not os.path.exists(os.path.join(repo_dir, "go.mod")) else None)
