#!/usr/bin/env python3
"""State stays small and injected context stays within budget. Stdlib only.

state.json keeps clipped entry bodies (the full text is read back from events.jsonl when shown),
data.js is rewritten at most once a minute, and the mail and board blocks a hook injects are capped.

    python3 tests/smoke_size_test.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402


def main():
    d = tempfile.mkdtemp(prefix="docket-size-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    st = lambda: json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
    hook(d, "SessionStart", "size1", source="startup")
    hook(d, "SessionStart", "size2", source="startup")
    run(["work", "new", "Size work", "--session", "size1"], d)
    big = "".join("line %04d of a long subagent output\n" % i for i in range(400))  # ~14 KB
    hook(d, "SubagentStop", "size1", agent_id="a1", agent_type="general-purpose", last_assistant_message=big)
    for i in range(5):
        run(["log", "note", "Note %d" % i, "-b", big[:3000] + "END%d" % i, "--session", "size1"], d)

    s = st()
    ents = s["sessions"]["size1"]["entries"]
    check("state keeps clipped bodies, not full ones", ents and max(len(e["body"]) for e in ents) <= 500,
          str([len(e["body"]) for e in ents]))
    check("a clipped entry remembers where its full text is", all("at" in e for e in ents if e["kind"] in ("note", "output")))
    check("an agent's output is clipped in state",
          all(len(a.get("output", "")) <= 400 for a in s["sessions"]["size1"]["agents"].values()))
    check("state events carry no long bodies", all(len(e.get("body") or "") <= 200 for e in s["events"]))
    note = [e for e in ents if e["title"] == "Note 4"][0]
    _, out = run(["show", note["id"]], d)
    check("show prints the full body", "END4" in out and "line 0080 of" in out, out[-300:])
    _, page = run(["show", "W-0001"], d)
    check("the work page shows full bodies", "line 0080 of" in page, page[-300:])
    m0 = os.path.getmtime(os.path.join(d, ".docket", "data.js"))
    os.utime(os.path.join(d, ".docket", "data.js"), (m0 - 5, m0 - 5))
    m1 = os.path.getmtime(os.path.join(d, ".docket", "data.js"))
    run(["log", "note", "One more", "--session", "size1"], d)
    check("data.js is not rewritten on every write", os.path.getmtime(os.path.join(d, ".docket", "data.js")) == m1)
    hook(d, "Stop", "size1")
    check("data.js is rewritten when a session idles", os.path.getmtime(os.path.join(d, ".docket", "data.js")) != m1)
    data = open(os.path.join(d, ".docket", "data.js"), encoding="utf-8").read()
    check("data.js has full bodies for the viewer", "line 0300 of" in data and "END4" in data)

    before = open(os.path.join(d, ".docket", "state.json"), encoding="utf-8").read()
    run(["rebuild"], d)
    a, b = json.loads(before), st()
    a.pop("index", None), b.pop("index", None)
    check("rebuild reproduces state (offsets included)", a == b)
    run(["rebuild"], d)
    c = st()
    c.pop("index", None)
    check("rebuild is deterministic", b == c)

    for i in range(30):  # a flood of mail: the hook brings what fits, the rest stays unread
        run(["msg", "size2", "Status %02d" % i, "-b", "Status %02d detail " % i + "x" * 600, "--kind", "finding",
             "--session", "size1"], d)
    run(["msg", "size2", "Please check the cache", "--kind", "ask", "--session", "size1"], d)
    ctx = hook(d, "UserPromptSubmit", "size2", prompt="go on")
    mail = ctx[ctx.find("<docket-mail"):ctx.find("</docket-mail>")]
    check("injected mail stays within its budget", 0 < len(mail) < 8000, str(len(mail)))
    check("an ask comes first even in a flood", "Please check the cache" in mail)
    check("mail that didn't fit says how to get it", "more unread" in mail, mail[-300:])
    check("a title that opens the body isn't printed twice", mail.count("Status 00") == 1)
    seen = mail
    for _ in range(6):  # mid-turn: each tool call brings the next slice, with no new mail arriving
        seen += hook(d, "PostToolUse", "size2", tool_name="Bash", tool_input={"command": "ls"})
    check("the rest arrives on the next tool calls, each message once",
          all(seen.count("Status %02d detail" % i) == 1 for i in range(30)),
          str([i for i in range(30) if seen.count("Status %02d detail" % i) != 1]))

    for i in range(12):
        run(["post", "Pin %02d about something else" % i, "-b", "pinbody%02d " % i + "y" * 280, "--pin", "--session", "size1"], d)
    ctx = hook(d, "SessionStart", "size3", source="startup")
    board = ctx[ctx.find("<docket-board"):]
    check("pins about other work show by title only", "Pin 11" in board and "pinbody11" not in board, board[:600])
    check("older pins are counted, not dropped silently", "older pins" in board)


if __name__ == "__main__":
    sys.exit(main())
