# Project guide for Claude Code

Grey-box model of locomotion: a half-centre central pattern generator (CPG)
combined with a machine-learning component, fitted to real movement data.

## Reporting findings (required)

Every time you learn something worth keeping, record it with the findings API
**before** moving on. That includes results, negative results ("X did not
work"), bugs that changed earlier numbers, and design decisions.

```bash
python tools/findings.py add \
  --title "<one-line claim, phrased as what was found>" \
  --type result|negative|bug|decision|idea|question \
  --summary "<2-4 sentences: what you did, what you saw, how confident you are>" \
  --metric key=value            # repeat; numbers only where possible
  --tag <topic>                 # repeat; e.g. half-centre, ml, data, xenopus
  --evidence <path/in/repo>     # repeat; figure, log, results file
  --details "<method, parameters, caveats>"   # or --details-file notes.md
  --next "<what to try next>" \
  --commit --push
```

Rules:
- One finding = one claim. Split multi-part results into several findings.
- Status starts as `tentative`. Only mark `confirmed` after a replication
  (different seed or held-out data): `python tools/findings.py status F-0007 confirmed --commit --push`
- If a new result replaces an older one, pass `--supersedes F-000X`.
- Save figures/logs into the repo (e.g. `figures/`, `results/`) and commit them
  **before** logging, so `--evidence` paths and `code_version` point at real files.
- `code_version` ending in `-dirty` means the code was not committed. Commit
  code first, then log the finding.
- Check `findings/INDEX.md` at the start of a session to see what is known.
- Never edit `findings/INDEX.md` by hand; it is regenerated.

## Commits and privacy (public repo)

- Do NOT add `Co-Authored-By`, "Generated with Claude Code", or any AI
  attribution lines to commits, PRs or files. Commits are authored by the
  repo owner only.
- Never commit personal information (names, emails, addresses, student IDs,
  local file paths containing a username), credentials, API keys or `.env` files.
- Never commit raw third-party datasets unless their licence allows it; commit
  a download script and a citation instead.
