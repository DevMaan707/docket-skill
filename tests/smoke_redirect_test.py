#!/usr/bin/env python3
"""A user's redirect must win: directives newest first and dated, a newer one overrides older ones and the goal,
the session that received it is told to offer retiring the old ones, and "retire" counts as the user's drop.

    python3 tests/smoke_redirect_test.py
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402


def main():
    d = os.path.realpath(tempfile.mkdtemp(prefix="docket-redirect-"))
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    os.makedirs(os.path.join(d, ".docket"))
    hook(d, "SessionStart", "sU", source="startup")
    hook(d, "UserPromptSubmit", "sU", prompt="fix every engine false positive in TS and JS")
    run(["goal", "set", "fix every engine false positive in TS and JS"], d, "sU")
    hook(d, "UserPromptSubmit", "sU", prompt="@all make TS JS 90% then move to Go")
    time.sleep(1.1)
    ctx = hook(d, "UserPromptSubmit", "sU", prompt="@all deterministic candidates first, then AI classifies them; stop engine FP patches")
    check("the session that got the redirect is told to offer retiring older ones and list affected work",
          "Retire these directives?" in ctx and "override older directives and the goal" in ctx, ctx[-900:])
    st = docket.load_state(d)
    old, new = sorted(docket.directives(st), key=lambda x: x["ts"])
    block = docket.directives_block(st)
    check("directives are newest first, dated, and say the newer one wins",
          block.index("deterministic candidates") < block.index("TS JS 90%") and "NEWER one wins" in block
          and ("(just now)" in block or " ago)" in block), block)
    g = docket.goal_block(st)
    check("the goal says which later directives override it", "override it where they conflict" in g
          and new["id"][:6] in g and old["id"][:6] in g, g)
    code, out = run(["directive", "drop", old["id"][:6]], d, "sU")
    check("without the user's words, no drop", code != 0, out)
    hook(d, "UserPromptSubmit", "sU", prompt="yes, retire those old directives")
    code, out = run(["directive", "drop", old["id"][:6]], d, "sU")
    check("'retire those directives' counts as the user's drop", code == 0 and "dropped" in out, out)
    check("charter tells the lead a redirect is a re-plan", "re-plan, not an addition" in docket.LEAD_CHARTER)


if __name__ == "__main__":
    sys.exit(main())
