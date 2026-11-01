<!-- Adapted for docket from garrytan/gstack, review/checklist.md and review/SKILL.md
     (https://github.com/garrytan/gstack). MIT License, Copyright (c) 2026 Garry Tan. -->
# Review checklist

Review the diff against its base (`git diff <base>...`), plus uncommitted files. Cite `file:line`
for every finding and suggest the fix. Flag only real problems. Be terse: one line for the
problem, one for the fix; no preamble, no "looks good overall". Record the result on the docket:
`$B log review "<verdict>" --verdict sound|partial|wrong -b "<findings>"`, superseding any entry
the review proved false.

## Two passes

**Pass 1, critical (run first):**
- **Data safety:** string-built SQL, check-then-set races that should be atomic, writes that skip
  validation, N+1 queries on hot paths.
- **Concurrency:** read-check-write without a unique constraint, find-or-create without a unique
  index, status transitions that aren't `WHERE old_status = ...`. Parallel sessions are concurrent
  writers too.
- **Trust boundaries:** LLM or user output written to storage, mailers, URLs or shells without
  validation; unsafe HTML rendering; `shell=True` or `os.system` with interpolation;
  `eval`/`exec` on generated code.
- **Enum and value completeness:** a new status, type or accepted input. Read (not just grep)
  every consumer that switches on, filters or displays it; check allowlists and `if/elif` chains.
  The broken code is usually outside the diff.
- **Gate integrity:** a test removed or skipped, a threshold or timeout relaxed, a snapshot
  changed without its test, a swallowed exception. Ask: does this silence the failure it was added
  for, or is it justified by a measurement visible in the diff? Gate findings always go to the
  user, never auto-fixed.

**Pass 2, informational:** sync calls in async code, wrong column or field names, prompt text that
lists tools that aren't wired up, shortcut implementations where the complete version is cheap,
time-window mismatches, tests that assert on wall-clock time, type changes across serialization
boundaries, CI and release config.

## Sideways sweep (every finding)

A finding is a defect class, not a line.
- **Siblings:** grep the same pattern at every other entry point (commands, hooks, routes, workers,
  cron) and read each match. Rate on the worst sibling; list them under one finding.
- **Always critical:** data loss, a trust-boundary bypass (auth, sandbox, redaction, consent
  skipped), uncapped spend (a paid call or retry loop with no cap). Never downgraded.
- **A new cache in front of a guarded call:** name every check a hit skips.
- **A changed function with parity claims:** find its twins (mirrored helpers, docstrings, parity
  tests) and flag each one left unchanged.
- **A test-only flake fix** (timeout, retry, looser assertion) without numbers is a gate finding.

## Severity

- **blocker:** the intended case is wrong: a test would fail, production breaks, data or secrets
  are lost. Fix before landing.
- **should:** a real bug a caller will hit. Fix it if it's in the diff; otherwise file it (a
  pending task, or `msg --about` to the owner's work item).
- **nit:** style, naming, wording, "I'd have done it differently". A note; never a reason for
  another review round.

## Fix first

Mechanical fixes a senior engineer would apply without discussion (dead code, stale comments,
magic numbers, path mismatches, unused variables): fix them, if you hold the file's lease. Anything
reasonable engineers could disagree on (security, races, design, removing behaviour, fixes over
~20 lines, user-visible changes, gates): ask, batched into one question with a recommended option
(`$B msg <owner or user> "..." --kind ask`). In another session's files, send the finding to its
owner instead of editing.

## Verify claims

Every safety claim cites the line that proves it ("escaped at `views.py:88`"); read and cite any
handling code you rely on; name the test file and function for coverage claims. "This looks fine"
is not evidence. Unverified: say so.

## Don't flag

**Zero findings is a valid outcome.** If the diff is clean, say so. Skip: harmless redundancy that
aids reading, "add a comment explaining this constant", "this assertion could be tighter" when it
covers the behaviour, consistency-only changes, edge cases the input can't produce, anything the
diff already handles, "consider error handling" where a caller already owns errors, "too long" for
tables and exhaustive switches, hardcoded values in tests, non-crypto randomness.
