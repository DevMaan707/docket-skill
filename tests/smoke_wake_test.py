#!/usr/bin/env python3
"""Who gets woken: plain fyi waits for the recipient's next hook, asks wake it; the sender sees read
receipts instead of acks. Stdlib only. Uses a temp socket, never Claude Code's.

    python3 tests/smoke_wake_test.py
"""
import json
import os
import re
import shutil
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, run  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-wake-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    sp = os.path.join(tempfile.mkdtemp(prefix="dk-"), "in.sock")
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sp)
    srv.listen(20)
    h = lambda event, sid, env=None, **kw: run(["hook"], d, stdin=json.dumps(dict(
        hook_event_name=event, session_id=sid, cwd=d, **kw)), extra_env=env)[1]
    wakes = lambda: sum(1 for l in open(os.path.join(d, ".docket", "events.jsonl")) if '"sock_wake"' in l)
    msg = lambda *a: run(["msg"] + list(a) + ["--session", "sesA"], d)[1]
    mid = lambda out: re.search(r"sent \w+ (\w+)", out).group(1)
    for sid in ("sesA", "sesB", "sesC"):
        h("SessionStart", sid, dict(CLAUDE_CODE_MESSAGING_SOCKET=sp), source="startup")
        h("Stop", sid)  # idle

    out = msg("sesB", "Gate took 9m40s on main", "--kind", "fyi")
    check("fyi doesn't wake an idle session", wakes() == 0 and "nudged" not in out, out)
    out = h("Stop", "sesB", dict(DOCKET_LISTEN="on"))
    check("Stop doesn't keep a session going for a fyi", '"block"' not in out, out)
    out = h("UserPromptSubmit", "sesB", prompt="carry on")
    check("the fyi arrives with the next prompt", "Gate took 9m40s" in out, out)

    ask = mid(msg("sesB,sesC", "Is the test box free?", "--kind", "ask"))
    check("an ask wakes", wakes() == 1, str(wakes()))
    msg("sesB", "Root cause: cache key misses the arch", "--kind", "finding")
    check("a finding wakes", wakes() == 2, str(wakes()))
    run(["reply", ask, "thanks!", "--session", "sesB"], d)
    check("a bare ack doesn't wake, even in an ask's thread", wakes() == 2, str(wakes()))
    run(["reply", ask, "Yes, free until 15:00", "--session", "sesB"], d)
    check("an answer to an ask wakes the asker", wakes() == 3, str(wakes()))

    h("UserPromptSubmit", "sesB", prompt="go")  # sB reads the ask, sC doesn't
    _, out = run(["show", ask], d)
    check("show <msg id> says who read it", "Seen by 1/2: session sesB" in out, out)
    out = h("UserPromptSubmit", "sesA", prompt="next")  # sA has the answer: its mail block carries receipts
    check("the sender's mail block shows receipts", "Seen by (your messages of the last hour): " in out
          and "[%s] 1/2 (session sesB)" % ask in out, out)
    _, out = run(["inbox", "--session", "sesA"], d)
    check("inbox shows receipts when nothing is unread", "No unread messages." in out and "[%s] 1/2" % ask in out, out)
    srv.close()
    shutil.rmtree(os.path.dirname(sp), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
