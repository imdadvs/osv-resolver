"""Run and resume Pile A cases from the saved reproduction results.

Usage: python3 -I run_pile_a.py WORKDIR OUT_JSONL [--id GO-2026-6372]
"""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


FIX_LINK = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/(commit|pull)/([0-9a-fA-F]+|\d+)(?:[/?#].*)?$")
RETRYABLE = {"search_incomplete", "timeout", "script_error"}


def enriched_result(source, outcome):
    metadata = {key: source[key] for key in ("id", "severity", "fix_status", "fix_commit", "confidence", "repo")
                if key in source}
    return {**metadata, **outcome, "id": source["id"], "source_verdict": source.get("verdict"), "source_result": source}


def read_jsonl(path, recover=False):
    if not path.exists():
        return []
    rows, offset = [], 0
    lines = path.read_bytes().splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            offset += len(line)
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            if recover and index == len(lines) - 1 and not line.endswith(b"\n"):
                with path.open("r+b") as fh:
                    fh.truncate(offset)
                break
            raise
        offset += len(line)
    return rows


def run_case(command, timeout):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return {"verdict": "timeout", "err": (stderr or stdout)[-1000:]}
    last = (stdout.strip().splitlines() or [""])[-1]
    try:
        result = json.loads(last)
        if not isinstance(result, dict) or "verdict" not in result:
            raise ValueError("missing verdict")
    except ValueError:
        return {"verdict": "script_error", "err": (stderr or stdout)[-1000:], "returncode": process.returncode}
    if process.returncode:
        return {"verdict": "script_error", "err": (stderr or stdout)[-1000:], "returncode": process.returncode}
    return result


def main(argv=None):
    tools_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--input", type=Path, default=tools_dir.parent / "results" / "go-critical-high.jsonl")
    parser.add_argument("--reasons", type=Path, default=tools_dir.parent / "results" / "failure_reasons.json")
    parser.add_argument("--id", action="append", dest="ids", help="run only this advisory (repeatable)")
    parser.add_argument("--max-attempts", type=int, default=25, help="new candidates per harness invocation")
    parser.add_argument("--case-budget", type=int, help="maximum new candidates per case during this batch run")
    parser.add_argument("--case-timeout", type=float, default=7200, help="seconds per harness invocation")
    args = parser.parse_args(argv)
    if args.max_attempts < 1 or (args.case_budget is not None and args.case_budget < 1) or args.case_timeout <= 0:
        parser.error("attempt budgets and timeout must be positive")
    args.workdir = args.workdir.resolve()
    args.workdir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reasons = json.loads(args.reasons.read_text())
    selected = {row["id"] for row in reasons if row.get("reason") == "symbol_from_fix_missing"}
    if args.ids:
        selected &= set(args.ids)
    latest = {row["id"]: row for row in read_jsonl(args.output, recover=True)}
    for source in read_jsonl(args.input):
        vid = source["id"]
        if vid not in selected or (vid in latest and latest[vid].get("verdict") not in RETRYABLE):
            continue
        match = FIX_LINK.match(source.get("fix_commit", ""))
        if not match:
            result = enriched_result(source, {"verdict": "stale_input",
                                             "err": "saved fix_commit is not a GitHub commit or pull URL"})
            with args.output.open("a") as fh:
                fh.write(json.dumps(result) + "\n")
            continue
        repo = f"https://github.com/{match[1]}/{match[2]}"
        base_command = [sys.executable, "-I", str(tools_dir / "gorepro.py"), str(args.workdir), vid,
                        repo, match[4], "--pile-a"]
        if source.get("fix_sha"):
            base_command += ["--expected-fix-sha", source["fix_sha"]]
        if source.get("before"):
            base_command += ["--expected-before", source["before"]]
        if source.get("go_image"):
            base_command += ["--go-image", source["go_image"]]
        spent = 0
        previous_attempts = latest.get(vid, {}).get("attempts", 0)
        previous_completed = latest.get(vid, {}).get("completed_candidates", previous_attempts)
        while True:
            allowance = args.max_attempts
            if args.case_budget is not None:
                allowance = min(allowance, args.case_budget - spent)
            if allowance <= 0:
                break
            outcome = run_case(base_command + ["--max-attempts", str(allowance)], args.case_timeout)
            expected = source.get("fix_sha")
            if expected and outcome.get("fix_sha") and not outcome["fix_sha"].startswith(expected):
                outcome = {**outcome, "verdict": "stale_input", "expected_fix_sha": expected}
            result = enriched_result(source, outcome)
            with args.output.open("a") as fh:
                fh.write(json.dumps(result) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            latest[vid] = result
            print(vid, result["verdict"], "attempts=" + str(result.get("attempts", 0)), flush=True)
            completed = result.get("attempts", previous_attempts)
            added = result.get("new_attempts", max(0, completed - previous_attempts))
            spent += added
            previous_attempts = completed
            completed_candidates = result.get("completed_candidates", completed)
            progress = completed_candidates - previous_completed
            previous_completed = completed_candidates
            if result["verdict"] != "search_incomplete" or added == 0 or progress <= 0:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
