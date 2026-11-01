#!/usr/bin/env python3
"""Worktrees: who made them, which are merged/pushed/clean (prunable), the owner's nudge; and a push that
moves main is posted to the board once. Stdlib + git only.

    python3 tests/smoke_worktree_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import FAILS, check, hook, run  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import docket  # noqa: E402

for k, v in dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t").items():
    os.environ[k] = v


def g(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def main():
    d = os.path.realpath(tempfile.mkdtemp(prefix="docket-wt-"))
    try:
        _main(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\n" + ("FAILED: %d" % len(FAILS) if FAILS else "all passed"))
    return 1 if FAILS else 0


def bash(p, sid, cmd, resp=None):
    return hook(p, "PostToolUse", sid, tool_name="Bash", tool_input={"command": cmd}, tool_response=resp or {})


def _main(d):
    remote, p = os.path.join(d, "remote.git"), os.path.join(d, "proj")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
    os.makedirs(p)
    g(p, "init", "-q", "-b", "main")
    open(os.path.join(p, "a.txt"), "w").write("a\n")
    g(p, "add", "a.txt")
    g(p, "commit", "-qm", "first")
    g(p, "remote", "add", "origin", remote)
    g(p, "push", "-q", "-u", "origin", "main")
    g(p, "remote", "set-head", "origin", "main")
    with open(os.path.join(p, ".git", "info", "exclude"), "a") as f:
        f.write(".docket/\n.wts/\n")
    hook(p, "SessionStart", "sA", source="startup")
    hook(p, "SessionStart", "sB", source="startup")

    wt = os.path.join(d, "wt-feat")
    g(p, "worktree", "add", "-q", "-b", "feat", "../wt-feat")
    bash(p, "sA", "git worktree add -b feat ../wt-feat")
    st = docket.load_state(p)
    check("git worktree add is recorded with its session", st.get("worktrees") == {wt: "sA"}, repr(st.get("worktrees")))

    open(os.path.join(wt, "f.txt"), "w").write("f\n")
    g(wt, "add", "f.txt")
    g(wt, "commit", "-qm", "Add feat")
    code, out = run(["worktrees"], p)
    check("an unmerged worktree is listed, unpushed, not prunable",
          code == 0 and wt in out and "owner session sA" in out and "branch feat" in out and "unpushed" in out
          and "PRUNABLE" not in out, out)

    g(p, "merge", "-q", "feat")
    r = g(p, "push", "origin", "main")
    bash(p, "sB", "git push origin main", {"stdout": r.stdout, "stderr": r.stderr})
    sha = g(p, "rev-parse", "--short=7", "HEAD").stdout.strip()
    posts = [m for m in docket.load_state(p).get("msgs", []) if m["to"] == ["board"]]
    check("a push that moves main is posted to the board as fyi", len(posts) == 1 and posts[0]["kind"] == "fyi"
          and posts[0]["title"] == "main moved to %s: Add feat (by session sB)" % sha, repr(posts))
    r = g(p, "push", "origin", "feat")
    bash(p, "sB", "git push origin feat", {"stdout": r.stdout, "stderr": r.stderr})
    bash(p, "sB", "git push origin main", {"stderr": "Everything up-to-date\n"})
    check("pushing another branch or nothing posts nothing",
          len([m for m in docket.load_state(p).get("msgs", []) if m["to"] == ["board"]]) == 1)

    code, out = run(["worktrees"], p)
    check("merged and clean but fresh: not prunable yet", "merged, clean" in out and "PRUNABLE" not in out, out)
    old = docket.now() - 7200
    os.utime(os.path.join(wt, ".git"), (old, old))
    code, out = run(["worktrees"], p)
    check("merged, pushed, clean and an hour old: prunable", "PRUNABLE " + wt in out, out)

    other = os.path.join(p, ".wts", "other")
    g(p, "worktree", "add", "-q", "--detach", other)
    os.utime(os.path.join(other, ".git"), (old, old))
    run(["claim", ".wts/other/x.py"], p, "sB")
    open(os.path.join(other, "x.py"), "w").write("x\n")
    code, out = run(["worktrees"], p)
    check("owner from a claim under the worktree; dirty is not prunable",
          "%s\n    owner session sB, branch (detached), merged, dirty" % other in out and "PRUNABLE " + other not in out, out)

    st = docket.load_state(p)
    up = docket.upkeep(p, "sA", st) or ""
    check("the owner's upkeep nudges it to remove the prunable worktree",
          "Your worktree %s is merged and pushed: git worktree remove %s" % (wt, wt) in up, up)
    check("at most hourly", wt not in (docket.upkeep(p, "sA", st) or ""))
    check("not another session's", wt not in (docket.upkeep(p, "sB", st) or ""))

    before = json.load(open(os.path.join(p, ".docket", "state.json"), encoding="utf-8"))
    run(["rebuild"], p)
    after = json.load(open(os.path.join(p, ".docket", "state.json"), encoding="utf-8"))
    before.pop("index", None), after.pop("index", None)
    check("rebuild reproduces state with worktrees", before == after)


if __name__ == "__main__":
    sys.exit(main())
