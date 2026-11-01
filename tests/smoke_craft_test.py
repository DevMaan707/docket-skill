#!/usr/bin/env python3
"""Smoke test for docket's engineering-discipline pieces: hypotheses and the project constitution.

    python3 tests/smoke_craft_test.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

REFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")


def main():
    d = tempfile.mkdtemp(prefix="docket-craft-")
    try:
        for f in ("debugging.md", "verification.md", "review-checklist.md", "premise-check.md"):
            t = open(os.path.join(REFS, f), encoding="utf-8").read()
            check("reference %s carries its MIT attribution" % f, "MIT License" in t and "Adapted for docket" in t)

        # hypotheses: logged open, settled by superseding, shown on the page and to the next session
        hook(d, "UserPromptSubmit", "sA", prompt="Debug the flaky login timeout in the auth tests")
        run(["work", "new", "Flaky login timeout in auth tests", "-k", "flaky,login,timeout,auth"], d, "sA")
        _, out = run(["log", "hypothesis", "DNS lookup stalls the login request"], d, "sA")
        hid = out.split()[2]
        run(["log", "hypothesis", "Connection pool too small under parallel tests"], d, "sA")
        code, out = run(["log", "hypothesis", "DNS lookup stalls the login request", "--refuted"], d, "sA")
        check("a settled hypothesis needs evidence", code != 0, out)
        code, out = run(["log", "hypothesis", "DNS lookup stalls the login request", "--supersedes", hid,
                         "--refuted", "--evidence", "strace: no getaddrinfo during the stall"], d, "sA")
        check("a hypothesis is refuted with evidence", code == 0, out)
        page = open(os.path.join(d, ".docket", "work", "W-0001.md"), encoding="utf-8").read()
        check("the work page lists hypotheses, refuted ones struck through with evidence",
              "## Hypotheses" in page and "[REFUTED] ~~DNS lookup stalls the login request~~" in page
              and "no getaddrinfo" in page and "[OPEN] Connection pool too small" in page, page)
        check("the superseded open version isn't listed as a hypothesis",
              page.split("## Hypotheses")[1].split("##")[0].count("DNS lookup") == 1, page)
        hook(d, "SessionEnd", "sA", reason="exit")
        ctx = hook(d, "UserPromptSubmit", "sB", prompt="the auth login test times out again, flaky")
        check("prior work shows refuted and open hypotheses",
              "W-0001" in ctx and "REFUTED" in ctx and "DNS lookup" in ctx and "Connection pool" in ctx, ctx)

        # constitution: only the user's words, numbered, injected at start, reminder when it changes
        code, out = run(["constitution", "add", "Never add a runtime dependency"], d, "sB")
        check("an agent can't add a principle the user didn't say", code != 0 and "Refused" in out, out)
        hook(d, "UserPromptSubmit", "sB", prompt="Add to the constitution: stdlib only, no new dependencies")
        code, out = run(["constitution", "add", "stdlib only, no new dependencies"], d, "sB")
        check("the user's principle is added as C-1", code == 0 and "C-1 added" in out, out)
        hook(d, "UserPromptSubmit", "sB", prompt="Also constitution: every bug fix ships with a failing test first")
        _, out = run(["constitution", "add", "every bug fix ships with a failing test first"], d, "sB")
        check("the next one is C-2", "C-2 added" in out, out)
        ctx = hook(d, "SessionStart", "sC", source="startup")
        check("a new session gets the constitution with its hash",
              '<docket-constitution from="the user" hash=' in ctx and "C-1. stdlib only" in ctx and "C-2." in ctx, ctx)
        ctx = hook(d, "UserPromptSubmit", "sC", prompt="carry on")
        check("no reminder while the constitution is unchanged", "docket-constitution" not in ctx, ctx)
        p = os.path.join(d, ".docket", "constitution.md")
        with open(p, "a", encoding="utf-8") as f:
            f.write("C-3. Hand-written principles count too\n")
        ctx = hook(d, "UserPromptSubmit", "sC", prompt="carry on")
        check("a hand edit gives a one-line reminder", "changed the project constitution" in ctx, ctx)
        ctx = hook(d, "UserPromptSubmit", "sC", prompt="carry on")
        check("the reminder comes once", "docket-constitution" not in ctx, ctx)
        code, out = run(["constitution", "drop", "C-1"], d, "sC")
        check("an agent can't drop a principle", code != 0 and "Refused" in out, out)
        hook(d, "UserPromptSubmit", "sC", prompt="drop C-1 from the constitution")
        code, out = run(["constitution", "drop", "C-1"], d, "sC")
        t = open(p, encoding="utf-8").read()
        check("the user drops C-1; the others keep their numbers",
              code == 0 and "C-1." not in t and "C-2. every bug fix" in t and "C-3." in t, out + t)

        before = open(os.path.join(d, ".docket", "state.json"), encoding="utf-8").read()
        run(["rebuild"], d)
        after = open(os.path.join(d, ".docket", "state.json"), encoding="utf-8").read()
        a, b = json.loads(before), json.loads(after)
        a.pop("index", None); b.pop("index", None)
        check("rebuild reproduces state", a == b)
        print("\n%s" % ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
