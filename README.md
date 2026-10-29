# Docket

**An offline, in-repo journal and work index for Claude Code sessions and subagents.**

Run two or three Claude Code sessions at once, each spawning subagents, and you lose track of who
planned what, what was decided and why, and what was left half-done. Docket keeps that record
in a `.docket/` folder in your project, gives you a live journal to read it in, and makes the next
session build on earlier work instead of starting over. It is careful never to trust that work blindly.

- **A written record per session.** Plans, decisions (with what was rejected), sub-agent outputs,
  summaries and a rolling brief, read like documents in an offline HTML journal.
- **A work index.** Work is grouped into typed items in a tree (`Faster builds › Engine optimizations`).
  When a session gets a task, it is shown pointers to related earlier work before it starts.
- **Nothing left behind.** Unfinished tasks from earlier sessions come with ids, and the next
  session has to adopt, resolve or drop each one; a drop needs a reason.
- **Resistant to context poisoning.** Facts need evidence and store hashes of the files they cite.
  When the code changes they show as STALE. Everything else is labelled as an unverified claim.
- **Live conflict warnings.** Two sessions working on the same item at once are told about each other.

No server, no dependencies: Python 3 standard library and one static HTML file.

## Install

```bash
git clone https://github.com/<you>/docket-skill ~/.claude/skills/docket
python3 ~/.claude/skills/docket/scripts/install.py            # hooks for every project
# or, for one repo only:
cd your-repo && python3 ~/.claude/skills/docket/scripts/install.py --project
```

Start a new `claude` session, then open `./.docket/index.html` in a browser, or run
`python3 ~/.claude/skills/docket/scripts/docket.py open`. Windows: use `python` instead of `python3`.

Remove the hooks with `install.py --uninstall`. Turn Docket off for one session with
`DOCKET_DISABLE=1 claude`, or name a session up front with `DOCKET_NAME="auth refactor" claude`.

## What gets recorded

| Automatically, by hooks | By the agents, following the skill |
|---|---|
| session start and end, "waiting for you" | plans: goal and steps |
| every prompt | decisions, why, and what was rejected |
| TodoWrite / TaskCreate / TaskUpdate task lists | facts, with evidence (file:line or a command) |
| plan-mode plans | the rolling brief: now, done, next, blocked |
| edited files, with hashes | blockers, reviews, summaries |
| sub-agent spawn, brief, and final output | adopt / resolve / drop of pending tasks |

The hooks also inject the exact logging command into each session's and each sub-agent's context,
with the session id and agent name filled in.

## The work index

```bash
docket.py search "token expiry"              # find earlier work
docket.py show W-0003                        # read a work page, with trust re-checked live
docket.py check W-0003                       # re-hash cited files; lists STALE facts
docket.py work attach W-0003                 # continue it from this session
docket.py work new "Gate optimizations" --parent W-0002
docket.py work move W-0005 W-0002            # fix the structure any time
docket.py pending W-0003                     # what earlier sessions left unfinished
docket.py adopt T-2ca1f8                     # take it on; then it goes on your task list
docket.py drop N-523263 --reason "already removed in 91ab"
docket.py work list                          # the whole index, by area and by type
```

Each work item gets a Markdown page in `.docket/work/`, plus a line in `.docket/work/INDEX.md`.
Agents can read these directly.

## Agents never collide

Parallel sessions and subagents collide in two places, the same file and the same record. Both
writes are conditional and decided under one lock, the way GitLoom serializes per namespace and
uses compare-and-swap as the backstop:

- **File leases.** An agent's first edit of a file takes a lease on it, checked by a `PreToolUse`
  hook *before* the edit runs. Another live agent's edit is denied with who holds it and why.
  `docket.py claim src/auth/` reserves an area up front; `--steal --reason` takes one over and
  logs it. Leases end when the holder's session or subagent stops, or its process dies.
- **Compare-and-swap on the record.** Each work item has a rev. `log … --expect <rev>` is refused
  with exit code 3 and a list of what changed if another session wrote since that read.
- **Conditional create.** New work-item ids and titles are allocated under the lock, so two
  agents can't create the same item.
- **Lock ownership.** The lock records its owner; a dead owner's lock is freed at once, and no
  one removes a lock they don't hold.

`DOCKET_LEASES=warn` turns denials into warnings; `off` disables leases.

## Agents talk to each other

Parallel sessions can't see each other's context, so docket carries mail between them, the way
[mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail) does for MCP agents, but
through hooks with no server:

- `msg <session|W-xxxx|all> "…"` writes to one session (by name or id), everyone attached to a
  work item, or every session. `reply <id>` threads it.
- `--about "build speed"` routes to whichever open work item owns the topic. `--kind fyi`
  makes the owner aware; `finding` reports a cause you already found; `ask` hands the problem
  over and is tracked as a pending task on their item. `--attach build.log` hands over files,
  keeping the tail of big logs.
- `post "…" [--pin]` puts a notice on the project board: shared machines, changed baselines,
  rules the user set. Pinned posts are shown to every new session.
- Unread mail is injected with the next prompt and after any tool call, so a session mid-run gets
  it too, then marked read. A two-stat check keeps that cheap when nothing is waiting.
- Idle sessions are reached too: before stopping, a session starts `docket.py listen` in the
  background (the Stop hook asks it to when other sessions are live). The listener exits when mail
  arrives, and Claude Code wakes the session on its exit. `DOCKET_LISTEN=off` turns the nudge off.
- Mail is labelled as notes from a colleague, not instructions, and instruction-like text is
  flagged like any other docket text.

The journal's **Board** page shows pinned notices, threads and messages with read receipts.

## Protects the machine

