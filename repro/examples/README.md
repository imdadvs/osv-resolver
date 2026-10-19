# Example reproductions

The before/after test logs for the cases discussed in the write-up. Each pair
is one advisory: `.old.log` is the maintainer's test run on the commit *before*
the fix, `.fixed.log` is the same test on the fix. The first line of every log
is the exact `docker run … go test` command, so the run can be repeated.

| Advisory | Project | Class | Fix commit |
|---|---|---|---|
| [GO-2026-6142](https://osv.dev/vulnerability/GO-2026-6142) | Logging Operator | Fluentd config injection → RCE | [cf437d7](https://github.com/kube-logging/logging-operator/commit/cf437d7f1e056c78740bf5716ac8bdebcf002425) |
| [GO-2026-6435](https://osv.dev/vulnerability/GO-2026-6435) | Semaphore UI | OS command injection | [7e8a943](https://github.com/semaphoreui/semaphore/commit/7e8a9434bd81b82cf42220151c74801ea97542d6) |
| [GO-2026-5875](https://osv.dev/vulnerability/GO-2026-5875) | Rancher | Command injection via YAML parameter | [2aa77eb](https://github.com/rancher/rancher/commit/2aa77eb283e7451d605fb85e1bd9b1791cd73875) |

To regenerate any of these from scratch, see the harness usage in the top-level
`README.md`, e.g.:

```bash
python3 -I repro/tools/gorepro.py /tmp/osv-repro \
  GO-2026-6142 https://github.com/kube-logging/logging-operator cf437d7f1e05
```

A failing library test here demonstrates the bug in the library. It does not by
itself establish that a deployed application contains the affected code, accepts
attacker-controlled input, or is exploitable.
