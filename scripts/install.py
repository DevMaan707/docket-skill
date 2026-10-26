#!/usr/bin/env python3
"""Wire docket's hooks into Claude Code settings.

  python3 install.py              # user-wide: ~/.claude/settings.json (every project)
  python3 install.py --project    # only this repo: ./.claude/settings.json
  python3 install.py --uninstall  # remove the hooks again (add --project for repo)

Existing settings are kept; a .bak copy is written first. Safe to re-run.
"""
import argparse
import json
import os
import shutil
import sys

BOARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docket.py")
MARK = "docket.py\" hook"
OLD_MARKS = ("board.py\" hook",)  # installs from before the rename (agent-board)

EVENTS = [
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", "Agent|Task"),
    ("PostToolUse", "TodoWrite|TaskCreate|TaskUpdate|ExitPlanMode|Edit|Write|MultiEdit|NotebookEdit"),
    ("SubagentStart", None),
    ("SubagentStop", None),
    ("Stop", None),
    ("SessionEnd", None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()

    path = (os.path.join(os.getcwd(), ".claude", "settings.json") if a.project
            else os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    settings = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except ValueError:
                sys.exit("Could not parse %s; fix it first." % path)
        shutil.copyfile(path, path + ".bak")

    hooks = settings.setdefault("hooks", {})
    # drop any earlier docket entries so re-running doesn't duplicate
    for ev in list(hooks):
        groups = []
        for g in hooks[ev]:
            g = dict(g, hooks=[h for h in g.get("hooks", []) if MARK not in h.get("command", "") and not any(m in h.get("command", "") for m in OLD_MARKS)])
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]

    if not a.uninstall:
        cmd = '"%s" "%s" hook' % (sys.executable, BOARD)
        for ev, matcher in EVENTS:
            g = {"hooks": [{"type": "command", "command": cmd, "timeout": 10}]}
            if matcher:
                g["matcher"] = matcher
            hooks.setdefault(ev, []).append(g)
    if not hooks:
        settings.pop("hooks")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print(("Removed docket hooks from " if a.uninstall else "Installed docket hooks in ") + path)
    if not a.uninstall:
        print("Start a new `claude` session; the board appears at ./.docket/index.html")


if __name__ == "__main__":
    main()