Many sessions, subagents and builds on one machine can exhaust memory and, once swap fills the
disk, force a restart. Before every shell command and agent spawn docket checks memory pressure
and free disk. When it's critical, new agents and heavy commands are refused (freeing memory
still works) and every session is told. When it's tight, heavy jobs and extra subagents only get a
warning, since lag is acceptable. `docket.py mem` shows the biggest processes.

## Directives from the user

Start any prompt line with `@all` and it becomes a directive every session and agent must follow:
`@all limit your subagents to 4 parallel`, `@all every test must report FP, FN and join accuracy
on unseen repos`. Live sessions get it mid-turn, subagents get it at start, and each prompt
carries a short reminder. Subagent limits are enforced. Agents can't invent or drop directives.

## A standing goal, divided between sessions

`docket.py goal set "<the user's words>" --autonomous` gives every session and agent the user's
goal, plus working rules:

- **Coordinate:** agree a split on the goal thread, then each session takes one lane.
- **Decide:** don't wait for permission.
- **Delegate:** spawn subagents inside your lane.
- **Doubt:** critique plans and results, and measure on inputs you didn't tune on.
- **Never sit idle:** run long jobs in the background instead of fixed sleeps, and post shared
  notices before waiting.
- **Report:** update each other with numbers.
- **Audit:** check tasks regularly.
- **Ship:** commit and merge.

The goal must come from a prompt the user actually typed. Sessions holding a lane are kept working by the Stop hook until the goal is
met or they log a real blocker (capped at 10 turns in a row). `audit` lists tasks nobody owns,
stale ones, ones marked done without evidence, and items whose tasks are all finished; `reopen`
puts back a task that was marked done but isn't.

## The record is in git

Like [git-bug](https://github.com/git-bug/git-bug) and GitLoom, the record lives in git:
`events.jsonl` (split by day) and the work pages are committed after every turn to
`refs/docket/log`. That ref sits outside your branches, so it never appears in `main`, PRs or
`git status`. You get history and diffs of every work page, and a wiped `.docket/` is restored by
`docket.py sync`.

`docket.py sync --remote origin` shares it across machines; after that every turn pulls and
pushes in the background. Events are append-only with unique ids, so merging is a union. The
pushed log wins, and a W-id two machines both created is renumbered on the one that hadn't pushed
yet (`RENUMBERED W-a -> W-b`). `DOCKET_GIT=off` turns syncing off.

## Safeguards against context poisoning

A wrong fact in shared memory gets repeated by every session that reads it, and each step that
builds on it still looks like it succeeded. Docket treats its own record as suspect:

- Facts require evidence and store hashes of the files they cite. If those files change, the fact
  shows as STALE until someone re-checks it against the code.
- Plans, decisions, summaries and outputs are labelled as unverified claims.
- The record is append-only. Corrections use `--supersedes`, so you can see what was believed and when.
- Earlier work reaches a new session as short pointers, never pasted bodies, inside a block
  labelled as notes rather than instructions.
- Instruction-like text in stored notes ("ignore previous instructions", `curl … | sh`) is marked
  `[flagged: …]`.
- Earlier work must be reviewed against the code, ideally by a fresh-context sub-agent, so the
  reviewer can't inherit the original session's mistakes. A session attached to work other
  sessions wrote can't edit files or adopt tasks until it has logged that review
  (`DOCKET_REVIEW=warn|off` to soften). Entries the review finds false are superseded, struck
  through and listed as corrected claims.

## Files

```
.docket/
  events.jsonl     append-only log; the only source of truth
  state.json       derived state (docket.py rebuild regenerates it)
  data.js          the state, for the viewer
  index.html       the journal; open it in any browser
  work/INDEX.md    the work index
  work/W-0001.md   one page per work item
```

`.docket/` comes with its own `.gitignore`, so it is never committed to your branches. Its
history lives on `refs/docket/log` instead (see above).

## Viewer

`index.html` is a single file with no dependencies. It reads `data.js` by re-injecting a script tag
every 2 seconds, which works over `file://` where `fetch` does not. Your place on the page survives
refreshes. Light and dark themes, down to phone width.

## Prior art

Nothing we found combines a work index, evidence-checked facts and mandatory task handoff, but
each of these does part of it well:

- [slipstream](https://github.com/sarmakska/slipstream): per-project hook logging, resume briefs and
  a live localhost dashboard.
- [bettermemory](https://github.com/0Mattias/bettermemory) and
  [verified-repo-memory-mcp](https://github.com/cognitivemyriad/verified-repo-memory-mcp): memories
  re-checked against the code and marked stale. Docket's fact hashing follows the same idea.
- [Beads](https://github.com/steveyegge/beads): hierarchical, claimable issues for agents, planned
  up front rather than built from what sessions did.
- [claude-mem](https://docs.claude-mem.ai): cross-session context injection from a searchable store.
- [claude-code-log](https://github.com/daaain/claude-code-log): static HTML from Claude Code transcripts.
- [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail): inboxes, threads and file
  leases for coding agents over an MCP server, archived in git. Docket's messages follow its model.
- [git-bug](https://github.com/git-bug/git-bug): issues stored in git objects on their own refs and
  pushed and pulled like code. Docket's `refs/docket/log` is the same idea.

Background: [How contexts fail](https://dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html),
[OWASP ASI06: memory and context poisoning](https://www.pointguardai.com/glossary/owasp-asi06-memory-and-context-poisoning).

## Contributing

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). By contributing, you agree
that your work is licensed under the MIT License.

## License

[MIT](LICENSE). Docket is an independent project, not affiliated with or endorsed by Anthropic.
Claude and Claude Code are trademarks of Anthropic.
