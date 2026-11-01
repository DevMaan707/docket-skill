<!-- Adapted for docket from garrytan/gstack, plan-ceo-review/SKILL.md (Step 0)
     (https://github.com/garrytan/gstack). MIT License, Copyright (c) 2026 Garry Tan. -->
# Premise check (before a plan)

Answer these in a few lines at the top of your `plan` entry. If an answer is "I don't know",
that's the first thing to find out, or to ask the user (see the clarify rule in SKILL.md).

1. **The real problem.** What pain does this remove, for whom? Does the plan fix the pain directly
   or only a proxy for it?
2. **The outcome.** What is observably true when it's done? Make it checkable (a test, a metric, a
   command and its output).
3. **The cost of doing nothing.** If nobody builds this, what happens? If the answer is "not much",
   say so and stop.
4. **The smallest version.** The minimum change that delivers the outcome. Flag work that can be
   deferred without blocking it. More than ~8 files or 2 new modules: challenge whether fewer
   moving parts do the same.
5. **Reuse map.** Map each sub-problem to code that already exists (this repo, stdlib, installed
   dependencies) and to prior work on the docket (`$B search`, dead ends, refuted hypotheses). For
   anything you rebuild, say why extending the existing path is worse.
6. **Alternatives.** At least: A) the requested plan, B) the smallest scoped alternative, C) a
   larger approach only with evidence it pays off. Log the pick as a `decision` with the others
   in `--rejected`.
7. **Scope mode.** Pick one and say it:
   - **Expand:** a new product or system; propose additions, the user opts into each.
   - **Selective:** added capability; hold scope, offer each expansion with effort and risk.
   - **Hold:** a fix or refactor; keep scope, trace failures, edge cases, error paths, tests.
   - **Reduce:** strip to the essential core; cut only with the user's approval.

Every scope change needs the user's approval. Accepted additions go into the plan; deferred ones
become pending tasks on the work item (or a new work item), not a separate TODO file. Rejected ones
go under "Not in scope" in the plan. If the project has a constitution (`$B constitution`), check
the plan against it and cite the principles it touches (C-1, C-2, ...).
