"""Proof attribution must distinguish developer tests from setup failures."""

import json

from repro.tools.pile_a_eval import needs_new_symbol, parse_go_json, proof_from_candidate, summarize


PKG = "example.test/project"
COMMAND = ["go", "test", "-json", "-run", "TestSecurity"]


def events(*items):
    return "\n".join(json.dumps({"Package": PKG, **item}) for item in items)


def report(text, returncode=0, command=COMMAND):
    packages = parse_go_json(text)
    modules = [{"returncode": returncode, "command": command, "output": text, "packages": packages}]
    return {"state": summarize(modules, packages), "packages": packages, "modules": modules}


def passed(test="TestSecurity"):
    return report(events({"Action": "run", "Test": test}, {"Action": "pass", "Test": test}, {"Action": "pass"}))


def failed(test="TestSecurity"):
    return report(events({"Action": "run", "Test": test}, {"Action": "fail", "Test": test}, {"Action": "fail"}), 1)


def test_selected_developer_test_is_proof_but_unrelated_test_is_not():
    targets = {PKG: {"TestSecurity"}}
    proof = proof_from_candidate(passed(), failed(), targets)
    assert proof["failed_tests"] == ["TestSecurity"]
    assert proof_from_candidate(passed(), failed("TestOther"), targets) is None
    assert proof_from_candidate(passed(), failed(), {"example.test/sibling": {"TestSecurity"}}) is None


def test_changed_suite_method_matches_subtest_events():
    targets = {PKG: {"TestSecurity"}}
    proof = proof_from_candidate(passed("TestSuite/TestSecurity"), failed("TestSuite/TestSecurity"), targets)
    assert proof["failed_tests"] == ["TestSuite/TestSecurity"]


def test_build_failure_in_another_module_prevents_proof():
    candidate = failed()
    candidate["modules"].append({"returncode": 1, "command": COMMAND, "packages": {},
                                  "output": "go: errors parsing go.mod: invalid go version"})
    candidate["state"] = summarize(candidate["modules"], candidate["packages"])
    assert candidate["state"] == "build_failed"
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}}) is None


def test_external_timeout_and_changed_test_command_are_not_proof():
    candidate = failed()
    candidate["modules"][0]["returncode"] = 124
    candidate["state"] = summarize(candidate["modules"], candidate["packages"])
    assert candidate["state"] == "external_timeout"
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}}) is None
    candidate = failed()
    candidate["modules"][0]["command"] = ["go", "test", "-run", "."]
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}}) is None


def test_panic_requires_test_attribution():
    candidate = report(events({"Action": "run", "Test": "TestSecurity"},
                              {"Action": "run", "Test": "TestOther"},
                              {"Action": "output", "Output": "panic: broken\n"}, {"Action": "fail"}), 1)
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}}) is None
    candidate = report(events({"Action": "run", "Test": "TestSecurity"},
                              {"Action": "output", "Test": "TestSecurity", "Output": "panic: broken\n"},
                              {"Action": "fail"}), 1)
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}})["failure_kind"] == "panic"


def test_internal_test_timeout_is_distinct_from_external_timeout():
    candidate = report(events({"Action": "run", "Test": "TestSecurity"},
                              {"Action": "output", "Output": "panic: test timed out after 10m0s\n"},
                              {"Action": "fail"}), 1)
    assert proof_from_candidate(passed(), candidate, {PKG: {"TestSecurity"}})["failure_kind"] == "test_timeout"


def test_no_tests_and_missing_api_are_not_a_test_pass_or_failure():
    empty = report(events({"Action": "pass"}))
    assert empty["state"] == "no_tests_ran"
    build = report(events({"Action": "output", "Output": "undefined: sanitizePath\nFAIL x [build failed]\n"},
                          {"Action": "fail"}), 1)
    assert build["state"] == "build_failed"
    assert needs_new_symbol(build)
    assert proof_from_candidate(passed(), build, {PKG: {"TestSecurity"}}) is None


def test_skipped_fixed_test_cannot_be_used_as_a_passing_baseline():
    baseline = report(events({"Action": "run", "Test": "TestSecurity"},
                             {"Action": "skip", "Test": "TestSecurity"}, {"Action": "pass"}))
    assert baseline["state"] == "no_tests_ran"
    assert proof_from_candidate(baseline, failed(), {PKG: {"TestSecurity"}}) is None


def test_test_output_containing_compiler_words_does_not_become_build_failure():
    candidate = report(events({"Action": "run", "Test": "TestSecurity"},
                              {"Action": "output", "Test": "TestSecurity", "Output": "expected string undefined: x\n"},
                              {"Action": "fail", "Test": "TestSecurity"}, {"Action": "fail"}), 1)
    assert candidate["state"] == "fail"


def test_unexplained_nonzero_module_exit_is_an_error():
    assert report("docker daemon unavailable", 1)["state"] == "error"
    assert report(events({"Action": "run", "Test": "TestSecurity"},
                         {"Action": "pass", "Test": "TestSecurity"}, {"Action": "pass"}), 1)["state"] == "error"
