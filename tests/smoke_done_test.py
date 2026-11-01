#!/usr/bin/env python3
"""Done means done: done-when criteria, the close gate, reviews pinned to code, commit trailers,
and subagents that claim success without doing anything.

    python3 tests/smoke_done_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402


def git(d, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=d, capture_output=True, check=True)


def main():
    d = tempfile.mkdtemp(prefix="docket-done-")
    src = os.path.join(d, "src", "limit.py")
    os.makedirs(os.path.dirname(src))
    with open(src, "w") as f:
        f.write("TRIES = 5\n")
    git(d, "init", "-q")
    git(d, "add", ".")
    git(d, "commit", "-qm", "init")
    try:
        hook(d, "SessionStart", "sA", source="startup")
        hook(d, "SessionStart", "sB", source="startup")
        code, out = run(["work", "new", "Login rate limiter", "--top-level", "--done-when", "429 after 5 tries",
                         "--done-when", "sast.fn<=0"], d, "sA")
        check("work new prints its criteria", "W-0001/AC1" in out and "W-0001/AC2" in out, out)
        _, page = run(["show", "W-0001"], d, "sA")
        check("criteria sit at the top of the page with status",
              "## Done when" in page and page.index("## Done when") < page.index("## Current brief")
              and "**AC2** sast.fn<=0" in page and "no sast.fn metric yet" in page, page[:1500])
        hook(d, "PostToolUse", "sA", tool_name="Edit", tool_input={"file_path": src})

        code, out = run(["work", "status", "W-0001", "done"], d, "sA")
        check("done refused while criteria are open and nobody reviewed",
              code == 1 and "AC1" in out and "AC2" in out and "log review" in out and "--verdict sound" in out, out)
        code, out = run(["resolve", "AC1"], d, "sA")
        check("resolving a criterion needs evidence", code != 0, out)
        code, out = run(["resolve", "AC1", "--reason", "tests/test_limit.py::test_429 passes"], d, "sA")
        check("bare AC id resolves on the session's item", code == 0 and "AC1 done" in out, out)
        code, out = run(["drop", "W-0001/AC2", "--reason", "too strict"], d, "sB")
        check("another session can't drop a frozen criterion", "frozen" in out, out)

        run(["metric", "sast", "fn=2"], d, "sA")
        code, out = run(["work", "status", "W-0001", "done"], d, "sA")
        check("metric criterion unmet shows its current value", code == 1 and "fn=2" in out and "AC1" not in out, out)
        run(["metric", "sast", "fn=0"], d, "sA")

        run(["log", "review", "looks fine to me", "--verdict", "sound", "--work", "W-0001"], d, "sA")
        code, out = run(["work", "status", "W-0001", "done"], d, "sA")
        check("the builder alone can't vouch for its work", code == 1 and "no review" in out and "AC2" not in out, out)
        run(["log", "review", "one hole", "--verdict", "sound", "--critical", "1", "--work", "W-0001"], d, "sB")
        code, out = run(["work", "status", "W-0001", "done"], d, "sA")
        check("a review with critical findings doesn't count as sound", code == 1 and "no review" in out, out)
        code, out = run(["log", "review", "limiter checked", "--verdict", "sound", "--scope", "diff", "--work", "W-0001"], d, "sB")
        rid = out.split()[2]
        ev = [json.loads(l) for l in open(os.path.join(d, ".docket", "events.jsonl"))]
        rv = next(e for e in ev if e["id"] == rid)
        check("a review is pinned to HEAD and the item's file hashes",
              rv.get("head") and "src/limit.py" in rv.get("files", {}) and rv.get("scope") == "diff", str(rv))
        code, out = run(["check", "W-0001"], d, "sA")
        check("an unchanged review isn't stale", "STALE review" not in out, out)
        with open(src, "a") as f:
            f.write("WINDOW = 60\n")
        code, out = run(["check", "W-0001"], d, "sA")
        check("check reports a review STALE once its files change", "STALE review limiter checked" in out, out)
        code, out = run(["work", "status", "W-0001", "done"], d, "sA")
        check("criteria met and reviewed by someone else: done", code == 0 and "is now done" in out, out)

        run(["work", "new", "Docs pass", "--top-level", "--done-when", "README updated"], d, "sA")
        code, out = run(["work", "accept", "W-0002", "--done-when", "SKILL.md updated"], d, "sA")
        check("accept adds a later criterion", "W-0002/AC2" in out, out)
        code, out = run(["drop", "W-0002/AC2", "--reason", "folded into AC1"], d, "sA")
        check("the session that set a criterion can drop it", "AC2 dropped" in out, out)
        code, out = run(["work", "status", "W-0002", "done", "--force"], d, "sA")
        check("--force needs a reason", code != 0 and "reason" in out, out)
        code, out = run(["work", "status", "W-0002", "done", "--force", "--reason", "user said ship it"], d, "sA")
        _, page = run(["show", "W-0002"], d, "sA")
        check("forced close is done and logged as a decision",
              code == 0 and "Closed W-0002 without meeting its bar" in page, out + page[-1500:])

        run(["work", "new", "Retry backoff", "--top-level", "--done-when", "backoff doubles each retry"], d, "sB")
        run(["log", "brief", "x", "--now", "backoff", "--next", "Cap the jitter window"], d, "sB")
        hook(d, "SessionEnd", "sB", reason="exit")  # nobody live: its tasks show in the audit
        _, out = run(["pending", "W-0003"], d, "sA")
        nid = next(l.split()[0] for l in out.splitlines() if "jitter" in l)
        with open(src, "a") as f:
            f.write("BACKOFF = 2\n")
        git(d, "commit", "-qam", "Exponential retry\n\nDocket: W-0003/AC1\nAlso %s" % nid)
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        _, out = run(["audit"], d, "sA")
        ac = next((l for l in out.splitlines() if "AC1" in l and "W-0003" in l), "")
        nl = next((l for l in out.splitlines() if nid in l), "")
        check("a commit naming W-x/ACn marks it DONE? with the sha", "DONE?" in ac and sha in ac, out)
        check("a commit naming a pending pid marks it DONE?", "DONE?" in nl and sha in nl, out)

        run(["hook"], d, stdin=json.dumps(dict(hook_event_name="PreToolUse", session_id="sA", cwd=d, tool_name="Agent",
            tool_input={"description": "fix it", "prompt": "fix the parser bug", "subagent_type": "general-purpose"})),
            extra_env=dict(DOCKET_MEM_GUARD="off"))  # spawned by the session, not one of Claude Code's own helpers
        hook(d, "SubagentStart", "sA", agent_id="lazy01", agent_type="general-purpose")
        hook(d, "SubagentStop", "sA", agent_id="lazy01", agent_type="general-purpose",
             last_assistant_message="Implemented the limiter; all tests pass.")
        hook(d, "SubagentStart", "sA", agent_id="busy01", agent_type="general-purpose")
        hook(d, "PostToolUse", "sA", agent_id="busy01", agent_type="general-purpose", tool_name="Edit",
             tool_input={"file_path": src})
        hook(d, "SubagentStop", "sA", agent_id="busy01", agent_type="general-purpose", last_assistant_message="Done.")
        tr = os.path.join(d, "tr.jsonl")
        with open(tr, "w") as f:
            f.write(json.dumps({"type": "tool_use", "name": "Bash", "input": {"command": "python3 -m pytest -q"}}) + "\n")
        hook(d, "SubagentStart", "sA", agent_id="test01", agent_type="general-purpose")
        hook(d, "SubagentStop", "sA", agent_id="test01", agent_type="general-purpose",
             last_assistant_message="Fixed, tests pass.", agent_transcript_path=tr)
        ctx = hook(d, "PostToolUse", "sA", tool_name="Bash", tool_input={"command": "ls"})
        check("a subagent claiming done without edits or tests is flagged to its main session",
              "general-purpose:lazy01 reports done but changed no files" in ctx, ctx)
        check("subagents that edited or ran tests are not flagged", "busy01" not in ctx and "test01" not in ctx, ctx)

        before = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
        run(["rebuild"], d)
        after = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
        before.pop("index", None); after.pop("index", None)
        check("rebuild reproduces state", before == after)
        print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
