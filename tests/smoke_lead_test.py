#!/usr/bin/env python3
"""Lead and product aim: the lead is the session the user talks to most, gets the product-owner charter,
others get the member charter; the aim is the lead's draft until the user's own words confirm it.

    python3 tests/smoke_lead_test.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-lead-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    for k in ("sA", "sB"):
        hook(d, "SessionStart", k, source="startup")
    hook(d, "UserPromptSubmit", "sB", prompt="look at the parser")
    for p in ("I want a booking app for small clinics", "patients book, staff see the day",
              "yes, that aim is right: ship the clinic booking MVP"):
        ctx = hook(d, "UserPromptSubmit", "sA", prompt=p)
    for i in range(4):  # docket's own wake-ups are not the user talking
        c = hook(d, "UserPromptSubmit", "sB", prompt="[docket] you've been idle 20 min")
        member = c if i == 0 else member
    st = docket.load_state(d)
    check("the lead is the session the user talks to most", docket.lead_of(st) == "sA", docket.lead_of(st))
    check("the lead gets the product-owner charter once it becomes lead", "You are the lead" in ctx, ctx[-400:])
    ctx = hook(d, "UserPromptSubmit", "sA", prompt="carry on")
    check("the charter isn't repeated while nothing changed", "You are the lead" not in ctx)
    check("other sessions get the member charter naming the lead", "leads this project as product owner" in member, member[-400:])

    code, out = run(["aim", "set", "-b", "Outcome: clinic booking MVP\nUsers: small clinics"], d, session="sA")
    check("the lead records the aim as a draft", code == 0 and "DRAFT" in out, out)
    ctx = hook(d, "UserPromptSubmit", "sB", prompt="ok")
    check("a new aim reaches the other sessions as a draft", "DRAFT" in ctx and "clinic booking MVP" in ctx, ctx[-400:])
    code, out = run(["aim", "confirm", "go ahead and build a crypto exchange"], d, session="sA")
    check("an agent can't confirm the aim with words the user didn't type", code != 0 and "Refused" in out, out)
    code, out = run(["aim", "confirm", "yes, that aim is right"], d, session="sA")
    check("the user's own words confirm the aim", code == 0, out)
    check("the aim shows as confirmed", docket.load_state(d)["aim"]["status"] == "confirmed")

    code, out = run(["lead"], d, session="sB")
    check("someone else can't take the lead while the lead is live", code != 0 and "is the lead" in out, out)
    code, out = run(["lane", "take", "lead"], d, session="sB")
    check("nor through lane take", code != 0 and docket.lead_of(docket.load_state(d)) == "sA", out)
    hook(d, "SessionStart", "sC", source="startup")
    code, out = run(["lead"], d, session="sA")
    check("the lead can claim it explicitly, and gets its charter", code == 0 and "You are the lead" in out, out[-300:])

    check("'I wrote no files' is not a claim of changed code", not docket.CLAIMS_DONE.search("I wrote no repo files"))
    check("'I wrote the parser' still is", bool(docket.CLAIMS_DONE.search("I wrote the parser")))

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json")))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json")))
    before.pop("index", None); after.pop("index", None)
    check("rebuild reproduces the aim and the user's prompt counts", before == after)


if __name__ == "__main__":
    sys.exit(main())
