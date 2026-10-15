# Advisories assert. This proves.

### Verifying every high/critical Go vulnerability in OSV — at scale, for the price of lunch

*Draft for imdadm.substack.com — your voice, edit freely. [Notes to you in brackets.]*

---

## The itch

It started with what a security advisory **doesn't** tell you.

When a CVE lands, you get one fact — that something was fixed — and almost
nothing else. Not what the vulnerability actually was. Not what would happen if
you hadn't patched. The advisory points at a repository and a version and leaves
you to fill in the rest.

Researchers do fill it in, by hand. You take the patched version, diff it against
the vulnerable one, and read the change backwards: what the fix added is what was
missing, and what was missing is the bug. I wanted to know if the useful part of
that — understanding a vulnerability and confirming it's real — could be done not
one CVE at a time, but across a whole ecosystem.

## What the advisory really gives you

So I pointed a tool at OSV, the open vulnerability database, and at the projects
it references. For a given advisory it takes the OSV link, finds the fix, and
tries to reproduce the bug — to confirm this isn't just a line in a database but
a real, demonstrable flaw.

The first thing I ran into wasn't drama, it was ambiguity. You run the tool
against a vulnerability id and the record hands back not one answer but several:
a fixed version, and a handful of reference links — a pull request here, a commit
there, an advisory page. Which link is the change that actually fixed the bug?
It isn't labelled. Some are release notes. Some point at the merge, not the fix.
Before I could reproduce anything, the tool had to choose the right one: fetch
each candidate, discard the release and version-bump commits, and prefer the
change a human actually pointed to.

That's worth saying plainly, because it's the quiet problem underneath all of
this: **an advisory is a set of assertions, not evidence.** It asserts a version
is fixed. It asserts some links are relevant. It never shows you the bug.

## Turning an assertion into evidence

Here's the idea the whole thing rests on, and it needs no AI and no exploit.

A security fix almost always ships with a test — the developer's own proof that
the bug is gone. So instead of trusting the advisory, follow it to that test and
run it twice:

- run the fix's test on the code **just before** the fix — it should **fail**,
- run it on the **fixed** code — it should **pass**.

Fail before, pass after. That single transition is the proof: the bug was real,
and this change is what fixed it. A crash, a failed assertion, a timeout — any of
them counts as the bug showing itself. Nothing is sent to a live system; the
developer's own test runs in a throwaway container.

At a whiteboard I'd explain it like this. You point the tool at a Go
vulnerability, and it reads the fix — the patch, the diff between the vulnerable
and the patched version. Then it does the obvious thing almost nobody does
automatically: it takes the test that came with the fix and runs that same test
against the old, unpatched code.

If the bug is real, that test fails on the old code — it was written to catch
exactly this flaw. Then the tool runs it again on the patched code, and it
passes. Fail on the old, pass on the new. That's the whole argument. The tool
doesn't take anyone's word that the vulnerability existed; it makes the
vulnerability show itself, and then watches the fix shut it down.

## At scale, for $9

A method is only interesting if it runs across an ecosystem, not a handful. So I
ran it against **every high and critical Go vulnerability in OSV that has a
GitHub fix — 1,525 of them** — on one rented 16-core server. For each one the
tool clones the project, builds it with the Go version that was current on the
fix date, works out the true vulnerable-versus-patched boundary, and runs the
test on both sides.

The run took about a day and cost roughly **$9**.

**[N] vulnerabilities came back proven** — the bug demonstrably present before
the fix and gone after it — with a reproducible test attached to each. For
context, the largest hand-built collections of reproduced vulnerabilities are 79
(Java) and 100 (Python), assembled by researchers over months. This is an
ecosystem, in a day, for the price of lunch.

[NUMBER PENDING — fill when the run finishes. Baseline method proved 369. A
second technique (partial revert: start from the fixed code and undo only the
fix, for the cases whose test needs code the fix added) is still running and was
at ~432 and climbing when this draft was written. Use the final figure here, and
state both: how many via "run the fix's own test" and how many via partial
revert.]

## Why this matters, honestly

OSV will tell you a Go package is fixed in version X. In my checks its *version*
data is mostly right — so this is not a story about the database being wrong.
It's a story about what the database can't give you: **proof.** "Fixed in X" is
an assertion. A test that fails on the vulnerable version and passes on the
patched one is evidence — the kind you can hand an auditor, pin into CI as a
regression guard, or run against your own forked or backported copy where a
version number can quietly lie.

That's the shift: from *trusting* that a vulnerability was real and is now fixed,
to *showing* it — automatically, at the scale of every advisory, not one
researcher reading one diff.

## What I didn't prove (because it matters)

- About 4 in 10 of these fixes shipped **no test**. Without a test there's
  nothing to run — this method can't prove those. (A generated test is a later
  step, and even then a plain test run stays the judge.)
- "Not proven" never means "safe." It means not shown here — and every
  unproven case is logged with the specific reason.
- A proof shows the bug is real **in the library**. Whether it's reachable in
  *your* deployment is a separate question — that's reachability analysis, not
  this.

## Dual-use: what I am and am not releasing

A tool that confirms vulnerabilities is worth threat-modelling honestly. So here
is what it does and doesn't hand a motivated attacker.

It does **not** produce a working exploit. It proves a bug exists inside a
library function; it does not reach that function through an application's
external interface, and it does not tell you whether a given deployment is
exploitable. Everything it reads — the advisory, the patch, the test — is
already public.

What it does offer, to attacker and defender alike, is **triage at scale**:
which advisories are genuinely real, and which commit is the actual fix. That
work is now cheap. And each proven case comes with a minimal reproducer, which
is a starting point — not an exploit, but the first rung toward one.

That shapes what I publish. The **method and the aggregate numbers** carry no
real uplift; they are analysis of public data. A **turnkey bundle of hundreds of
per-vulnerability reproducers** would — so I am not releasing that. The post
shows the method, the totals, and a few long-public illustrative cases. The
tool stays scoped to confirming a bug is real, in a lab container, using the
developer's own test — never to reaching it on someone's live system. Stating
that boundary is the point, not a disclaimer.

## What's next

- Generate a test, with an LLM, for the no-test cases — judged by the same
  fail-before/pass-after run, never by the model's opinion.
- Map a proven library bug to whether it's reachable in a given codebase.
- Extend past Go.

## The takeaway

The point is small and, I think, durable. A security advisory tells you a bug
was fixed. It doesn't show you. For every high and critical Go vulnerability in
OSV with a fix, I stopped trusting that claim and checked it — by running each
fix's own test on the code before and after — and [N] of them proved real,
automatically, for about $9. Not because the database was wrong, but because an
assertion and a piece of evidence are different things, and at the scale security
teams actually operate, you can now afford the evidence. The leftover work — the
fixes with no test, reachability in your own code — is honest and bounded. But
the core holds: proof beats trust, and proof is no longer expensive.

[Tool and method — not the full reproducer bundle — at: your repo link. Keep it
aggregate; no single-vendor call-outs.]

---

*[Pre-publish checklist:*
- *You can explain in your own words: OSV, fix commit vs fixed version, fail-before/pass-after, reachability. I'll quiz you.*
- *Employer publishing policy checked.*
- *No Oracle / Java / MySQL examples.*
- *Every number traces to a file in the repo (1,525; 364; the $9 run).*
- *Dropped: the "10% wrong commit" claim — it's a Git-range finding, not a Go one. Save it for a separate post.]*
