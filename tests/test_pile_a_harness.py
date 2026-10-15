"""Exercise the complete harness with real Git histories and local Go tests.

The Docker shim only maps the throwaway mount to the host Go compiler, keeping
these orchestration tests independent of a Docker daemon or downloaded image.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


HARNESS = Path(__file__).resolve().parents[1] / "repro" / "tools" / "gorepro.py"
pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="Go is required for the integration fixture")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def fixture(tmp_path, adaptation=False, suite_fallback=False):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Harness Test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo / "go.mod").write_text("module example.test/demo\n\ngo 1.20\n")
    original = 'package demo\n\nconst label = "old"\n\nfunc Value(v string) string {\n    return v\n}\n'
    (repo / "code.go").write_text(original)
    if suite_fallback:
        (repo / "suite_test.go").write_text('package demo\nimport "testing"\nfunc TestSecurity(t *testing.T) { runSpec(t) }\n')
        (repo / "spec_test.go").write_text('package demo\nimport "testing"\nfunc runSpec(t *testing.T) {}\n')
    before = commit(repo, "before")
    if adaptation:
        fixed = original + '\nfunc NewAPI(v string) string {\n    if v == "bad" { return "" }\n    return v\n}\n'
    else:
        fixed = original.replace('label = "old"', 'label = "new"').replace(
            "    return v", '    if v == "bad" {\n        return ""\n    }\n    return v')
        fixed += '\nfunc NewAPI(v string) string {\n    return Value(v)\n}\n'
    (repo / "code.go").write_text(fixed)
    test_source = '''package demo
import "testing"
func TestSecurity(t *testing.T) {
    if NewAPI("bad") != "" { t.Fatal("guard did not reject input") }
}
'''
    if suite_fallback:
        (repo / "spec_test.go").write_text(test_source.replace("func TestSecurity", "func runSpec"))
    else:
        (repo / "code_test.go").write_text(test_source)
    fix = commit(repo, "fix")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "docker"
    shim.write_text("#!" + sys.executable + "\n" + '''import os, pathlib, subprocess, sys
args = sys.argv[1:]
mount = next(args[i + 1] for i, arg in enumerate(args) if arg == "-v" and args[i + 1].endswith(":/src"))
repo = pathlib.Path(mount[:-5])
workdir = args[args.index("-w") + 1]
cwd = repo / workdir.removeprefix("/src").lstrip("/")
flag = os.environ.get("PILE_A_FAIL_CANDIDATE_ONCE")
code = (repo / "code.go").read_text()
if flag and 'if v == "bad"' not in code and "func NewAPI" in code and not pathlib.Path(flag).exists():
    pathlib.Path(flag).write_text("failed")
    print("temporary Docker failure", file=sys.stderr)
    raise SystemExit(125)
command = args[args.index("timeout") + 2:]
command[0] = ''' + repr(shutil.which("go")) + '''
env = os.environ.copy()
env.update(GOCACHE=str(repo.parent.parent / "test-cache"), GOTOOLCHAIN="local", GOFLAGS="")
raise SystemExit(subprocess.run(command, cwd=cwd, env=env).returncode)
''')
    shim.chmod(0o755)
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    return repo, before, fix, env


def run(tmp_path, repo, before, fix, env, max_attempts=None):
    command = [sys.executable, "-I", str(HARNESS), str(tmp_path / "work"), "GO-TEST-1", str(repo), fix,
               "--pile-a", "--expected-fix-sha", fix, "--expected-before", before]
    if max_attempts:
        command += ["--max-attempts", str(max_attempts)]
    process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout.strip().splitlines()[-1])


def test_budget_resume_recovers_truncated_checkpoint_and_proves_guard(tmp_path):
    repo, before, fix, env = fixture(tmp_path)
    first = run(tmp_path, repo, before, fix, env, 1)
    assert first["verdict"] == "search_incomplete"
    assert first["completed_candidates"] == 1
    checkpoint = Path(first["checkpoint"])
    with checkpoint.open("ab") as fh:
        fh.write(b'{"type":')
    result = run(tmp_path, repo, before, fix, env)
    assert result["verdict"] == "reproduced"
    assert result["proof"]["failed_tests"] == ["TestSecurity"]
    assert len(result["fix_sha"]) == len(result["before"]) == 40
    assert Path(result["patch"]).exists()
    rows = [json.loads(line) for line in checkpoint.read_text().splitlines()]
    assert rows[-1]["confirmation"]["fixed"] == "pass"
    assert len(rows[-1]["hunks"]) == 1


def test_missing_api_routes_to_test_adaptation(tmp_path):
    repo, before, fix, env = fixture(tmp_path, adaptation=True)
    result = run(tmp_path, repo, before, fix, env)
    assert result["verdict"] == "needs_test_adaptation"
    assert result["full_revert_state"] == "build_failed"


def test_package_suite_entrypoint_is_kept_when_changed_spec_has_no_test_name(tmp_path):
    repo, before, fix, env = fixture(tmp_path, suite_fallback=True)
    result = run(tmp_path, repo, before, fix, env)
    assert result["verdict"] == "reproduced"
    assert result["test_selection_fallback"] == ["."]
    assert result["proof"]["failed_tests"] == ["TestSecurity"]


def test_transient_candidate_error_is_retried_on_resume(tmp_path):
    repo, before, fix, env = fixture(tmp_path)
    env["PILE_A_FAIL_CANDIDATE_ONCE"] = str(tmp_path / "failed-once")
    first = run(tmp_path, repo, before, fix, env, 2)
    assert first["verdict"] == "search_incomplete"
    assert first["completed_candidates"] == 1
    result = run(tmp_path, repo, before, fix, env)
    assert result["verdict"] == "reproduced"


def test_changed_saved_commit_is_rejected_before_any_test(tmp_path):
    repo, before, fix, env = fixture(tmp_path)
    command = [sys.executable, "-I", str(HARNESS), str(tmp_path / "work"), "GO-TEST-1", str(repo), fix,
               "--pile-a", "--expected-fix-sha", "0" * 40]
    process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout.strip().splitlines()[-1])
    assert result["verdict"] == "stale_input"
    assert not list((tmp_path / "work" / "logs").glob("*.log"))
