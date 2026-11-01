#!/usr/bin/env python3
"""Shared work queues: add, next, done, drop, list, the requester hearing the result, a linked ask
closing, two takers never getting the same item, and rebuild reproducing the queues. Stdlib only.

    python3 tests/smoke_queue_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-queue-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    for s in ("sGate", "sA", "sB"):
        hook(d, "SessionStart", s, source="startup")
    run(["name", "gate-owner"], d, "sGate")
    run(["name", "alice"], d, "sA")
    run(["work", "new", "Run the gate", "-k", "gate"], d, "sGate")

    _, out = run(["queue"], d, "sA")
    check("no queues yet", "No queues" in out, out)
    _, out = run(["queue", "gate", "add", "Batch feat/login", "-b", "branch feat/login"], d, "sA")
    check("add queues at position 1", "position 1" in out, out)
    q1 = re.search(r"Q-[0-9a-f]{6}", out).group(0)
    _, out = run(["msg", "gate-owner", "Please run feat/search", "--kind", "ask"], d, "sB")
    ask = re.search(r"sent ask (\w+)", out).group(1)
    _, out = run(["queue", "gate", "add", "Batch feat/search", "--re", ask], d, "sB")
    check("second add is position 2", "position 2" in out, out)
    q2 = re.search(r"Q-[0-9a-f]{6}", out).group(0)
    run(["queue", "gate", "add", "Batch feat/x"], d, "sB")

    _, out = run(["queue", "gate"], d, "sGate")
    check("list shows positions, who added and age",
          "1. %s waiting" % q1 in out and "added by alice" in out and "just now" in out, out)
    _, out = run(["queue"], d, "sGate")
    check("queue with no name lists counts", "gate: 3 waiting, 0 running" in out, out)
    ctx = hook(d, "SessionStart", "sC", source="startup")
    check("SessionStart has one queue line", "Queues: gate (3 waiting, 0 running)" in ctx, ctx[-600:])

    _, out = run(["queue", "gate", "next"], d, "sGate")
    check("next takes the oldest waiting item", "took %s" % q1 in out and "branch feat/login" in out, out)
    _, out = run(["queue", "gate", "done", q1, "--result", "42 passed, 0 failed"], d, "sGate")
    check("done reports and tells the requester", "%s done" % q1 in out and "told alice" in out, out)
    _, out = run(["inbox"], d, "sA")
    check("requester receives the result in its inbox", q1 in out and "42 passed" in out, out)

    # two sessions take concurrently: each gets a different item
    outs = {}
    ts = [threading.Thread(target=lambda s=s: outs.__setitem__(s, run(["queue", "gate", "next"], d, s)[1]))
          for s in ("sGate", "sB")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    took = [re.search(r"took (Q-\w+)", o).group(1) for o in outs.values() if "took" in o]
    check("concurrent next hands out two different items", len(took) == 2 and len(set(took)) == 2, repr(outs))
    _, out = run(["queue", "gate", "next"], d, "sB")
    check("next on an empty queue says so", "Nothing waiting" in out, out)

    _, out = run(["queue", "gate", "done", q2, "--result", "3 failures", "--failed"], d, "sGate")
    check("failed result closes the linked ask's pending task", "%s failed" % q2 in out and "closed pending task A-%s" % ask[:6] in out, out)
    _, out = run(["pending", "W-0001", "--all"], d, "sGate")
    check("the ask's task shows done", re.search(r"A-%s.*done|done.*A-%s" % (ask[:6], ask[:6]), out) is not None, out)
    _, out = run(["queue", "gate", "done", q2, "--result", "again"], d, "sGate")
    check("finishing twice is refused", "already failed" in out, out)
    third = [t for t in took if t not in (q2,)][0]
    _, out = run(["queue", "gate", "drop", third], d, "sGate")
    check("drop needs --reason", "needs --reason" in out, out)
    _, out = run(["queue", "gate", "drop", third, "--reason", "branch deleted"], d, "sGate")
    check("drop works", "%s dropped" % third in out, out)
    _, out = run(["queue", "gate"], d, "sGate")
    check("list shows finished items with results", "42 passed" in out and "3 failures" in out and "dropped" in out, out)

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json")))["queues"]
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json")))["queues"]
    check("rebuild reproduces the queues exactly", before == after and before, json.dumps(before)[:400])

    # stale: an item running for more than a day
    run(["queue", "gate", "add", "Old run"], d, "sA")
    run(["queue", "gate", "next"], d, "sGate")
    st = json.load(open(os.path.join(bd, "state.json")))
    ev = [json.loads(x) for x in open(os.path.join(bd, "events.jsonl"))]
    ev[-1]["ts"] -= 2 * 86400  # backdate the take
    with open(os.path.join(bd, "events.jsonl"), "w") as f:
        f.write("".join(json.dumps(e) + "\n" for e in ev))
    run(["rebuild"], d)
    _, out = run(["queue", "gate"], d, "sGate")
    check("an item running over 24h shows as stale", "running STALE" in out, out)


if __name__ == "__main__":
    sys.exit(main())
