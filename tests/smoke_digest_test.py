#!/usr/bin/env python3
"""Status digest for hubs: a session that gets lots of direct fyi mail gets it batched, not one by one.
Stdlib only.

    python3 tests/smoke_digest_test.py
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402


def prompt(d, sid, **env):
    payload = dict(hook_event_name="UserPromptSubmit", session_id=sid, cwd=d, prompt="go on")
    _, out = run(["hook"], d, stdin=json.dumps(payload), extra_env=env)
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip().startswith("{") else ""


def main():
    d = tempfile.mkdtemp(prefix="docket-digest-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    for s in ("lead1", "work1", "other1"):
        hook(d, "SessionStart", s, source="startup")
    msg = lambda to, title, *x: run(["msg", to, title, "--session", "work1"] + list(x), d)[1]

    out = msg("other1", "batch running on box 2")
    check("a fyi to a quiet session is not steered", "digest" not in out, out)
    check("a non-hub session gets fyi immediately", "batch running on box 2" in prompt(d, "other1"))

    for i in range(21):
        out = msg("lead1", "status %02d" % i)
    check("the sender of fyi to a hub is steered to its brief", "digest" in out and "log brief" in out, out)
    ctx = prompt(d, "lead1")
    check("a new hub gets its backlog as one digest",
          "Status digest: 21 fyi" in ctx and "status 20" in ctx and "show <id>" in ctx and "  status" not in ctx, ctx[-800:])

    msg("lead1", "status held")
    ctx = prompt(d, "lead1")
    check("a hub's fyi is held inside the digest window", "status held" not in ctx, ctx[-600:])

    msg("lead1", "need a decision on the cache", "--kind", "ask")
    ctx = prompt(d, "lead1")
    check("an ask to the hub is delivered immediately", "need a decision on the cache" in ctx and "status held" not in ctx, ctx[-600:])

    ctx = prompt(d, "lead1", DOCKET_DIGEST_MINUTES="0")
    check("the held fyi goes out as a digest after the window", "Status digest: 1 fyi" in ctx and "status held" in ctx, ctx[-600:])

    msg("lead1", "status for inbox")
    out = run(["inbox", "--session", "lead1"], d)[1]
    check("docket inbox shows held mail", "status for inbox" in out, out)

    mid = (re.findall(r"\[(\w+)\][^\n]*status for inbox", out) or ["-"])[0]
    out = run(["show", mid], d)[1]
    check("docket show <msg id> reads one in full", "status for inbox" in out, out)

    bd = os.path.join(d, ".docket")
    before = json.load(open(os.path.join(bd, "state.json"), encoding="utf-8"))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(bd, "state.json"), encoding="utf-8"))
    before.pop("index", None); after.pop("index", None)
    check("digest delivery times survive an identical rebuild",
          before == after and before["sessions"]["lead1"].get("digestTs"))


if __name__ == "__main__":
    sys.exit(main())
