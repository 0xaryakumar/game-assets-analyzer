# codebase-measure-kit

Measures one git repository **on your own machine** and writes a small set of numeric report files. You review them, then send them back. Nothing is uploaded by the tool itself.

> **Confidential.** This kit is shared with you for this engagement only. Please do not redistribute it.

## What you need

- Python 3.10 or newer
- `git` on your PATH
- The `claude` CLI (Claude Code) installed and signed in with your own account. Two of the measurements use it, and every report needs them, so there is no mode that skips them. (`codex` is also supported via `--provider codex --model <name>`.)
- A **fresh, disposable clone** of each repository to measure (see "Before you run")

## Install

Clone this repo straight into your Claude skills folder, using this exact folder name:

```bash
git clone <THIS-REPO-URL> ~/.claude/skills/repo-quality-evaluation-measure-ext
pip install -r ~/.claude/skills/repo-quality-evaluation-measure-ext/requirements.txt
```

## Before you run

Point the tool at a **fresh clone**, not the working copy you develop in. By default the run executes the project's own install, build and test commands and leaves the checkout modified.

```bash
git clone <YOUR-REPO-URL> ~/measure/first-repo
```

## Run

**Option A: ask Claude.** Start `claude` and say:

```
Use the repo-quality-evaluation-measure-ext skill to measure each of
these repositories, each into its own folder under ./out named after
the repository: ~/measure/first-repo, ~/measure/second-repo
```

**Option B: run it directly**, one output folder per repository (every run writes the same filenames):

```bash
python ~/.claude/skills/repo-quality-evaluation-measure-ext/measure.py \
    ~/measure/first-repo --out ./out/first-repo
```

The run prints an estimate before it starts. One repository is capped at 2.5 hours (`--budget-seconds`); most finish far sooner. Anything the budget does not reach is reported as null with a reason, never as a low score.

## Review before you send

Every run ends with a plain-language review of what is in the files. To see every field and value:

```bash
python ~/.claude/skills/repo-quality-evaluation-measure-ext/measure.py \
    ~/measure/first-repo --out ./out/first-repo --review
```

## Send back

```
out/
 |-- first-repo/
 |    |-- measurement.json            <- required
 |    |-- codebase_repo_mining.json   <- required
 |    |-- codebase_repos.json
 |    '-- codebase_repos.csv
 '-- second-repo/
      '-- ...the same files
```

Send the whole `out` folder (or a zip of it) back to Zero Latitude Labs. Please send the parent `out` folder, not a single repository's folder.

## What leaves your machine, and what doesn't

**In the report files:** numbers, booleans, fixed-vocabulary labels, content digests, and one-line descriptions of the *shape* of engineering work (for example, "add cursor pagination to a list endpoint"). Exactly two names: the repository's own name (from the `origin` remote) and the company it belongs to. No source code, file paths, author names or emails, commit messages, branch or tag names. The tool refuses to write any field that is not on its declared allowlist.

**During the run (not in the files):**

- **Model lanes.** The two model-assisted measurements show your source and git history to *your own* Claude account, exactly as a normal Claude Code session would. The agent gets read-only tools only (`Read`, `Grep`, `Glob`): no shell. Settings committed to the repository (hooks, `CLAUDE.md`, MCP servers) are ignored, and no session transcript is written to disk.
- **Build probe.** By default the tool installs dependencies, builds, and runs the test suite using the repository's own commands. This fetches from package registries and runs repository-authored install scripts, in a child process with a scratch `HOME` and no credentials. The checkout is modified, which is why a disposable clone is required. `--build none` skips this and reports those measurements as null; `--build discover` skips running the suite.
- **Anything committed to the repo**, including an accidentally committed credential, is visible to your provider during the model lanes. The tool does not scan for secrets and does not record any.

The tool opens no network connection of its own. `references/client-runbook.md` has the full detail and a one-command check for each claim above.

## If a run fails

Send the last 20 lines of terminal output, your Python version, and whether `git` and `claude` are on your PATH.

## Repository layout

| Path | Purpose |
|---|---|
| `measure.py` | Entry point |
| `collectors/` | Deterministic collectors, the build probe, the allowlist and redaction layers |
| `miners/` | Task-type mining lane |
| `references/` | `schema.md` (field schema) and `client-runbook.md` (security detail) |
| `SKILL.md` | Claude Code skill definition and full option reference |
