#!/usr/bin/env python3
"""Leases across git worktrees: the same repo file in two worktrees (inside or outside the project folder) is one
lease; branches that would conflict on merge are told to both owners, once. Stdlib + git only.

    python3 tests/smoke_wtlease_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, pre_edit, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402

for k, v in dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t").items():
    os.environ[k] = v


def g(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def main():
    d = os.path.realpath(tempfile.mkdtemp(prefix="docket-wtl-"))
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def commit(wt, text):
    with open(os.path.join(wt, "src", "x.py"), "w") as f:
        f.write(text)
    g(wt, "commit", "-qam", text)


def _main(d):
    p = os.path.join(d, "proj")
    os.makedirs(os.path.join(p, "src"))
    g(p, "init", "-q", "-b", "main")
    for n in ("x.py", "y.py"):
        open(os.path.join(p, "src", n), "w").write("v = 0\n")
    g(p, "add", "src")
    g(p, "commit", "-qm", "first")
    with open(os.path.join(p, ".git", "info", "exclude"), "a") as f:
        f.write(".docket/\nwt/\n")
    for s in ("sA", "sB", "sC"):
        hook(p, "SessionStart", s, source="startup")
    a, b = os.path.join(p, "wt", "a"), os.path.join(d, "outside-b")  # one inside the project folder, one outside
    g(p, "worktree", "add", "-q", "-b", "fa", a)
    g(p, "worktree", "add", "-q", "-b", "fb", b)

    check("a file in a worktree is keyed by its path in the repo",
          docket.rel(p, os.path.join(a, "src", "x.py")) == "src/x.py" and docket.rel(p, os.path.join(b, "src/x.py")) == "src/x.py")
    check("outside any worktree: as before", docket.rel(p, os.path.join(d, "elsewhere.py")) is None
          and docket.rel(p, "src/y.py") == "src/y.py")

    check("first edit in worktree a is allowed", pre_edit(p, "sA", os.path.join(a, "src", "x.py")).get("permissionDecision") != "deny")
    out = pre_edit(p, "sB", os.path.join(b, "src", "x.py"))
    why = json.dumps(out)
    check("the same file in worktree b (another branch) warns, naming session sA and worktree a",
          out.get("permissionDecision") != "deny" and "src/x.py is held by session sA" in why
          and "in worktree " + a in why and "another branch" in why, why)
    out = pre_edit(p, "sC", os.path.join(p, "src", "x.py"))
    check("and in the main checkout (also another branch)", out.get("permissionDecision") != "deny" and "another branch" in json.dumps(out), repr(out))
    out = pre_edit(p, "sC", os.path.join(a, "src", "x.py"))
    check("the same file in the same worktree is denied", out.get("permissionDecision") == "deny", repr(out))
    check("a different file in worktree b is free", pre_edit(p, "sB", os.path.join(b, "src", "y.py")).get("permissionDecision") != "deny")
    code, out = run(["claim", os.path.join(b, "src", "y.py")], p, "sB")
    check("a worktree outside the project can be claimed", code == 0 and "claimed src/y.py" in out, out)

    st = docket.load_state(p)
    check("leases remember their worktree, so worktree_owner finds the owner",
          docket.worktree_owner(p, st, a) == "sA" and docket.worktree_owner(p, st, b) == "sB",
          repr(st.get("leases")))

    commit(a, "v = 1\n")
    commit(b, "v = 2\n")
    commit(p, "v = 3\n")
    st = docket.load_state(p)
    up = docket.upkeep(p, "sA", st) or ""
    check("sA is told its branch conflicts with sB's",
          "Your branch fa and session sB's branch fb both change src/x.py (merge conflict predicted)" in up, up)
    check("and with main", "Your branch fa and main both change src/x.py" in up, up)
    up = docket.upkeep(p, "sB", st) or ""
    check("sB is told too", "Your branch fb and session sA's branch fa both change src/x.py" in up, up)
    for s in ("sA", "sB"):
        os.remove(os.path.join(p, ".docket", "tidy", s + ".wt"))
    check("once per pair", "conflict" not in (docket.upkeep(p, "sA", st) or ""))
    code, out = run(["worktrees"], p)
    check("worktrees lists the conflicts", "conflicts with main (src/x.py); fb (src/x.py)" in out, out)

    c = os.path.join(p, "wt", "c")
    g(p, "worktree", "add", "-q", "-b", "fc", c, "HEAD~1")
    run(["claim", os.path.join(c, "src", "y.py")], p, "sC")
    with open(os.path.join(c, "src", "y.py"), "w") as f:
        f.write("w = 1\n")
    g(c, "commit", "-qam", "y")
    up = docket.upkeep(p, "sC", docket.load_state(p)) or ""
    check("no nudge when the branches touch disjoint files", "conflict" not in up, up)


if __name__ == "__main__":
    sys.exit(main())
