#!/usr/bin/env python3
"""Safety checks for Docket: secret scrubbing, compaction, context pressure, rtk, git hook bypass,
SessionStart size. Stdlib only.

    python3 tests/smoke_safety_test.py
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


def pre_bash(cwd, sid, cmd, **env):
    payload = dict(hook_event_name="PreToolUse", session_id=sid, cwd=cwd, tool_name="Bash", tool_input={"command": cmd})
    _, out = run(["hook"], cwd, stdin=json.dumps(payload), extra_env=env)
    return json.loads(out)["hookSpecificOutput"].get("permissionDecision") if out.strip().startswith("{") else None


def main():
    d = tempfile.mkdtemp(prefix="docket-safety-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    bd = os.path.join(d, ".docket")
    gh, aws = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8", "AKIA" + "IOSFODNN7EXAMPLE"
    hook(d, "SessionStart", "sS", source="startup")
    hook(d, "UserPromptSubmit", "sS", prompt="deploy with %s and %s, then fix the login form" % (gh, aws))
    ev, st = (open(os.path.join(bd, f), encoding="utf-8").read() for f in ("events.jsonl", "state.json"))
    check("a prompt's GitHub token and AWS key are stored redacted",
          gh not in ev + st and aws not in ev + st and "[REDACTED]" in ev and "fix the login form" in ev, ev[-400:])

    S = docket.scrub
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
    cases = {
        "password=hunter2hunter2": "password=[REDACTED]",
        "Authorization: Bearer abcdefghijklmnop": "Authorization: Bearer [REDACTED]",
        "curl -H 'x' bearer abcdefghijkl": "curl -H 'x' bearer [REDACTED]",
        "api_key: \"sk-proj-abcdefghijklmnopqrstuv\"": "api_key: \"[REDACTED]\"",
        "postgres://app:s3cretpw@db:5432/x": "postgres://app:[REDACTED]@db:5432/x",
        "key " + pem + " end": "key [REDACTED] end",
    }
    bad = [(k, S(k)) for k, v in cases.items() if S(k) != v]
    check("scrub covers key=value, Bearer, sk-, DSN and PEM secrets", not bad, repr(bad))
    plain = "Refresh tokens expire after 1h; see http://localhost:3000 and task-runner-for-everything; token expiry"
    check("ordinary text is untouched", S(plain) == plain, S(plain))
    check("scrub is linear on long input", S("token=" + "a" * 200000 + "!") is not None)

    run(["work", "new", "Ship exporter", "-k", "exporter"], d, "sS")
    run(["log", "brief", "Exporter", "--now", "wiring CSV", "--next", "write tests"], d, "sS")
    _, out = run(["hook"], d, stdin=json.dumps(dict(hook_event_name="PreCompact", session_id="sS", cwd=d, trigger="auto")))
    check("PreCompact records the event and repeats the brief",
          '"kind": "compact"' in open(os.path.join(bd, "events.jsonl")).read() and "wiring CSV" in out and "write tests" in out, out)
    ctx = hook(d, "SessionStart", "sS", source="compact")
    check("SessionStart after compaction reminds the session of its brief", "wiring CSV" in ctx, ctx[-400:])

    sl = lambda cw: run(["statusline"], d, stdin=json.dumps(dict(session_id="sS", cwd=d, **cw)))
    sl({})  # missing context_window: nothing recorded, nothing breaks
    check("statusline without context_window records nothing", not os.path.exists(os.path.join(bd, "ctx", "sS")))
    post = lambda: hook(d, "PostToolUse", "sS", tool_name="Read", tool_input={})
    sl({"context_window": {"remaining_percentage": 30}})
    a, b = post(), post()
    check("context at 70% nudges once", "Context is 70% used" in a and "Context is" not in b, a + "|" + b)
    sl({"context_window": {"used_percentage": 80}})
    a, b = post(), post()
    check("context at 80% nudges again, once", "Context is 80% used" in a and "Context is" not in b, a + "|" + b)

    check("rtk-prefixed builds count as heavy", docket.is_heavy("rtk cargo test") and not docket.is_heavy("rtk git status"))
    check("rtk-prefixed relief commands pass the memory guard", docket.RELIEF.match("rtk git status") is not None)

    denied = ["git commit --no-verify -m x", "git commit -nm wip", "git push --no-verify origin main",
              "git -c core.hooksPath=/dev/null commit -m x", "cd a && rtk git commit -an -m x"]
    allowed = ["git commit -m 'skip --no-verify next time'", "git push -n origin main", "git commit -m x -- --no-verify",
               "cat <<EOF\ngit commit --no-verify\nEOF", "echo git commit --no-verify", "git commit --amend -m x"]
    got = {c: pre_bash(d, "sS", c) for c in denied + allowed}
    check("git hook bypass is denied", all(got[c] == "deny" for c in denied), repr(got))
    check("quoted, heredoc and dry-run mentions are not denied", all(got[c] is None for c in allowed), repr(got))
    check("DOCKET_NOVERIFY_GUARD=off allows it",
          pre_bash(d, "sS", "git commit --no-verify -m x", DOCKET_NOVERIFY_GUARD="off") is None)

    for i in range(40):  # a board long enough to overflow SessionStart
        run(["post", "Notice %d" % i, "-b", "x" * 400, "--pin"], d, "sS")
    ctx = hook(d, "SessionStart", "sBig", source="startup")
    check("SessionStart context is capped, own context first",
          len(ctx) < 8300 and ctx.startswith("DOCKET is on") and ("(more:" in ctx or "30 older pins" in ctx),
          "%d chars" % len(ctx))

    before = open(os.path.join(bd, "state.json"), encoding="utf-8").read()
    run(["rebuild"], d)
    after = open(os.path.join(bd, "state.json"), encoding="utf-8").read()
    a, b = json.loads(before), json.loads(after)
    a.pop("index", None); b.pop("index", None)
    check("rebuild reproduces state with compact events", a == b)

    # bugs seen live in xyla: flags agents pass everywhere, bare pending/check, guard blocking docket itself
    for args in (["who", "--session", "sS"], ["audit", "--session", "sS", "--agent", "main"],
                 ["--session", "sS", "lanes"], ["work", "list", "--session=sS"]):
        code, out = run(args, d)
        check("%s takes --session/--agent" % args[0], code == 0 and "unrecognized" not in out, out[-200:])
    run(["work", "new", "Login form", "-k", "login"], d, session="sS")
    code, out = run(["pending"], d, session="sS")
    check("pending defaults to the session's item", code == 0 and "required" not in out, out[-200:])
    for c, want in (('cd /x; python3 /a/docket.py reply 12 "hi"', True), ("D=/a/docket.py; S=x; python3 $D who", True),
                    ('B="python3 /a/docket.py"; $B who', True), ('d(){ python3 /a/docket.py "$@"; }; d reply 1 "x"', True),
                    ("docket mem", True),
                    ("ps -Ao rss,comm | awk '{r[$2]+=$1; c++} END{print c}' | sort -rn | head; sysctl hw.memsize", True),
                    ("echo 'a; make'", True), ("grep x f | sort; npm test", False), ("cd x; docket reply 1 hi", True), ("cd x && go test ./...", False), ("python3 scan.py", False), ("X=1; python3 $X", False)):
        check("memory guard: %s is %s" % (c, "light" if want else "new work"), docket.light(c) == want)
    other = os.path.join(d, "other")
    os.makedirs(os.path.join(other, ".docket"))
    old = os.environ.get("DOCKET_ROOT")
    os.environ["DOCKET_ROOT"] = d
    try:
        check("a folder's own .docket wins over DOCKET_ROOT", docket.find_root(other) == os.path.realpath(other))
        check("DOCKET_ROOT still covers folders without one", docket.find_root("/") == os.path.realpath(d))
    finally:
        os.environ.pop("DOCKET_ROOT") if old is None else os.environ.__setitem__("DOCKET_ROOT", old)

    # upkeep nobody owns: old pins, settled notes to the user, idle items, lagging briefs -> tidy list, steward duty
    run(["post", "Proof contracts v2", "--pin"], d, session="sS")
    run(["msg", "user", "W-0001 needs your A/B/C"], d, session="sS")
    run(["work", "new", "Old idle thing", "-k", "idle"], d, session="sT")
    st = docket.load_state(d)
    day = docket.now() - 2 * 86400
    for m in st["msgs"]:
        m["ts"] = day
    for w in st["work"].values():
        w["updated"] = day
    rows = docket.tidy_list(st)
    kinds = {r.split()[0] for r in rows}
    check("tidy lists old pins, needs and idle items", {"pin", "needs", "item"} <= kinds, "\n".join(rows))
    note = next(m for m in st["msgs"] if "user" in m["to"])
    code, out = run(["withdraw", note["id"], "--reason", "decided in 3b74312f43"], d, session="sS")
    check("withdraw takes a settled note off the needs list",
          code == 0 and not any(n["id"] == note["id"] for n in docket.needs_user(docket.load_state(d))), out)
    code, out = run(["withdraw", "nosuchid", "--reason", "x"], d, session="sS")
    check("withdraw names ids it can't find", "not on the needs list" in out, out)
    st = docket.load_state(d)
    for m in st["msgs"]:
        m["ts"] = day
    for w in st["work"].values():
        w["updated"] = day
    for k in ("sS", "sT"):
        st["sessions"][k].update(sock="/nonexistent/sock", host=docket.socket.gethostname(), pid=os.getpid(), status="idle")
    first = docket.steward(d, st)
    check("steward hands tidy duty to one live session", first in ("sS", "sT"))
    st2 = docket.load_state(d)
    duty = [m for m in st2["msgs"] if m["sid"] == "steward"]
    check("tidy duty is a tracked ask listing the stale things", len(duty) == 1 and duty[0]["kind"] == "ask"
          and "Old idle thing" in duty[0]["body"] and "pin " in duty[0]["body"], duty and duty[0]["body"][-600:])
    check("the steward is not a session", "steward" not in [x["id"] for x in docket.free_identities(st2, "sS")]
          if hasattr(docket, "free_identities") else True)
    check("steward waits its turn", docket.steward(d, st) is None)
    os.utime(os.path.join(bd, "steward"), (0, 0))
    for k in ("sS", "sT"):
        st2["sessions"][k].update(sock="/nonexistent/sock", host=docket.socket.gethostname(), pid=os.getpid(), status="idle")
    for m in st2["msgs"]:
        m["ts"] = day
    for w in st2["work"].values():
        w["updated"] = day
    check("tidy duty rotates to the other session", docket.steward(d, st2) not in (first, None))


if __name__ == "__main__":
    sys.exit(main())
