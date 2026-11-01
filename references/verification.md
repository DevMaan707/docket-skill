<!-- Adapted for docket from obra/superpowers, skills/verification-before-completion/SKILL.md
     (https://github.com/obra/superpowers). MIT License, Copyright (c) 2025 Jesse Vincent. -->
# Verification before completion

**Evidence before claims, always.** If you haven't run the check in this turn, you can't say it
passes. This covers every "done", "fixed", "passing", a `summary`, a `fact`, `resolve <task>`,
`work status ... done`, a commit and a PR, and any paraphrase that implies success.

## The gate

1. **Identify** the command that proves the claim.
2. **Run** it, fresh and complete.
3. **Read** the whole output: exit code, failure count.
4. **Does it confirm the claim?** No: state the real status with the evidence. Yes: state the
   claim *with* the evidence.
5. Only then claim it, and record it: `$B log fact "<claim>" --evidence "<command: result>"`,
   `$B resolve <id> --reason "<commit, test or gate result>"`.

## Claim → evidence

| Claim | Requires | Not enough |
|---|---|---|
| Tests pass | The test command's output: 0 failures | An earlier run, "should pass" |
| Linter clean | Linter output: 0 errors | A partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look fine |
| Bug fixed | The original symptom, re-run: gone | Code changed, assumed fixed |
| Regression test works | Red-green: fails without the fix, passes with it | Passes once |
| Agent finished | The diff shows the changes | The agent's report says "success" |
| Another session's work is done | Its code and tests, checked by you | Its brief or summary on the docket |
| Requirements met | Line-by-line checklist against the request | Tests passing |

## Red flags: stop

- "Should", "probably", "seems to"
- "Great!", "Done!" before the check ran
- About to commit, push, open a PR or close a work item without a check
- Trusting a subagent's or another session's report (the record is claims; the code is truth)
- Partial verification; "just this once"

## Patterns

- Tests: run the command, see `34/34 pass`, then say "all tests pass".
- Regression test: write, run (pass), revert the fix, run (**must fail**), restore, run (pass).
- Requirements: re-read the plan, make a checklist, verify each item, report gaps or completion.
- Delegation: the agent reports success, you check the diff, verify, then report the real state.
