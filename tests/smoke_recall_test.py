#!/usr/bin/env python3
"""Smoke test for recall: entry search, show <entry> [--around], file recall on Read, retro, token cost.

    python3 tests/smoke_recall_test.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402


def read_hook(cwd, sid, path, **extra):
    payload = dict(hook_event_name="PreToolUse", session_id=sid, cwd=cwd, tool_name="Read",
                   tool_input={"file_path": path}, **extra)
    _, out = run(["hook"], cwd, stdin=json.dumps(payload))
    return out


def main():
    d = tempfile.mkdtemp(prefix="docket-recall-")
    try:
        os.makedirs(os.path.join(d, "src"))
        for f in ("cache.py", "other.py"):
            with open(os.path.join(d, "src", f), "w") as fh:
                fh.write("x = 1\n")
        hook(d, "SessionStart", "sA", source="startup")
        run(["work", "new", "Scanner cache layer", "-k", "cache,scanner"], d, "sA")
        _, out = run(["log", "decision", "Use an LRU for the scanner cache", "-b", "Lives in src/cache.py",
                      "--rejected", "redis"], d, "sA")
        run(["log", "deadend", "Memcached for the scanner", "-b", "too slow: 40ms per lookup"], d, "sA")
        run(["log", "note", "Unrelated note about logging"], d, "sA")
        hook(d, "PostToolUse", "sA", tool_name="Edit", tool_input={"file_path": os.path.join(d, "src", "other.py")})

        # 1. entry-level search and show
        _, out = run(["search", "memcached scanner"], d)
        check("search lists matching entries after work items", "Entries" in out and "deadend" in out
              and "Memcached" in out and "Unrelated" not in out, out)
        _, js = run(["search", "memcached scanner", "--json"], d)
        eid = [h["entry"] for h in json.loads(js) if "entry" in h][0]
        _, out = run(["show", eid[:6]], d)
        check("show <entry-id> prints the entry in full", "DEADEND" in out and "40ms per lookup" in out, out)
        _, out = run(["show", eid[:6], "--around", "1"], d)
        check("show --around prints its timeline on the work item", "> " + eid[:8] in out and "decision" in out
              and "note" in out, out)
        _, out = run(["show", "W-0001"], d)
        check("show W-xxxx still prints the work page", "Scanner cache layer" in out, out[:300])

        # 2. file recall on Read, once per session per file, never for your own entries
        hook(d, "SessionStart", "sB", source="startup")
        out = read_hook(d, "sB", os.path.join(d, "src", "cache.py"))
        check("Read of a file the record cites injects recall", "docket-recall" in out and "LRU" in out
              and "deny" not in out, out)
        out = read_hook(d, "sB", os.path.join(d, "src", "cache.py"))
        check("recall is injected once per session per file", "docket-recall" not in out, out)
        out = read_hook(d, "sB", os.path.join(d, "src", "other.py"))
        check("recall names the work item whose edits touched the file", "W-0001" in out and "edited it" in out, out)
        out = read_hook(d, "sA", os.path.join(d, "src", "cache.py"))
        check("a session isn't reminded of its own entries", "docket-recall" not in out, out)
        out = read_hook(d, "sB", os.path.join(d, "src", "nothing.py"))
        check("a file the record doesn't know stays silent", not out.strip(), out)
        hook(d, "SessionStart", "sC", source="startup")
        out = read_hook(d, "sC", os.path.join(d, "src", "cache.py"), agent_id="abc123", agent_type="Explore")
        check("a subagent's Read gets recall too", "docket-recall" in out and "LRU" in out, out)

        # 4. token cost at Stop, from the transcript since the last Stop
        tp = os.path.join(d, "transcript.jsonl")
        msg = lambda i, n: json.dumps({"type": "assistant", "message": {"id": "m%d" % i, "role": "assistant", "usage": {
            "input_tokens": n, "output_tokens": n, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}})
        with open(tp, "w") as f:
            f.write("\n".join([msg(1, 1000), msg(1, 1000), msg(2, 500), "{\"type\": \"user\"}"]) + "\n")
        env = {"DOCKET_LISTEN": "off", "DOCKET_SWEEP": "off"}
        run(["hook"], d, stdin=json.dumps(dict(hook_event_name="Stop", session_id="sB", cwd=d, transcript_path=tp)), extra_env=env)
        with open(tp, "a") as f:
            f.write(msg(3, 2000) + "\n")
        run(["hook"], d, stdin=json.dumps(dict(hook_event_name="Stop", session_id="sB", cwd=d, transcript_path=tp)), extra_env=env)
        run(["hook"], d, stdin=json.dumps(dict(hook_event_name="Stop", session_id="sB", cwd=d, transcript_path=tp)), extra_env=env)
        run(["hook"], d, stdin=json.dumps(dict(hook_event_name="Stop", session_id="sB", cwd=d,
                                               transcript_path=os.path.join(d, "missing.jsonl"))), extra_env=env)
        st = json.load(open(os.path.join(d, ".docket", "state.json")))
        rows = st.get("metrics", {}).get("tokens", [])
        check("Stop records tokens since the last Stop, deduped by message, nothing when idle",
              [r["vals"]["in"] for r in rows] == [1500, 2000] and st["sessions"]["sB"].get("tokens") == 7000, rows)
        _, out = run(["who"], d)
        check("who shows a session's token total", "7k tokens" in out, out)

        # 3. retro
        run(["log", "blocker", "Need creds"], d, "sA")
        run(["log", "review", "Checked it", "--work", "W-0001", "--verdict", "sound"], d, "sB")  # the close gate
        run(["work", "status", "W-0001", "done"], d, "sA")
        _, out = run(["retro", "--days", "7"], d, "sA")
        check("retro reports per session and overall, with 3 recommendations",
              "Per session:" in out and "1 closed" in out and "1 dead ends" in out and "Recommendations:\n1." in out
              and "\n3. " in out and "Saved as" in out, out)
        _, wl = run(["work", "list"], d)
        st = json.load(open(os.path.join(d, ".docket", "state.json")))
        check("retro files itself on a top-level Retros chore without moving the session",
              "Retros" in wl and "chore" in wl and st["sessions"]["sA"]["work"] == "W-0001", wl)
        _, out = run(["retro"], d, "sA")
        check("the next retro lists the last one's recommendations", "Last retro's recommendations" in out, out)

        before = open(os.path.join(d, ".docket", "state.json"), encoding="utf-8").read()
        run(["rebuild"], d)
        after = open(os.path.join(d, ".docket", "state.json"), encoding="utf-8").read()
        a, b = json.loads(before), json.loads(after)
        a.pop("index", None)
        b.pop("index", None)
        check("rebuild reproduces state", a == b)
        hook(d, "SessionStart", "sD", source="startup")
        out = read_hook(d, "sD", os.path.join(d, "src", "cache.py"))
        check("recall index is rebuilt from the log after rebuild", "docket-recall" in out, out)
        print("\n%s" % ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
