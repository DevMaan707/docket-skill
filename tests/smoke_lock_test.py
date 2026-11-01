#!/usr/bin/env python3
"""Kept pins (standing rules), lock --wait (a line for a held resource), and no CLOSE? while a session's
subagents are still on the item. Stdlib only.

    python3 tests/smoke_lock_test.py
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

os.environ.update(DOCKET_NOTIFY="off", DOCKET_WAKE="off")


def main():
    d = tempfile.mkdtemp(prefix="docket-lock-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    for s in ("sA", "sB", "sC"):
        hook(d, "SessionStart", s, source="startup")

    # 1. standing rules: --keep pins are never stale
    _, out = run(["post", "USER DIRECTIVE: measure both precision and recall", "--pin", "--keep"], d, "sA")
    check("post --pin --keep says it's a rule", "(pinned rule)" in out, out)
    run(["post", "Box 3 is down today", "--pin"], d, "sA")
    _, out = run(["post", "VM regions + CampX rule"], d, "sA")
    mid = out.split()[2]
    _, out = run(["pin", mid, "--keep"], d, "sA")
    check("pin <id> --keep makes an existing post a rule", "pinned as a rule" in out, out)
    st = docket.load_state(d)
    for m in st["msgs"]:
        m["ts"] -= 2 * 86400
    rows = [r for r in docket.tidy_list(st) if r.startswith("pin")]
    check("tidy lists the old plain pin but never a rule",
          len(rows) == 1 and "Box 3" in rows[0], "\n".join(rows))
    _, out = run(["board"], d, "sA")
    check("board marks rules", out.count("RULE [") == 2 and "PINNED [" in out, out)
    blk = docket.pinned_block(st)
    check("new sessions see rules marked", blk.count("RULE [") == 2, blk)

    # 2. lock --wait: a line for a held resource
    K = docket._norm("foundry-llm")
    run(["lock", "foundry-llm", "--minutes", "30", "--why", "eval run"], d, "sA")
    code, out = run(["lock", "foundry-llm", "--wait", "--minutes", "20"], d, "sB")
    check("lock --wait on a held resource queues instead of failing", code == 0 and "#1 in line" in out, out)
    code, out = run(["lock", "foundry-llm", "--wait"], d, "sC")
    check("a second waiter is #2", code == 0 and "#2 in line" in out, out)
    _, out = run(["locks"], d)
    check("locks shows who is waiting", "waiting:" in out, out)
    _, out = run(["unlock", "foundry-llm"], d, "sA")
    st = docket.load_state(d)
    lk = st["locks"].get(K) or {}
    check("unlock hands it to the first in line", lk.get("sid") == "sB" and "handed to" in out, out + str(lk))
    told = [m for m in st["msgs"] if m["sid"] == "steward" and m["to"] == ["sB"] and "yours now" in m["title"]]
    check("the waiter is told (steward mail, so it wakes)", len(told) == 1, str(st["msgs"][-2:]))
    check("only the next waiter remains in line", [w["sid"] for w in st["lockWait"][K]] == ["sC"])
    real = docket.now
    try:  # sB's 20 min run out with sC still in line: the next hook pass hands it over
        docket.now = lambda: real() + 3600
        got = docket.hand_over(d, docket.load_state(d))
    finally:
        docket.now = real
    st = docket.load_state(d)
    check("an expired lock goes to the next waiter", got == ["sC"] and st["locks"][K]["sid"] == "sC", str(got))
    check("nothing left in line", st["lockWait"][K] == [])

    # 3. no CLOSE? while the session's subagents still work on the item
    run(["work", "new", "SAST precision analysis", "-k", "sast"], d, "sA")
    wid = docket.load_state(d)["sessions"]["sA"]["work"]
    _, out = run(["msg", wid, "Check recall too", "--kind", "ask"], d, "sB")
    pid = out.split("pending task ")[1].split()[0]
    run(["resolve", pid, "--reason", "recall checked in eval.log:12"], d, "sA")
    hook(d, "SubagentStart", "sA", agent_id="an1", agent_type="general-purpose")
    rows = [r for r in docket.audit(docket.load_state(d)) if r[0] == wid and r[2] == "CLOSE?"]
    check("no CLOSE? while a subagent is still running on the item", not rows, str(rows))
    hook(d, "SubagentStop", "sA", agent_id="an1", agent_type="general-purpose")
    rows = [r for r in docket.audit(docket.load_state(d)) if r[0] == wid and r[2] == "CLOSE?"]
    check("CLOSE? once the subagents are done", rows, str(docket.audit(docket.load_state(d))))

    before = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
    before.pop("index", None), after.pop("index", None)
    check("rebuild reproduces rules, locks and the line", before == after)


if __name__ == "__main__":
    sys.exit(main())
