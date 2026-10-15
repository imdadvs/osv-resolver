import json

from repro.tools import run_pile_a


def inputs(tmp_path):
    source = {"id": "GO-TEST-1", "verdict": "inconclusive_build", "fix_sha": "a" * 12,
              "before": "b" * 12, "go_image": "golang:1.25", "severity": "HIGH",
              "fix_commit": "https://github.com/example/demo/commit/" + "a" * 40}
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(json.dumps(source) + "\n")
    reasons = tmp_path / "reasons.json"
    reasons.write_text(json.dumps([{"id": source["id"], "reason": "symbol_from_fix_missing"}]))
    return source_path, reasons, tmp_path / "output.jsonl"


def test_batch_resumes_search_and_skips_final_results(tmp_path, monkeypatch):
    source, reasons, output = inputs(tmp_path)
    outcomes = iter([
        {"verdict": "search_incomplete", "attempts": 1, "new_attempts": 1, "completed_candidates": 1,
         "fix_sha": "a" * 40},
        {"verdict": "reproduced", "attempts": 2, "new_attempts": 1, "fix_sha": "a" * 40},
    ])
    commands = []

    def fake_run(command, timeout):
        commands.append(command)
        return next(outcomes)

    monkeypatch.setattr(run_pile_a, "run_case", fake_run)
    args = [str(tmp_path / "work"), str(output), "--input", str(source), "--reasons", str(reasons)]
    assert run_pile_a.main(args) == 0
    assert len(commands) == 2
    assert "--expected-fix-sha" in commands[0] and "--expected-before" in commands[0]
    assert "--go-image" in commands[0]
    rows = run_pile_a.read_jsonl(output)
    assert rows[-1]["verdict"] == "reproduced"
    assert rows[-1]["source_verdict"] == "inconclusive_build"
    assert run_pile_a.main(args) == 0
    assert len(commands) == 2


def test_budget_and_unresolved_attempts_remain_resumable(tmp_path, monkeypatch):
    source, reasons, output = inputs(tmp_path)
    calls = []

    def fake_run(command, timeout):
        calls.append(command)
        return {"verdict": "search_incomplete", "attempts": 1, "new_attempts": 1,
                "completed_candidates": 0, "reason": "unresolved_attempts", "fix_sha": "a" * 40}

    monkeypatch.setattr(run_pile_a, "run_case", fake_run)
    args = [str(tmp_path / "work"), str(output), "--input", str(source), "--reasons", str(reasons),
            "--case-budget", "1"]
    run_pile_a.main(args)
    assert len(calls) == 1
    run_pile_a.main(args)
    assert len(calls) == 2
    assert run_pile_a.read_jsonl(output)[-1]["verdict"] == "search_incomplete"


def test_output_recovers_only_an_interrupted_final_append(tmp_path):
    path = tmp_path / "output.jsonl"
    path.write_bytes(b'{"id":"first"}\n{"id":')
    assert run_pile_a.read_jsonl(path, recover=True) == [{"id": "first"}]
    assert path.read_bytes() == b'{"id":"first"}\n'
