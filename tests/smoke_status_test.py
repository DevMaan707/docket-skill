#!/usr/bin/env python3
"""Typed status: result / handoff change the record instead of a status message. Only the owner, the lead or
the user may accept, kill or hand off; the change reaches the other sessions as one line with their next hook,
never as a wake. A status-looking msg gets a tip naming the typed command.

    python3 tests/smoke_status_test.py
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


def main():
    d = tempfile.mkdtemp(prefix="docket-status-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def _main(d):
    for k in ("sA", "sB", "sL"):
        hook(d, "SessionStart", k, source="startup")
    for p in ("plan the parser work", "split it in lanes", "go", "lane 1", "lane 2", "lane 3", "lane 4"):  # the hub
        hook(d, "UserPromptSubmit", "sL", prompt=p)
    check("sL is the lead", docket.lead_of(docket.load_state(d)) == "sL")
    run(["name", "Builder"], d, "sA")
    run(["name", "Reviewer"], d, "sB")
    run(["work", "new", "Parser rewrite", "--top-level"], d, "sA")
    run(["work", "attach", "W-0001"], d, "sB")
    hook(d, "UserPromptSubmit", "sB", prompt="ok")  # drain sB's mail

    code, out = run(["result", "W-0001", "parser merged, MAIN = abc123"], d, "sA")
    check("the owner records a result", code == 0 and "recorded" in out, out)
    st = docket.load_state(d)
    m = st["msgs"][-1]
    check("it travels as a status change that wakes nobody", m["kind"] == "status" and not docket.rouses(st, m), str(m))
    check("the result is an entry on the item", any(e["title"].startswith("W-0001 result: parser merged")
                                                    for _, e in docket.all_entries(st, "W-0001")))
    ctx = hook(d, "UserPromptSubmit", "sB", prompt="next")
    check("it reaches the other session's next context as one line",
          "<docket-changes>" in ctx and "parser merged" in ctx and "<docket-mail" not in ctx, ctx[-600:])
    ctx = hook(d, "UserPromptSubmit", "sB", prompt="again")
    check("only once", "<docket-changes>" not in ctx, ctx[-300:])

    code, out = run(["result", "W-0001", "looks good", "--accepted"], d, "sB")
    check("a non-owner can't accept", code != 0 and "Refused" in out, out)
    code, out = run(["handoff", "W-0001", "Builder"], d, "sB")
    check("nor hand off", code != 0 and "Refused" in out, out)

    code, out = run(["result", "W-0001", "meets the aim", "--accepted"], d, "sL")
    st = docket.load_state(d)
    check("the lead may accept", code == 0 and any(e.get("verdict") == "accepted"
                                                   for _, e in docket.all_entries(st, "W-0001")), out)
    check("accept doesn't close past an unmet bar", st["work"]["W-0001"]["status"] == "open" and "still open" in out, out)

    code, out = run(["handoff", "W-0001", "Reviewer"], d, "sA")
    st = docket.load_state(d)
    check("handoff changes the owner", code == 0 and st["work"]["W-0001"]["owner"] == "sB", out)
    code, out = run(["result", "W-0001", "drop it", "--killed"], d, "sA")
    check("the old owner no longer may", code != 0 and "Refused" in out, out)
    ctx = hook(d, "UserPromptSubmit", "sB", prompt="what changed")
    check("the new owner hears of it", "handed off to Reviewer" in ctx, ctx[-600:])

    run(["log", "brief", "parser", "--now", "parser", "--next", "write the docs"], d, "sA")
    st = docket.load_state(d)
    pid = next(i["pid"] for i in docket.pending_items(st, "W-0001") if i["subject"] == "write the docs")
    code, out = run(["handoff", pid, "Builder"], d, "sB")
    st = docket.load_state(d)
    it = next(i for i in docket.pending_items(st, "W-0001") if i["pid"] == pid)
    check("a task's handoff makes the target its holder", code == 0 and it["by"] == "sA", out + str(it))
    code, out = run(["result", pid, "docs written", "--accepted"], d, "sA")
    st = docket.load_state(d)
    it = next(i for i in docket.pending_items(st, "W-0001") if i["pid"] == pid)
    check("the task's holder settles it", code == 0 and it["status"] == "done", out + str(it))
    code, out = run(["result", "W-0001", "superseded by the new grammar", "--killed"], d, "sB")
    check("the new owner may kill it", code == 0 and docket.load_state(d)["work"]["W-0001"]["status"] == "abandoned", out)

    code, out = run(["msg", "Reviewer", "W-0001 accepted, merged to main"], d, "sA")
    check("a status message gets a tip naming the typed command", code == 0 and "tip:" in out and "result" in out, out)
    code, out = run(["msg", "Reviewer", "Is W-0001 merged?"], d, "sA")
    check("a question doesn't", "tip:" not in out, out)
    code, out = run(["msg", "Reviewer", "The parser leaks memory on long inputs", "--kind", "finding"], d, "sA")
    check("nor a finding", "tip:" not in out, out)

    before = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
    run(["rebuild"], d)
    after = json.load(open(os.path.join(d, ".docket", "state.json"), encoding="utf-8"))
    before.pop("index", None), after.pop("index", None)
    check("rebuild reproduces state", before == after)


if __name__ == "__main__":
    sys.exit(main())
