# Contributing to Docket

Thanks for helping. A few ground rules keep Docket easy to install and safe to trust.

## Principles

- **Standard library only.** `docket.py` and `install.py` must run on a stock Python 3.8+ with no
  `pip install`. The viewer is one HTML file with no external scripts, fonts or network calls.
- **Never break Claude Code.** The hook entry point must exit 0 and stay fast, even when the record
  is corrupt or missing. Problems go to stderr.
- **`events.jsonl` is the only source of truth.** Everything else (state, pages, index, `data.js`)
  must be rebuildable with `docket.py rebuild` and come out identical.
- **Don't weaken the trust model.** Facts need evidence, history stays append-only, and injected
  context stays labelled as unverified notes. Changes that loosen these need a clear reason in the PR.

## Development

```bash
python3 tests/smoke_test.py      # runs the end-to-end scenario in a temp folder
```

The smoke test simulates Claude Code hook events (two sessions, a sub-agent, file drift, a live
conflict, pending-task handoff) and checks the results. Add a case for any behaviour you change.

To see the viewer, run the test with `--keep` and open the printed `index.html` path.

## Pull requests

- Open an issue first for larger changes, so we can agree on the approach.
- Keep PRs focused, and describe how you tested them.
- If you change hook handling, say which Claude Code version you tested against; hook payloads
  change between releases.

By contributing, you agree that your work is licensed under the MIT License.
