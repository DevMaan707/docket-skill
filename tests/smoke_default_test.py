#!/usr/bin/env python3
"""Defaults for questions to the user: applied after the deadline, never the user's words. Stdlib only.

    python3 tests/smoke_default_test.py
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
    d = tempfile.mkdtemp(prefix="docket-default-")
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def backdate(d):
    """Move each question with a default back in time, past its deadline, in the log; then rebuild state from it."""
    p = os.path.join(d, ".docket", "events.jsonl")
    evs = [json.loads(l) for l in open(p, encoding="utf-8")]
    for e in evs:
        if e.get("defaultAt") and e["defaultAt"] > docket.now():
            shift = e["defaultAt"] - docket.now() + 60
            e["ts"] -= shift
            e["defaultAt"] -= shift
    with open(p, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(e) + "\n" for e in evs))
    run(["rebuild"], d)


def _main(d):
    bd = os.path.join(d, ".docket")
    hook(d, "SessionStart", "sQ", source="startup")
    hook(d, "UserPromptSubmit", "sQ", prompt="build the CSV exporter")
    run(["work", "new", "CSV exporter", "-k", "csv"], d, "sQ")

    q, dflt = "Exporter: comma or semicolon separator?", "use comma, the RFC 4180 default"
    code, out = run(["msg", "user", q, "--default", dflt], d, "sQ")
    check("msg user --default is accepted and shows when it applies", code == 0 and "defaults in 4h to: use comma" in out, out)
    mid = out.split()[2]
    code, out = run(["needs"], d)
    check("needs shows the default and its deadline", "defaults in 4h to: use comma" in out, out)

    for risky in ("Force push the rebased branch to main?", "Drop table users_old?", "Deploy to prod now?",
                  "Run rm -rf build/ on the server?", "Change the billing plan?"):
        code, out = run(["msg", "user", risky, "--default", "yes"], d, "sQ")
        check("risky question refuses --default: %s" % risky, code != 0 and "Refused --default" in out
              and len(out.strip().splitlines()) == 1, out)
    code, out = run(["msg", "user", "Should the goal be 95% recall?", "--default", "yes"], d, "sQ")
    check("goal-type question refuses --default", code != 0 and "user's alone" in out, out)
    code, out = run(["msg", "sQ", "hello", "--default", "x"], d, "sR")
    check("--default only on questions to the user", code != 0, out)

    hook(d, "SessionStart", "sR", source="startup")
    code, out = run(["msg", "user", "Name the CLI flag --sep or --delimiter?", "--default", "use --delimiter",
                     "--decide-after", "30m"], d, "sR")
    mid2 = out.split()[2]
    st = docket.load_state(d)
    check("before the deadline nothing is applied", not docket.apply_defaults(d, st)
          and not any(m.get("defaulted") for m in st["msgs"]))

    backdate(d)
    os.environ.update(DOCKET_NOTIFY="off", DOCKET_WAKE="off")
    n = docket.apply_defaults(d)
    check("both defaults apply after the deadline", n == 2, str(n))
    check("applying again does nothing", docket.apply_defaults(d) == 0)
    st = docket.load_state(d)
    dec = [e for e in st["sessions"]["sQ"]["entries"] if e["kind"] == "decision"]
    check("a decision in the asker's name, marked as not the user's",
          len(dec) == 1 and dec[0]["title"].startswith("Proceeding on default (user didn't answer in 4h): use comma")
          and mid in dec[0]["body"] and "Not the user's decision" in dec[0]["body"], repr(dec))
    told = [m for m in st["msgs"] if m["to"] == ["sQ"] and m["sid"] == "steward"]
    check("the asker is told it may proceed", len(told) == 1 and "proceed on your default" in told[0]["title"], repr(told))
    ctx = hook(d, "PostToolUse", "sQ", tool_name="Read", tool_input={})
    check("the asker's next tool call delivers it", "proceed on your default" in ctx, ctx[-600:])
    code, out = run(["needs"], d)
    check("the question stays in needs, overridable", mid in out and "defaulted; answer to override" in out, out)
    check("nothing from the user was recorded", not any(m["sid"] == "user" for m in st["msgs"]))

    os.environ["CLAUDECODE"] = "1"
    try:
        check("the default never satisfies user_said", not docket.user_said(d, "sQ", dflt))
    finally:
        os.environ.pop("CLAUDECODE")
    code, out = run(["answer", mid, dflt], d, "sQ")
    check("an agent can't answer with the default", code != 0 and "Only the user" in out, out)

    run(["answer", mid, "semicolon, our users are in Germany"], d, agent=False)
    st = docket.load_state(d)
    ov = [m for m in st["msgs"] if m["sid"] == "user" and m["to"] == ["sQ"]]
    check("a later answer reaches the asker as an override that reverses the default",
          len(ov) == 1 and ov[0]["title"].startswith("Override of your default: semicolon")
          and "reverses the default" in ov[0]["body"] and "use comma" in ov[0]["body"], repr(ov))
    rows = docket.needs_user(st)
    check("answered question leaves needs; the other stays", [r["id"] for r in rows if r["id"] in (mid, mid2)] == [mid2], repr(rows))

    # the hook path applies due defaults, rate-limited by a stamp
    run(["msg", "user", "Cache size 64 or 128 MB?", "--default", "64 MB"], d, "sR")
    backdate(d)
    os.utime(os.path.join(bd, "defaults.stamp"), (0, 0))
    hook(d, "PostToolUse", "sR", tool_name="Read", tool_input={})
    st = docket.load_state(d)
    check("PostToolUse applies a due default", any(e["title"].endswith("64 MB") for e in st["sessions"]["sR"]["entries"]))

    before = open(os.path.join(bd, "state.json"), encoding="utf-8").read()
    run(["rebuild"], d)
    after = open(os.path.join(bd, "state.json"), encoding="utf-8").read()
    a, b = json.loads(before), json.loads(after)
    a.pop("index", None); b.pop("index", None)
    check("rebuild reproduces state with defaults", a == b)


if __name__ == "__main__":
    sys.exit(main())
