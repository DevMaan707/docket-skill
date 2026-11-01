#!/usr/bin/env python3
"""Socket-wake learning for Docket: a session whose inbox nudges start turns doesn't need `listen`;
one whose nudges go unanswered is asked for a listener. Stdlib only. Never touches a real socket.

    python3 tests/smoke_listen_test.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import DOCKET, FAILS, check, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-listen-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    on = dict(DOCKET_LISTEN="on", DOCKET_SWEEP="off")
    h = lambda event, sid, env=None, **kw: run(["hook"], d, stdin=json.dumps(dict(hook_event_name=event, session_id=sid,
                                                                                  cwd=d, **kw)), extra_env=env)[1]
    sessions = lambda: json.load(open(os.path.join(d, ".docket", "state.json")))["sessions"]
    for sid in ("sA", "sB", "sC", "sD", "sE", "sF"):
        h("SessionStart", sid, None if sid == "sE" else dict(CLAUDE_CODE_MESSAGING_SOCKET="/nonexistent/%s.sock" % sid),
          source="startup")
        h("Stop", sid)  # idle
    t = time.time()

    # a nudge answered by a [docket] prompt within 2 min: socket wakes work, listen isn't needed
    docket.emit(d, sid="sA", kind="sock_wake", to=["sB"], title="Nudged 1")
    h("UserPromptSubmit", "sB", prompt="[docket] FYI from session sA: ping")
    check("a [docket] prompt soon after a nudge marks sockOk", sessions()["sB"].get("sockOk"), str(sessions()["sB"]))
    t0 = time.time()
    code, out = run(["listen", "--session", "sB"], d)
    check("listen exits at once on a sockOk session", code == 0 and "Not needed" in out and "Don't restart" in out
          and time.time() - t0 < 10, out)
    h("Stop", "sB")

    # two nudges unanswered while idle: sockBlocked, and the Stop hook asks for a listener, saying why
    docket.emit(d, sid="sA", kind="sock_wake", to=["sC"], title="Nudged 1", ts=t - 400)
    docket.emit(d, sid="sA", kind="sock_wake", to=["sC"], title="Nudged 1", ts=t - 200)
    h("UserPromptSubmit", "sC", prompt="are you there?")
    check("two unanswered nudges mark sockBlocked", sessions()["sC"].get("sockBlocked")
          and not sessions()["sC"].get("sockOk"), str(sessions()["sC"]))
    out = h("Stop", "sC", on)
    check("Stop asks a sockBlocked session for a listener and says why", '"block"' in out and "listen --session sC" in out
          and "crossSessionInbound" in out and "bypass-permissions" in out, out)
    def keeps_listening(sid, name):
        env = dict(os.environ, CLAUDE_PID=str(os.getpid()))
        for k in ("CLAUDE_CODE_MESSAGING_SOCKET", "DOCKET_ROOT", "DOCKET_SESSION"):
            env.pop(k, None)
        p = subprocess.Popen([sys.executable, DOCKET, "listen", "--session", sid], cwd=d, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=env)
        try:
            p.wait(3)
            check(name, False, p.stdout.read())
        except subprocess.TimeoutExpired:
            check(name, True)
        p.kill()
        p.wait()

    keeps_listening("sC", "listen keeps running on a sockBlocked session")

    # unknown: today's behaviour (a socket means no nudge; no socket means the old nudge; listen runs)
    out = h("Stop", "sD", on)
    check("Stop lets an unknown session with a socket stop", "decision" not in out, out)
    out = h("Stop", "sE", on)
    check("Stop asks a session without a socket for a listener, as before",
          '"block"' in out and "Other sessions are live" in out and "crossSessionInbound" not in out, out)
    keeps_listening("sD", "listen keeps running on an unknown session")

    # wake() records its nudge (a temp socket, never Claude Code's)
    sp = os.path.join(tempfile.mkdtemp(prefix="dk-"), "in.sock")
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sp)
    srv.listen(5)
    run(["hook"], d, stdin=json.dumps(dict(hook_event_name="UserPromptSubmit", session_id="sF", cwd=d, prompt="hi")),
        extra_env=dict(CLAUDE_CODE_MESSAGING_SOCKET=sp))
    h("Stop", "sF")
    n = docket.wake(docket.load_state(d), {"sid": "sA", "to": ["sF"]}, "[docket] test")
    srv.close()
    check("wake() records a sock_wake for the session it nudged", n == 1 and sessions()["sF"].get("sockWakeTs"),
          str(sessions()["sF"]))

    _, out = run(["who"], d)
    check("who shows how each session is woken", "wake:socket" in out and "wake:listener" in out
          and "wake:unknown" in out, out)

    keys = ("sockOk", "sockBlocked", "sockMiss", "sockWakeTs", "sock")
    before = {k: {f: v.get(f) for f in keys} for k, v in sessions().items()}
    run(["rebuild"], d)
    after = {k: {f: v.get(f) for f in keys} for k, v in sessions().items()}
    check("rebuild reproduces the socket verdicts", before == after, "%s\n%s" % (before, after))


if __name__ == "__main__":
    sys.exit(main())
