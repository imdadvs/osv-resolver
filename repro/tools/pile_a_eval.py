"""Interpret structured Go test output for partial-revert experiments."""

import json
import re


BUILD_ERROR = re.compile(
    r"\[build failed\]|\[setup failed\]|undefined: |cannot find package|"
    r"could not import|has no field or method|not enough arguments in call|"
    r"errors parsing go\.mod|no required module provides package"
)


def parse_go_json(text):
    """Return package-level events from `go test -json` output."""
    packages = {}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or "Action" not in event or "Package" not in event:
            continue
        pkg = event["Package"]
        entry = packages.setdefault(pkg, {
            "state": "unknown", "run": set(), "passed": set(), "failed": set(),
            "active": set(), "panic_tests": set(), "output": [],
        })
        action, test = event["Action"], event.get("Test")
        if action == "output":
            output = event.get("Output", "")
            entry["output"].append(output)
            if test and "panic: " in output:
                entry["panic_tests"].add(test)
        elif test:
            if action == "run":
                entry["run"].add(test)
                entry["active"].add(test)
            elif action in ("pass", "fail", "skip"):
                entry["active"].discard(test)
                if action == "pass":
                    entry["passed"].add(test)
                elif action == "fail":
                    entry["failed"].add(test)
        elif action in ("pass", "fail"):
            entry["state"] = action
    for entry in packages.values():
        output = "".join(entry["output"])
        entry["output"] = output
        if re.search(r"\[build failed\]|\[setup failed\]", output) or (not entry["run"] and BUILD_ERROR.search(output)):
            entry["state"] = "build"
        elif entry["state"] == "pass" and not entry["passed"]:
            entry["state"] = "no_tests_ran"
    return packages


def summarize(modules, packages):
    """Summarize a multi-module run while preserving each package's result."""
    if any(module["returncode"] == 124 for module in modules):
        return "external_timeout"
    if any(module["returncode"] not in (0, 1) for module in modules):
        return "error"
    if any(package["state"] == "build" for package in packages.values()):
        return "build_failed"
    for module in modules:
        parsed = module.get("packages", packages if len(modules) == 1 else {})
        if module["returncode"] and not any(package["run"] for package in parsed.values()):
            return "build_failed" if BUILD_ERROR.search(module.get("output", "")) else "error"
        if module["returncode"] and not any(package["state"] == "fail" for package in parsed.values()):
            return "error"
    if any(package["state"] == "fail" for package in packages.values()):
        return "fail"
    if all(module["returncode"] == 0 for module in modules) and packages \
            and all(package["state"] == "pass" for package in packages.values()) \
            and any(package["run"] for package in packages.values()):
        return "pass"
    if all(module["returncode"] == 0 for module in modules) and packages \
            and all(package["state"] in ("pass", "no_tests_ran") for package in packages.values()):
        return "no_tests_ran"
    return "error"


def matches_target(name, targets):
    # Testify suite methods appear as TestSuite/TestMethod in Go's events.
    return any(component in targets for component in name.split("/"))


def proof_from_candidate(fixed_run, candidate_run, targets_by_package):
    """Accept only a changed developer test failing in its own package."""
    if candidate_run["state"] != "fail":
        return None
    if [module.get("command") for module in fixed_run.get("modules", [])] \
            != [module.get("command") for module in candidate_run.get("modules", [])]:
        return None
    for pkg, candidate in candidate_run["packages"].items():
        baseline = fixed_run["packages"].get(pkg)
        targets = targets_by_package.get(pkg, set())
        if not baseline or baseline["state"] != "pass" or candidate["state"] != "fail" or not targets:
            continue
        passed_targets = [test for test in baseline["passed"] if matches_target(test, targets)]
        if not passed_targets:
            continue
        def passed_before(test):
            return any(test == passed or test.startswith(passed + "/") for passed in passed_targets)

        failed = sorted(test for test in candidate["failed"] if matches_target(test, targets) and passed_before(test))
        if failed:
            return {"package": pkg, "failed_tests": failed, "failure_kind": "test_failure"}
        active = sorted(test for test in candidate["active"] if matches_target(test, targets) and passed_before(test))
        unrelated_active = [test for test in candidate["active"] if not matches_target(test, targets)
                            and not any(target.startswith(test + "/") for target in active)]
        output = candidate["output"]
        if active and not unrelated_active and "panic: test timed out" in output:
            return {"package": pkg, "failed_tests": active, "failure_kind": "test_timeout"}
        panic_targets = sorted(test for test in candidate.get("panic_tests", ())
                               if matches_target(test, targets) and passed_before(test))
        if re.search(r"(?m)^panic: ", output) and (panic_targets or (active and not unrelated_active)):
            if "panic: test timed out" in output:
                continue
            return {"package": pkg, "failed_tests": panic_targets or active, "failure_kind": "panic"}
    return None


def needs_new_symbol(run):
    """Whether a failed compile specifically names an API absent from old code."""
    if run["state"] != "build_failed":
        return False
    outputs = [package["output"] for package in run["packages"].values()]
    outputs += [module.get("output", "") for module in run.get("modules", [])]
    return any(re.search(r"undefined: |has no field or method|not enough arguments in call", output)
               for output in outputs)
