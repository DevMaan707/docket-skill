#!/usr/bin/env python3
"""Stale needs-you items: the author re-checks after 12 h (withdraw or still); an orphan drops off after 24 h
unless it's about a leak, deletion, cost or the like.

    python3 tests/smoke_stale_test.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402


def main():
    d = os.path.realpath(tempfile.mkdtemp(prefix="docket-stale-"))
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def ids(rows):
    return {n["title"]: n["id"] for n in rows}


def _main(d):
    os.makedirs(os.path.join(d, ".docket"))
    for s in ("sA", "sB"):
        hook(d, "SessionStart", s, source="startup")
    run(["msg", "user", "Which DB for the cache?", "--kind", "ask", "--session", "sA"], d)
    run(["msg", "user", "Possible secret leak in git history", "--kind", "ask", "--session", "sA"], d)
    run(["msg", "user", "Old note nobody needs", "--session", "sB"], d)
    st = docket.load_state(d)
    for m in st["msgs"]:
        m["ts"] -= 30 * 3600
    check("fresh enough or author live: all shown", len(docket.needs_user(st)) == 3)
    check("leak-type items come first", docket.needs_user(st)[0]["title"].startswith("Possible secret leak"))
    nudge = docket.own_stale_needs(st, "sA") or ""
    check("the author is asked to re-check its own old items",
          "Which DB" in nudge and "withdraw" in nudge and "still" in nudge and "Old note" not in nudge, nudge)

    st["sessions"]["sB"]["status"] = "ended"
    st["sessions"]["sA"]["status"] = "ended"
    left = ids(docket.needs_user(st))
    check("an orphan older than 24 h drops off; one about a leak stays",
          set(left) == {"Possible secret leak in git history"}, repr(left))
    check("needs --all still has them", len(docket.needs_user(st, everything=True)) == 3)

    st = docket.load_state(d)
    q = ids(docket.needs_user(st))
    code, out = run(["still", q["Which DB for the cache?"], "--session", "sA"], d)
    check("still restarts the item's age", code == 0 and "still needed" in out
          and [n for n in docket.needs_user(docket.load_state(d)) if n["id"] == q["Which DB for the cache?"]][0]["age"] < 60, out)
    code, out = run(["withdraw", q["Old note nobody needs"], "--reason", "superseded by decision abc", "--session", "sB"], d)
    check("withdraw takes it off", code == 0 and "Old note nobody needs" not in ids(docket.needs_user(docket.load_state(d))), out)
    run(["log", "blocker", "Need the staging password", "--session", "sB"], d)
    b = ids(docket.needs_user(docket.load_state(d)))["Need the staging password"]
    code, out = run(["withdraw", b, "--reason", "got it from the vault", "--session", "sB"], d)
    check("a blocker can be withdrawn too", "Need the staging password" not in ids(docket.needs_user(docket.load_state(d))), out)
    code, out = run(["tidy"], d)
    check("tidy no longer forbids withdrawing a moot question", "moot" in out or "Nothing stale" in out, out)


if __name__ == "__main__":
    sys.exit(main())
