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
    d2 = tempfile.mkdtemp(prefix="docket-lead-")
    try:
        _main(d)
        goal_as_aim(d2)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)
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
    for _ in range(4):  # nor are background-task notices or a loop resending the same prompt
        hook(d, "UserPromptSubmit", "sB", prompt="<task-notification><summary>job done</summary></task-notification>")
        hook(d, "UserPromptSubmit", "sB", prompt="Session sweep (every 20 min): check mail")
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

    # the steward is bookkeeping, not a working session
    docket.emit(d, sid="steward", kind="msg", to=["sB"], msgKind="fyi", title="Tidy duty", body="x")
    code, out = run(["who"], d, session="sB")
    check("who doesn't list the steward as a live session", "Docket steward" not in out and "sA" in out, out)
    st = docket.load_state(d)
    check("nor does anything counting live sessions", docket.latest_session(st) != "steward"
          and not docket.is_live(st["sessions"]["steward"]))

    # the hub hands the lead to a coordinating session
    hook(d, "SessionStart", "sCoord1", source="startup")
    run(["name", "Lead: TS/JS coverage"], d, session="sCoord1")
    code, out = run(["lead", "Lead: TS/JS coverage"], d, session="sB")
    check("only the hub or the lead names a coordinator", code != 0 and "is the lead" in out, out)
    code, out = run(["lead", "Lead: TS/JS coverage"], d, session="sA")
    check("the hub names a coordinating lead and gets the hub note",
          code == 0 and "coordinates this project" in out and "You are the lead" not in out, out[-400:])
    st = docket.load_state(d)
    check("the coordinator is the lead while it's live", docket.lead_of(st) == "sCoord1", docket.lead_of(st))
    ctx = hook(d, "UserPromptSubmit", "sCoord1", prompt="go")
    check("the coordinator gets the lead charter", "You are the lead" in ctx, ctx[-300:])
    ctx = hook(d, "UserPromptSubmit", "sC", prompt="next")
    check("members are told who leads", "Lead: TS/JS coverage leads this project" in ctx, ctx[-300:])
    hook(d, "SessionEnd", "sCoord1", reason="exit")
    st = docket.load_state(d)
    check("when it ends the lead falls back to the hub", docket.lead_of(st) == docket.hub_of(st) == "sA", docket.lead_of(st))

    # how often idle sessions are nudged
    code, out = run(["idle", "5"], d, session="sA")
    check("the idle interval can be set", code == 0 and "5 min" in out and docket.load_state(d)["idleMin"] == 5, out)

    check("'I wrote no files' is not a claim of changed code", not docket.CLAIMS_DONE.search("I wrote no repo files"))
    check("'I wrote the parser' still is", bool(docket.CLAIMS_DONE.search("I wrote the parser")))

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json")))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json")))
    before.pop("index", None); after.pop("index", None)
    check("rebuild reproduces the aim and the user's prompt counts", before == after)


def goal_as_aim(d):
    """With no aim recorded, the user's standing goal is the confirmed aim: no separate aim step."""
    for p in ("make the parsers precise and fast please", "and keep the tests green", "go on"):
        hook(d, "UserPromptSubmit", "sH", prompt=p)
    code, out = run(["goal", "set", "make the parsers precise and fast"], d, "sH")
    check("goal set", code == 0, out)
    ctx = hook(d, "UserPromptSubmit", "sH", prompt="status?")
    check("the lead sees the goal as the confirmed aim, not 'start at step 1'",
          "You are the lead" in ctx and "standing goal, their own words" in ctx and "start at step 1" not in ctx, ctx[-500:])


if __name__ == "__main__":
    sys.exit(main())
