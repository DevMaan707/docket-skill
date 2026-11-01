#!/usr/bin/env python3
"""Ask escalation: an ask left unanswered 2 h past its due time goes once to the successor of an ended
identity, else the owner of the lane covering its work item, else the board. Stdlib only.

    python3 tests/smoke_escalate_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402

for k in ("CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "DOCKET_ROOT"):  # in-process calls too
    os.environ.pop(k, None)
os.environ.update(DOCKET_NOTIFY="off", DOCKET_WAKE="off")

A, B, L, C, N, D = "sAsker", "sBusy", "sLane", "sClosed", "sNext", "sDocs"


def main():
    d = tempfile.mkdtemp(prefix="docket-escalate-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def ask(d, frm, to, text):
    _, out = run(["msg", to, text, "--kind", "ask", "--due", "1m"], d, frm)
    return re.search(r"sent ask (\w+)", out).group(1)


def stop(d, sid):
    code, out = run(["hook"], d, stdin=json.dumps(dict(hook_event_name="Stop", session_id=sid, cwd=d)))
    check("Stop hook exits 0 for %s" % sid, code == 0, out[-400:])


def backdate(d, ids, secs):
    """Move these events (and their deadlines) into the past in the log, then rebuild state from it."""
    p = os.path.join(d, ".docket", "events.jsonl")
    evs = [json.loads(l) for l in open(p, encoding="utf-8")]
    for e in evs:
        if e["id"] in ids:
            e["ts"] -= secs
            if e.get("due"):
                e["due"] -= secs
    with open(p, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(e) + "\n" for e in evs))
    run(["rebuild"], d)


def _main(d):
    for s in (A, B, L, C, N, D):
        hook(d, "SessionStart", s, source="startup")
    run(["work", "new", "Exporter", "-k", "exporter"], d, B)            # W-0001
    run(["lane", "take", "Export", "-b", "W-0001 exporter speed"], d, L)
    run(["name", "Gate lead"], d, C)
    run(["work", "new", "Gate", "-k", "gate"], d, C)                    # W-0002
    run(["work", "new", "Docs site", "-k", "docs"], d, D)               # W-0003, no lane covers it

    a_lane = ask(d, A, B, "Why is the export slow?")
    a_succ = ask(d, A, C, "Is the gate flaky?")
    a_board = ask(d, A, D, "Where do the docs build?")
    a_done = ask(d, A, B, "Which CSV dialect?")
    run(["reply", a_done, "RFC 4180"], d, B)
    hook(d, "SessionEnd", C)
    code, out = run(["assume", "Gate lead"], d, N)
    check("a new session takes over the ended identity", code == 0, out)
    backdate(d, {a_lane, a_succ, a_board, a_done}, 3 * 3600)

    stop(d, A)  # the cheap hook path; no stamp yet, so it checks now
    st = docket.load_state(d)
    msgs = {m["id"]: m for m in st["msgs"]}
    esc = {m["re"]: m for m in st["msgs"] if m["sid"] == "steward" and m["to"] != [A]}
    check("an overdue ask escalates to the owner of the lane covering its item",
          esc.get(a_lane, {}).get("to") == [L] and msgs[a_lane].get("escalated"), repr(esc.get(a_lane)))
    check("an ask to an ended identity goes to its successor", esc.get(a_succ, {}).get("to") == [N], repr(esc.get(a_succ)))
    check("an ask with no other owner falls back to the board", esc.get(a_board, {}).get("to") == ["board"], repr(esc.get(a_board)))
    check("an answered ask does not escalate", a_done not in esc and not msgs[a_done].get("escalated"))
    check("the escalation quotes the original id and how to answer it", a_lane in esc[a_lane]["body"]
          and "reply %s" % a_lane in esc[a_lane]["body"], esc[a_lane]["body"])
    told = [m["title"] for m in st["msgs"] if m["sid"] == "steward" and m["to"] == [A]]
    check("the asker is told where each went", len(told) == 3 and any(
        t.startswith("your ask %s got no reply in 3 h; escalated to" % a_lane) for t in told)
          and any(t.endswith("escalated to board") for t in told), repr(told))
    _, ib = run(["inbox"], d, L)
    check("the lane owner gets it in its inbox", "Escalated ask %s" % a_lane in ib, ib[-600:])

    n = len(st["msgs"])
    again = docket.escalate_asks(d, docket.load_state(d))
    os.utime(os.path.join(d, ".docket", "escalate"), (0, 0))
    stop(d, B)
    check("an ask escalates only once", again == [] and len(docket.load_state(d)["msgs"]) == n, repr(again))

    _, out = run(["audit"], d, A)
    row = next((l for l in out.splitlines() if "A-" + a_lane[:6] in l), "")
    check("audit labels an escalated ask ESCALATED", "ESCALATED" in row and "escalated to" in row, out[-800:])
    check("an answered ask is not labelled ESCALATED", "ESCALATED" not in next(
        (l for l in out.splitlines() if "A-" + a_done[:6] in l), ""), out[-800:])

    run(["reply", esc[a_lane]["id"], "It was the gzip level"], d, L)
    st = docket.load_state(d)
    rep = [m for m in st["msgs"] if m["sid"] == L and m["re"] == a_lane]
    check("a reply to the escalation answers the original ask, to the asker",
          rep and rep[-1]["to"] == [A] and a_lane not in [m["id"] for m in docket.open_asks(st)], repr(rep))

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json"), encoding="utf-8"))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json"), encoding="utf-8"))
    before.pop("index", None); after.pop("index", None)
    check("rebuild reproduces the escalations exactly", before == after)


if __name__ == "__main__":
    sys.exit(main())
