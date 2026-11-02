#!/usr/bin/env python3
"""Pulled work: the lead writes ordered tasks (pending --add --after --lane), sessions claim with `next`.
A blocked task isn't claimable, finishing its blocker frees it, two claims never get the same task,
a lane's own tasks come first, the idle nudge names the task, and rebuild reproduces it all. Stdlib only.

    python3 tests/smoke_next_test.py
"""
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-next-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def add(d, title, *extra):
    _, out = run(["pending", "W-0001", "--add", title] + list(extra), d, "sL")
    return re.search(r"P-[0-9a-f]{6}", out).group(0), out


def claimed(out):
    m = re.search(r"claimed (P-\w+)", out)
    return m and m.group(1)


def _main(d):
    for s in ("sL", "sB", "sC", "sD"):
        hook(d, "SessionStart", s, source="startup")
    run(["work", "new", "Build the parser", "-k", "parser"], d, "sL")
    run(["lane", "take", "Docs", "-b", "the manual"], d, "sC")

    p1, _ = add(d, "Write the tokenizer")
    p2, out = add(d, "Write the parser", "--after", p1)
    check("--after is recorded", "after W-0001/" + p1 in out, out)
    p4, _ = add(d, "Lint the grammar")
    p3, _ = add(d, "Document the syntax", "--lane", "docs")
    code, out = run(["pending", "W-0001", "--add", "x", "--after", "P-zzzzzz"], d, "sL")
    check("--after an unknown task is refused", code != 0 and "No pending task" in out, out)

    _, out = run(["next"], d, "sB")
    check("next claims the oldest free task", claimed(out) == p1 and "resolve " + p1 in out, out)
    _, out = run(["pending", "W-0001"], d, "sB")
    check("pending shows what a task waits on", re.search(r"%s .*after W-0001/%s" % (p2, p1), out) is not None, out)
    _, out = run(["next"], d, "sC")
    check("a lane's own task comes before older ones", claimed(out) == p3, out)
    _, out = run(["next"], d, "sB")
    check("another live lane's task isn't taken; next is the free one", claimed(out) == p4, out)
    _, out = run(["next"], d, "sB")
    check("a blocked task can't be claimed", claimed(out) is None and "Nothing ready" in out, out)

    run(["resolve", p1, "--reason", "tests pass"], d, "sB")
    st = docket.load_state(d)
    check("finishing the blocker frees its dependent", (docket.next_task(st, "sD") or {}).get("pid") == p2)

    # an idle session is told the concrete task, not generic advice (no real socket: wake is stubbed)
    got, real = [], docket.wake
    docket.wake = lambda st_, m, text: got.append((m["to"], text)) or 1
    try:
        st["goal"] = {"status": "active", "autonomous": True, "id": "g", "sid": "sL"}
        st["paused"] = None
        for v in st["sessions"].values():
            v["sock"] = ""
        st["sessions"]["sD"].update(sock="/nonexistent.sock", host=socket.gethostname(), pid=os.getpid(),
                                    status="idle", last=time.time() - 3600, waitUntil=0, entries=[])
        woke = docket.rouse_idle(d, st, {})
    finally:
        docket.wake = real
    check("the idle nudge names the next task and docket next",
          woke == ["sD"] and got and "next for you: %s Write the parser" % p2 in got[0][1] and "next" in got[0][1], repr(got))
    kg = docket.keep_going(dict(st, root=d), "sC") or ""
    check("the Stop hook names it too", "Next for you: %s" % p2 in kg, kg)

    p5, _ = add(d, "Write the error messages")
    outs = {}
    ts = [threading.Thread(target=lambda s=s: outs.__setitem__(s, run(["next"], d, s)[1])) for s in ("sB", "sD")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    got = sorted(claimed(o) for o in outs.values())
    check("two claims at once never get the same task", got == sorted([p2, p5]), repr(outs))

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json")))["work"]["W-0001"]
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json")))["work"]["W-0001"]
    check("rebuild reproduces planned tasks and claims",
          before["planned"] == after["planned"] and before["pending"] == after["pending"] and len(after["planned"]) == 5,
          json.dumps(after.get("planned"))[:400])


if __name__ == "__main__":
    sys.exit(main())
