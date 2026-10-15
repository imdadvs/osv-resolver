"""Patch handling tests with small, real Git histories."""

import subprocess

from repro.tools.partial_revert import (
    apply_reverse,
    candidate_sets,
    extract_code_hunks,
    render_patch,
)


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Patch Test")
    git(repo, "config", "user.email", "patch@example.invalid")
    return repo


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def test_extract_keeps_tests_and_can_reverse_selected_hunks(tmp_path):
    repo = make_repo(tmp_path)
    pkg = repo / "pkg"
    (pkg / "testdata").mkdir(parents=True)
    (pkg / "core.go").write_text("".join("line %02d\n" % i for i in range(20)))
    (pkg / "core_test.go").write_text("old test\n")
    (pkg / "testdata" / "input.txt").write_text("old data\n")
    before = commit(repo, "before")

    lines = (pkg / "core.go").read_text().splitlines(keepends=True)
    lines[1] = "FIX ONE\n"
    lines[17] = "FIX TWO\n"
    (pkg / "core.go").write_text("".join(lines))
    (pkg / "core_test.go").write_text("fixed test\n")
    (pkg / "testdata" / "input.txt").write_text("fixed data\n")
    fix = commit(repo, "fix")

    hunks = extract_code_hunks(repo, before, fix, tested_packages=["./pkg"])
    assert len(hunks) == 2
    assert all(h.path == "pkg/core.go" for h in hunks)
    assert all(h.changed_lines == 2 for h in hunks)
    assert [h.id for h in hunks] == [
        h.id for h in extract_code_hunks(repo, before, fix, tested_packages=["./pkg"])
    ]
    assert [len(candidate) for candidate in candidate_sets(hunks)] == [1, 1, 2]

    applied, diagnostic = apply_reverse(repo, [hunks[0]])
    assert applied, diagnostic
    current = (pkg / "core.go").read_text()
    assert "line 01\n" in current
    assert "FIX TWO\n" in current
    assert (pkg / "core_test.go").read_text() == "fixed test\n"
    assert (pkg / "testdata" / "input.txt").read_text() == "fixed data\n"

    # Reusing a candidate without restoring the fixed tree is rejected.
    applied, diagnostic = apply_reverse(repo, [hunks[0]])
    assert not applied
    assert diagnostic

    git(repo, "checkout", "-qf", fix)
    applied, diagnostic = apply_reverse(repo, [hunks[1]])
    assert applied, diagnostic
    current = (pkg / "core.go").read_text()
    assert "FIX ONE\n" in current
    assert "line 17\n" in current

    git(repo, "checkout", "-qf", fix)
    applied, diagnostic = apply_reverse(repo, hunks)
    assert applied, diagnostic
    assert (pkg / "core.go").read_text() == "".join(
        "line %02d\n" % i for i in range(20)
    )
    assert (pkg / "core_test.go").read_text() == "fixed test\n"


def test_rank_tested_package_then_smallest_hunk(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tested").mkdir()
    (repo / "other").mkdir()
    (repo / "tested" / "a.go").write_text("a\nb\nc\n")
    (repo / "tested" / "b.go").write_text("a\nb\nc\n")
    (repo / "other" / "c.go").write_text("a\nb\nc\n")
    before = commit(repo, "before")
    (repo / "tested" / "a.go").write_text("A\nB\nc\n")
    (repo / "tested" / "b.go").write_text("a\nB\nc\n")
    (repo / "other" / "c.go").write_text("a\nB\nc\n")
    fix = commit(repo, "fix")
    hunks = extract_code_hunks(repo, before, fix, tested_packages=["./tested"])
    assert [h.path for h in hunks] == [
        "tested/b.go", "tested/a.go", "other/c.go"
    ]


def test_new_deleted_binary_and_mode_changes_are_atomic(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "gone.go").write_text("old source\n")
    (repo / "mode.go").write_text("same source\n")
    before = commit(repo, "before")
    (repo / "gone.go").unlink()
    (repo / "new.go").write_text("new source\n")
    (repo / "space name.go").write_text("another new source\n")
    (repo / "binary.bin").write_bytes(b"\0\x01\x02\xff")
    (repo / "mode.go").chmod(0o755)
    fix = commit(repo, "fix")

    hunks = extract_code_hunks(repo, before, fix)
    assert {h.path for h in hunks} == {
        "gone.go", "new.go", "space name.go", "binary.bin", "mode.go"
    }
    assert all(h.old_start is None and h.new_start is None for h in hunks)
    assert len(list(candidate_sets(hunks))) == 5 + 10 + 1
    assert render_patch(hunks).startswith(b"diff --git ")

    applied, diagnostic = apply_reverse(repo, hunks)
    assert applied, diagnostic
    assert (repo / "gone.go").read_text() == "old source\n"
    assert not (repo / "new.go").exists()
    assert not (repo / "space name.go").exists()
    assert not (repo / "binary.bin").exists()
    assert not ((repo / "mode.go").stat().st_mode & 0o111)


def test_pair_search_is_complete_and_whole_set_is_not_duplicated():
    hunks = tuple(range(4))
    candidates = list(candidate_sets(hunks))
    assert candidates[:4] == [(0,), (1,), (2,), (3,)]
    assert candidates[4:-1] == [
        (0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)
    ]
    assert candidates[-1] == hunks
    assert list(candidate_sets(())) == []
    assert list(candidate_sets((0,))) == [(0,)]
    assert list(candidate_sets((0, 1))) == [(0,), (1,), (0, 1)]
