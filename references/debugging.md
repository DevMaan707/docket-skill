<!-- Adapted for docket from obra/superpowers, skills/systematic-debugging/SKILL.md
     (https://github.com/obra/superpowers). MIT License, Copyright (c) 2025 Jesse Vincent. -->
# Systematic debugging

**No fix without a root cause.** A symptom fix is a failure, even when the test goes green.
Use this for every bug, test failure, build break, performance problem or surprise, and most of
all when you are in a hurry or "one quick fix" looks obvious.

Before you start, check what other sessions already ruled out: `$B show W-xxxx` lists the item's
**Hypotheses** (refuted ones struck through) and **Dead ends**. Don't re-test a refuted cause
without new evidence.

## Phase 1: Root cause investigation

1. **Read the error completely.** The full stack trace, line numbers, codes, warnings.
2. **Reproduce it reliably.** Exact steps. Not reproducible: gather more data, don't guess.
3. **Check what changed.** `git log`, `git diff`, new dependencies, config, environment. Also the
   docket: another session's recent change (`$B search`, the board) may be the cause; if so,
   message its owner (`$B msg --about "<topic>" --kind finding|ask`) instead of fixing their files.
4. **Multi-component systems:** instrument each boundary (what enters, what leaves, which env and
   config arrive), run once, and let the evidence say *which* layer breaks before you dig into it.
5. **Trace the data backwards.** Where does the bad value come from? Who called this with it? Keep
   going up until you reach the source. Fix at the source.

## Phase 2: Pattern analysis

1. Find similar code in this repo that works.
2. If you are applying a pattern, read the reference implementation completely, not skimmed.
3. List every difference between working and broken, however small.
4. Name the dependencies: other components, settings, environment, assumptions.

## Phase 3: Hypothesis and test

1. **One hypothesis at a time,** stated as "X is the root cause because Y". Log it before you test
   it, so other sessions see it:
   `$B log hypothesis "X causes Y" --work W-xxxx -b "why I think so"`
2. **Test it with the smallest possible change.** One variable at a time.
3. **Record the verdict with evidence,** confirmed or refuted:
   `$B log hypothesis "X causes Y" --supersedes <id> --refuted --evidence "<command and result>"`
   A refuted hypothesis is as valuable as a confirmed one: it stops the next session from
   spending an hour on the same idea.
4. Refuted: form a **new** hypothesis. Don't pile more changes on top.
5. Don't know? Say "I don't understand X". Research, or ask (`$B msg user "..." --kind ask`).

## Phase 4: Implementation

1. **Write a failing test first,** the simplest reproduction (a one-off script if there's no
   framework).
2. **One fix,** for the root cause. No "while I'm here" changes, no bundled refactors.
3. **Verify** (see verification.md): the test passes, nothing else broke, the original symptom is
   gone.
4. **The fix didn't work?** Count your attempts. Under 3: back to Phase 1 with what you learned.
5. **3 failed fixes: stop and question the architecture.** Signs: each fix exposes new shared state
   or coupling somewhere else, fixes need "massive refactoring", each fix makes new symptoms. That
   is not a failed hypothesis, it's a wrong design. Log a `blocker` or ask the user before fix #4.

## Red flags: stop, back to Phase 1

- "Quick fix for now, investigate later" / "just try changing X and see"
- Several changes at once, then running the tests
- "It's probably X, let me fix that" without evidence
- Proposing fixes before tracing the data flow
- "One more fix attempt" after two failed ones
- Each fix reveals a new problem in a different place

The user saying "stop guessing", "is that not happening?" or "we're stuck?" means the same.

| Excuse | Reality |
|---|---|
| "It's simple, no process needed" | Simple bugs have root causes too; the process is fast for them. |
| "Emergency, no time" | Systematic is faster than guess-and-check thrashing. |
| "I'll write the test after the fix works" | Untested fixes don't stick. |
| "Multiple fixes at once saves time" | You can't tell which worked, and you add bugs. |
| "I see the problem" | Seeing a symptom isn't knowing the cause. |

## "No root cause"

If the investigation shows it's truly environmental, timing-dependent or external: record what you
investigated (hypotheses and dead ends on the docket), add handling (retry, timeout, clear error),
and logging for next time. Most "no root cause" cases are an unfinished investigation.
