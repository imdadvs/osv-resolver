"""Build and apply candidate partial reversions of a fix commit.

The caller starts from a clean checkout of ``fix``.  Test files and testdata
are excluded here so that the fix's own tests stay in place while code hunks
are selectively undone.  ``apply_reverse`` changes only the worktree; callers
must restore the fixed checkout between attempts.
"""

import hashlib
import itertools
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional


@dataclass(frozen=True)
class Hunk:
    """One independently reversible text hunk, or one atomic file change.

    ``patch`` includes the Git file header, so a single hunk is a usable patch.
    For additions, deletions, binary files, and mode changes, the whole file
    patch is atomic and the line numbers are ``None``.
    """

    id: str
    path: str
    old_start: Optional[int]
    new_start: Optional[int]
    patch: bytes
    changed_lines: int
    order: int = 0


def _git(repo_dir, *args):
    result = subprocess.run(
        ["git", "-C", os.fspath(repo_dir), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(
            "git %s failed: %s" % (
                " ".join(args), result.stderr.decode("utf-8", "replace").strip()
            )
        )
    return result.stdout


def _sections(diff):
    """Split a Git diff without decoding or changing patch bytes."""
    sections = []
    current = []
    for line in diff.splitlines(keepends=True):
        if line.startswith(b"diff --git "):
            if current:
                sections.append(b"".join(current))
            current = [line]
        elif current:
            current.append(line)
        elif line.strip():
            raise ValueError("unexpected text before first Git diff header")
    if current:
        sections.append(b"".join(current))
    return sections


def _changed_lines(patch):
    count = 0
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith(b"@@ "):
            in_hunk = True
        elif in_hunk and line.startswith((b"+", b"-")):
            count += 1
    return count


def _make_hunk(path, old_start, new_start, patch, order):
    digest = hashlib.sha256(patch).hexdigest()[:16]
    position = "file" if old_start is None else "%d-%d" % (old_start, new_start)
    return Hunk(
        id="%s:%s:%s" % (path, position, digest),
        path=path,
        old_start=old_start,
        new_start=new_start,
        patch=patch,
        changed_lines=_changed_lines(patch),
        order=order,
    )


def _file_hunks(path, section, first_order):
    lines = section.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(b"@@ ")]
    header = b"".join(lines[: starts[0]]) if starts else section
    atomic = not starts or any(
        line.startswith((
            b"new file mode ", b"deleted file mode ", b"old mode ",
            b"new mode ", b"rename from ", b"rename to ",
            b"copy from ", b"copy to ", b"GIT binary patch",
            b"Binary files ",
        ))
        for line in lines
    )
    if atomic:
        return [_make_hunk(path, None, None, section, first_order)]

    hunks = []
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        marker = lines[start]
        # Git's unified hunk header may contain a trailing function name.
        match = re.match(rb"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", marker)
        if match is None:
            raise ValueError("unsupported hunk header in %s: %r" % (path, marker))
        hunks.append(_make_hunk(
            path, int(match.group(1)), int(match.group(2)),
            header + b"".join(lines[start:end]), first_order + len(hunks)
        ))
    return hunks


def _package_distance(path, packages):
    directory = PurePosixPath(path).parent.as_posix()
    if not packages:
        return 0
    if directory in packages:
        return 0
    if any(
        package == "." or directory == "."
        or directory.startswith(package + "/")
        or package.startswith(directory + "/")
        for package in packages
    ):
        return 1
    return 2


def extract_code_hunks(repo_dir, before, fix, *, tested_packages=()):
    """Return stable, ranked code hunks for ``before..fix``.

    Paths ending in ``_test.go`` or containing a ``testdata`` directory are
    omitted.  Hunk IDs are derived from the original patch bytes.  The ranking
    puts code in tested packages first and then tries smaller changes first.
    ``before`` and ``fix`` should identify immutable commits.
    """
    flags = [
        "--no-ext-diff", "--no-textconv", "--no-renames", "--no-color",
        "--src-prefix=a/", "--dst-prefix=b/", "--binary", "--full-index",
        "-U0",
    ]
    paths = _git(repo_dir, "diff", *flags, "--name-only", "-z", before, fix, "--")
    names = [os.fsdecode(path) for path in paths.split(b"\0") if path]
    diff = _git(repo_dir, "diff", *flags, before, fix, "--")
    sections = _sections(diff)
    if len(sections) != len(names):
        raise ValueError(
            "Git diff listed %d paths but produced %d patches"
            % (len(names), len(sections))
        )
    packages = {
        str(package).removeprefix("./").rstrip("/") or "."
        for package in tested_packages
    }
    hunks = []
    for path, section in zip(names, sections):
        if path.endswith("_test.go") or "testdata" in PurePosixPath(path).parts:
            continue
        file_hunks = _file_hunks(path, section, len(hunks))
        hunks.extend(file_hunks)
    return sorted(
        hunks,
        key=lambda hunk: (
            _package_distance(hunk.path, packages),
            hunk.changed_lines,
            hunk.path,
            hunk.new_start if hunk.new_start is not None else -1,
            hunk.id,
        ),
    )


def candidate_sets(hunks):
    """Yield singles, all pairs, then the whole set, without duplicates."""
    hunks = tuple(hunks)
    for hunk in hunks:
        yield (hunk,)
    for pair in itertools.combinations(hunks, 2):
        yield pair
    if len(hunks) > 2:
        yield hunks


def render_patch(selected_hunks):
    """Combine selected hunks into a valid Git patch in original file order."""
    selected = tuple(selected_hunks)
    if not selected:
        raise ValueError("at least one code hunk must be selected")
    ids = [hunk.id for hunk in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("a code hunk was selected more than once")
    by_path = {}
    for hunk in sorted(selected, key=lambda item: item.order):
        by_path.setdefault(hunk.path, []).append(hunk)
    parts = []
    for path, file_hunks in by_path.items():
        atomic = [hunk for hunk in file_hunks if hunk.old_start is None]
        if atomic:
            if len(file_hunks) != 1:
                raise ValueError("atomic file patch cannot be combined: %s" % path)
            parts.append(atomic[0].patch)
            continue
        file_hunks.sort(key=lambda hunk: hunk.new_start)
        first_lines = file_hunks[0].patch.splitlines(keepends=True)
        first_marker = next(i for i, line in enumerate(first_lines) if line.startswith(b"@@ "))
        parts.append(b"".join(first_lines[:first_marker]))
        for hunk in file_hunks:
            lines = hunk.patch.splitlines(keepends=True)
            marker = next(i for i, line in enumerate(lines) if line.startswith(b"@@ "))
            parts.append(b"".join(lines[marker:]))
    return b"".join(parts)


def apply_reverse(repo_dir, selected_hunks):
    """Check and reverse-apply selected code hunks to the worktree.

    Returns ``(applied, diagnostic)``.  A failed check leaves the tree intact.
    A failed apply reports Git's diagnostic; callers should reset the checkout
    before another attempt.  Git/process launch errors propagate.
    """
    patch = render_patch(selected_hunks)
    command = ["git", "-C", os.fspath(repo_dir), "apply", "--reverse", "--unidiff-zero"]
    check = subprocess.run(
        command + ["--check"], input=patch, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if check.returncode:
        return False, (check.stderr or check.stdout).decode("utf-8", "replace").strip()
    applied = subprocess.run(
        command, input=patch, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return applied.returncode == 0, (
        (applied.stderr or applied.stdout).decode("utf-8", "replace").strip()
    )
