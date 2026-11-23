---
name: codebase-measure-kit
description: >-
  MEASURE one repository on your own machine and write the privacy-preserving MEASURE-stage
  artifacts: the flat `codebase_repos` row, `measurement.json` and `codebase_repo_mining.json`.
  Every stat is deterministic except two model-assisted lanes, logic depth and task-type mining,
  which run a headless claude, codex or gemini CLI under your own provider account. Numbers leave,
  plus exactly two names: the repository's own and the company it belongs to. No path, author,
  branch or commit subject. The build probe installs, builds and runs the test suite by default, so
  run it against a clean, disposable clone. The skill uploads nothing and prints a review of
  everything in the artifact. Use for "measure this repo", "emit codebase_repos + measurement.json",
  "get the repo stats + logic depth", "privacy-preserving repo measurement".
---

# codebase-measure-kit

The MEASURE stage of the codebase-quality pipeline, external variant. It collects static tree stats, git
history stats, a repository classification, and two model-assisted lanes — logic depth (the material
census) and task-type mining — maps them onto the shared contract schema, holds every field to the
emission allowlist, and writes JSON + CSV. The GRADE stage is a separate skill.

**The artifact belongs to whoever ran this.** It is written to a local directory, this skill uploads
nothing, and it never deletes anything it produced. Every run ends with a plain-language REVIEW of
what is in the files: counts per kind, the digest, every model-written line in full, and the list of
things that are never collected and why. `--review` prints every field and its value.

One fact belongs next to that sentence rather than three pages after it. The model lanes show the
source and the development history to the operator's own provider during the run, which is a
disclosure the artifact's contents say nothing about. That is the disclosure; it is not accompanied
by a second copy anywhere. The provider CLI used to write a verbatim session transcript under
`~/.claude/projects/<slugged-path>/` — file bodies and `git show` output, roughly 200 KB for an
eight-line repository — and the model lanes now launch it with session persistence off, so nothing
is written outside the output directory the operator named.

## Scope and disclosures

MEASURE one repository and emit the privacy-preserving MEASURE-stage schema: the flat
`codebase_repos` row (38 fields plus the additions `build_ok`, `testable_at_head`, `capacity`), the
full `measurement.json` (`tree` / `git` / `classification` blocks, an additive `ext_signals` block,
and a `material` block), and `codebase_repo_mining.json`.

Every stat is deterministic except two model-assisted lanes. LOGIC DEPTH, via the material census,
returns a 0-6 logic-depth band, a self-containment score, and per-category counts of the substantial
minable material the repository holds. TASK-TYPE MINING sends a headless agent (claude, codex or
gemini) through the code and history to take a CENSUS of the task ideas the repository can support
-- every idea that clears the bar, up to `--mine-n` (default 150), each classified into one of four
task types -- emitted as a count per task type plus one `"<task_type>: <sentence>"` line per idea in
`mined_task_summaries`, each sentence describing the engineering SHAPE of the work and never a real
path, symbol or product. Both lanes always run, and a provider CLI that is not installed stops the
run before any work starts rather than becoming a silently unscored lane. Lanes run concurrently
(`--jobs`), so the wall clock is the slowest lane, and ONE REPOSITORY CANNOT EXCEED
`--budget-seconds` (default 9000, two and a half hours): a single monotonic deadline is shared by
every lane, the run prints its own estimate before it starts, and anything the budget does not reach
is reported null with a reason rather than truncated to a number.

EXTERNAL variant = privacy-preserving: numbers leave, and exactly TWO names leave -- the
repository's own (`real_repo_name`, from the `origin` remote, so the platform can tell which
repository a measurement describes) and the COMPANY the repository belongs to (`company_identity`,
read from licence and notice files, recurring copyright headers, the remote's organisation and
manifest organisation namespaces, so a broker's report says whose code it is about; `none` rather
than a guess when the tree names nobody, no score and no confidence number, and author email domains
and CI hostnames are deliberately not among the signals read). No path, author, branch or commit
subject.

An emission ALLOWLIST (`collectors/emit_allowlist.py`) declares every field that may be written and
the kind of value it may hold -- number, boolean, closed-vocabulary enum, content digest, or one
validated sentence -- and fails the run rather than emit anything undeclared; the redactor and leak
audit sit behind it as a backstop. Nothing searches the source for secret-shaped strings, and no
author name, address, commit message, branch or tag name, or file path is emitted.

THE RUN ITSELF DISCLOSES MORE THAN THE ARTIFACT DOES: both model lanes hand a headless agent the
working tree and a pre-computed development history, under the operator's own provider account, so
the source is seen by the provider even though none of it reaches the files. The agent has NO shell,
the provider CLI is launched with flags that make it ignore configuration committed to the
repository (hooks, CLAUDE.md, MCP servers), it writes no session transcript, and credential-shaped
files are withheld from the history by git pathspec.

Every run prints a REVIEW of exactly what is in the artifact (`--review` for every field) so the
repository owner can read it before deciding to send anything; this skill uploads nothing and
deletes nothing.

THE BUILD PROBE RUNS BY DEFAULT, AT LEVEL `full`: every invocation resolves dependencies, installs
and builds the project, asks its test runners to enumerate their tests, then RUNS the suite and
reads coverage, using the repository's OWN commands inside the target checkout, with scratch caches
and best-effort restoration -- so run it against a clean, disposable clone. A repository whose suite
outruns `--full-attempt-seconds` completes the measurement at `discover` instead, records that it
did, and reports the full-level index null with a reason rather than scored low; `--build discover`
pins the cheaper level and `--build none` is the escape hatch that leaves every executed measurement
NULL. The level that actually ran is recorded in the artifact and printed in the run's own review,
so a grade produced without a build -- or without a suite -- cannot be mistaken for one with it.

## Contract

`references/schema.md` is the field schema for this copy: it records every field, how the collectors
map onto it, and the null-vs-0 decisions. Read it before changing a field.

Upstream keeps a separate `SCHEMA.md` shared across the four codebase-quality skills. It is not part of
this zip, so references to it are deliberately not carried here — `references/schema.md` is the file
you have.

## Usage

    python measure.py <repo> --out <dir> [--sink json|csv|db] [--review] [--jobs N]
                       [--build [none|discover|full]] [--budget-seconds N]
                       [--build-budget-seconds N] [--full-attempt-seconds N]
                       [--timeout-build N] [--max-build-projects N]
                       [--top-files N] [--git-top N] [--threshold FLOAT]
                       [--provider claude|codex|gemini] [--model NAME]
                       [--census-timeout SECONDS]
                       [--mine-n N] [--mine-timeout SECONDS]

- `<repo>` — path to the git repository (or sub-tree) to measure. Read-only on the default path.
- `--out DIR` — **required.** Writes `codebase_repos.json`, `codebase_repos.csv`,
  `codebase_repo_mining.json`, and (unless `--sink csv`) `measurement.json`.
- `--sink {json,csv,db}` — `json` (default) writes the JSON docs and the CSV row; `csv` writes only
  the row files; `db` is a documented stub that raises `NotImplementedError`. The platform ingests
  the JSON/CSV; there is no direct DB writer here.
- `--build [none|discover|full]` — the deterministic environment probe. **It runs by default, at
  level `full`.** The project's own install, build and test commands execute in the target checkout;
  caches use scratch storage and known changes are restored best-effort. Use a clean, disposable
  clone or worktree. The default used to be off, on the argument that executing a repository's own
  code is the owner's decision — but the executed signals are the best-evidenced things this skill
  measures (`tests_discovered` correlates +0.156 with delivered tasks and the two runnability
  indices carry 22 of the rubric's 100 points), and a measurement nobody takes by default is a
  measurement that is usually missing. The disclosure moved to the front of this file instead.
  - `discover`: resolve dependencies, install, build, and ask the RUNNER to list its tests
    (`pytest --collect-only`, `cargo test -- --list`, `go test -list`, `jest --listTests`). That
    turns `install_ok`, `build_ok`, `tests_discovered` and the derived `discover_runnability`
    (0..3), plus the test framework and the package manager, from inferred into EXECUTED facts.
    Measured at 22.6s on `psf/requests` and 12.9s on `BurntSushi/ripgrep`, against 61.8s and 20.8s
    for `full`.
  - **`full` is the default**, and what bare `--build` means. It also executes the suite and reads
    coverage, which is what `observed_runnability` needs: band 4 of that index is the largest
    measured step in the corpus (4.26 mean delivered tasks against a flat 2.20) and is unreachable
    at any other level.
  - **THE FALLBACK.** A `full` run that does not finish inside `--full-attempt-seconds` completes
    at `discover` with what is left of the build reserve. It records `build_level: discover`,
    `build_level_requested: full` and a `build_level_fallback_reason`, keeps every discover-level
    executed fact, and reports `observed_runnability` **null with a reason** rather than a low band.
    So a slow repository yields a usable, comparable measurement instead of nothing — `A_discover`
    still scores and positive-weight coverage stays above the rubric's floor.
  - **IT RUNS THE RUNTIME THE REPOSITORY ASKED FOR.** `wrong_runtime` was 27 of the 417-repo
    corpus: repositories that failed because the probe ran the wrong interpreter. The probe now
    reads what the tree declares — `.nvmrc`, `.node-version`, package.json engines,
    `.python-version`, `requires-python`, `python_requires`, `go.mod`'s go directive,
    `rust-toolchain`, `.ruby-version`, `.tool-versions`, pom.xml compiler levels, a Gradle
    toolchain, `global.json` — and selects the installed version nearest the declared floor,
    reporting the ask beside the answer in `runtime_requested` and `runtime_used`. It only *moves*
    when the host default is disallowed, because switching runtimes is itself a way to break a
    working build. **Nothing is installed, and nothing outside the system toolchain is used**: a
    runtime living under your home directory (nvm, pyenv, asdf, mise, uv) is deliberately *not*
    selected here, because handing a repository's own install hook a path inside your home is a
    change to the boundary you agreed to. When the version a tree asks for is not on this machine,
    the lane is named in `runtime_lanes_unsatisfied` and every failure under it is attributed to
    the **runner** — so `build_ok` goes null with a reason instead of false, and the repository is
    not charged for the age of our toolchain.
  - **WHO OWNS AN ABSENT MEASUREMENT.** A repository that is itself the reason no suite ran — a
    build that genuinely fails, a project the runner looked at and found no tests in — scores a real
    0 or 1 on `observed_runnability` and that costs points, which is the signal. A run stopped by
    *our* limits — the clock, a language runtime absent from the host, an unreachable registry, a
    build verdict that could not be established across the tree — reports the index **null with a
    reason** and the dimension goes unscored. The probe decides this from the `attribution` every
    phase already carries, and writes the answer into `observed_runnability_reason`. Reading our
    absences as zeros is the arithmetic that once graded a repository which installed, built,
    discovered 441 tests and passed all 441 at 13.7 out of 100. No fallback is attempted for a
    repository-owned failure: a completed `full` record already holds every discover-level term.
- `--budget-seconds N` — the GLOBAL wall-clock budget for the run, shared by every lane. Default
  9000, two and a half hours, and it is the bound on one repository. Anything the budget does not
  reach is reported null with a reason.
- `--build-budget-seconds N` — the probe's reserved share of that budget, cumulative across every
  project root and every phase (default 1800). Reserved rather than left over, because the probe
  runs last and is the only lane that executes anything.
- `--full-attempt-seconds N` — how long a `--build full` run may take before the measurement is
  completed at `discover` with whatever is left of the build reserve (default 900). A **slice** of
  `--build-budget-seconds`, not a second budget: the full attempt and its fallback are two draws on
  one allowance, so `--budget-seconds` is unaffected and the 2.5 hour bound still holds.
- `--timeout-build N` — ceiling for ONE command inside the probe (default 900), always subordinate
  to the two budgets.
- `--max-build-projects N` — how many discovered project roots the probe may run commands in,
  largest first (default 8). The rest are reported `skipped_budget` with reason
  `project_cap_reached`; a silent cap reads as "we looked and found nothing".
- `--review` — print every emitted field and its value, grouped by kind, after writing. A shorter
  review is printed even without it.
- `--jobs N` — maximum lanes to run concurrently. Default 0, meaning one worker per lane, the whole
  fan-out at once. `--jobs 1` serialises the run, which is what to use on a machine with no spare
  cores. `--build` never overlaps anything: it mutates the tree the other lanes read, so it runs
  alone after they have all finished.
- `--top-files N` — largest-files profile depth for `repo_stats.py` (default 10).
- `--git-top N` — cap on each per-class commit list emitted by `git_stats.py` (default 1). Only the
  counts are consumed, so this just bounds subprocess output. Full-history tallies are unaffected.
- `--threshold FLOAT` — minimum normalized class confidence for `classify_repo.py` (default 0.18).
- `--provider {claude,codex,gemini}` — model CLI provider; default `claude`. A provider whose CLI is
  not installed stops the run with a one-line error before any measurement happens. There is no
  fallback to another provider.
- `--model NAME` — provider model id/alias. Claude defaults from `collectors/models.py` / `CMK_MODEL`;
  Codex and Gemini require an explicit model. `provider` / `model` in the
  artifact record what was REQUESTED; nothing ever substitutes another one, so they are also what
  was used whenever that lane's `scored` flag is true.
- `--census-timeout SECONDS` — ceiling for the census lane, retries and backoff spent out of it
  rather than on top of it. Default 14400 (four hours), a runaway backstop rather than a budget.
- `--mine-n N` — ceiling on how many task ideas the miner enumerates (default 150, raised from 40).
  The lane is a census, not a shortlist: every idea that clears the bar is listed, classified into
  one of the four task types, and each type's count is the length of its own list of sentences.
  The old 40 was sized against a 30-minute budget that no longer exists, and mined ideas are the
  most valuable thing this skill produces. Raising it cannot make a run exceed `--budget-seconds`;
  it only decides what the budget is spent on.
- `--mine-timeout SECONDS` — ceiling for the mining lane. Default 14400 (four hours), a runaway
  backstop on the same terms as `--census-timeout`.

Environment variables: `MEASURER_VERSION` (optional; stamped as `measurer_version`, default
`codebase-measure-kit@3`); `CMK_MODEL` (optional; default census model when `--model`
is absent). No secrets, tokens, or account IDs are read anywhere.

Also required outside pip: `git` on PATH. For the model-assisted lanes: the chosen provider CLI on
PATH and signed in — auth comes from the ambient environment and is never read, logged, or stored
here. A provider is required: there is no offline mode, because a report without the mining counts
cannot be scored. For `--build` only: whatever toolchain the target repository already declares.

`references/client-runbook.md` is the page to give a repository owner: the exact command, what is
read and what is executed, what leaves the machine, how long it takes, and how to verify each of
those claims with one command.

## How long it takes, and what the budget means here

**One repository cannot exceed `--budget-seconds`, default two and a half hours.** There is a
single monotonic deadline for the whole invocation and every lane draws from it: the two model
lanes are capped at what is left minus the build probe's reserve, and the probe is capped at that
reserve and divides it between its project roots itself. Independent lanes run concurrently, so
the wall clock is the slowest lane rather than the sum, and the two model lanes are the long poles.

The run says what it expects to cost before it starts —

    [plan] 2 project roots (python), 114 files in 22 directories scanned
    [plan] this looks like a 1 minute run against a 150 minute budget (rough, from repository size
           and project count): deterministic collectors 0 min, build probe 1 min

— and prints the per-lane wall-clock table at the end. When the estimate does not fit the budget,
the plan says so up front and names what will be cut, so a truncated run is never a surprise.

Nothing is silently truncated. `--census-timeout` and `--mine-timeout` are runaway backstops four
hours out rather than budgets; the budget above is what bounds the run. Whatever a budget or a
backstop stops records every measurement it owns as NULL with a reason — never a partial count,
never a zero, never a low band. The build probe reports project roots it did not reach as
`skipped_budget`, and `observed_runnability` goes null rather than summing terms nobody executed.
the external grader then marks that dimension unscored and the whole grade `grade_status: UNGRADED` /
`score_comparable: false`. An unmeasured repository is reported as unmeasured. It is never reported
as a poor one.

The bound is tested, not asserted: `tests/test_repo_quality_runtime_budget.py` builds a repository
with eleven project roots across eight ecosystems where every install and every test command hangs
forever, and measures that the probe still returns inside its budget with everything it did not
reach reported `skipped_budget` and null.

## Three states, three different answers

A count in this artifact is a measurement or it is null. The three cases are distinguishable by
design, because collapsing them is how our own failures became verdicts about someone's repository.

| what happened | counts | row `status` / `skip_reason` | how you can tell |
|---|---|---|---|
| every lane ran | numeric; `0` means measured-none | `measured` / null | no `skip_reason`, no `*_unavailable_reason` |
| a lane did not run | zeroed | `partial` / `llm_disabled` or `mine_disabled` | `skip_reason` names which |
| a lane could not finish | **null** | `partial` / `lanes_unavailable` | `mine_unavailable_reason` / `logic_depth_unavailable_reason` says why |
| a lane ran out of clock | **null** | `partial` / `lanes_timed_out` | `material.timed_out`, `census_failure_kind: timeout` |

The top-level `status` is `measured` only when everything ran. This is one deliberate step
stricter than the internal variant, which does not count an operator-deselected lane against the run:
the internal variant's row is read by our own orchestrator, which knows what it asked for, and this row is
read by a buyer, for whom `measured` on a record with no material measurement is a claim we have
not earned. `skip_reason` still separates "you turned it off" from "it broke".

## What it emits

- `codebase_repos.{json,csv}` — the flat promoted row (41 columns: 38 contract fields including
  legacy `quality_score`, plus `build_ok`, `testable_at_head`, `capacity`). Numbers, dates, enums,
  and public stack-name lists only; no repository-derived symbols.
- `measurement.json` — `measurer_version`, `measured_at`, `repo_digest`, `real_repo_name`,
  `company_identity`, `variant`, then the `tree` /
  `git` / `classification` blocks, the additive `ext_signals` block (`structure` from
  `code_structure.py`, `history` from `git_history.py`, `build` from `build_probe.py` when
  `--build`, `authenticity` from `authenticity.py`, and `sourcing` from `sourcing.py`: counts of
  AI-authored commits and merged pull requests, how many lines at HEAD are dated on or after
  2025-02-01, and whether the repository ships seed data for its own database), and the
  `material` block from `material_census.py`. When the census is scored the
  `material` block carries `logic_depth` (0-6), `self_contained` (0-4), per-category minable-ideas
  counts (`n_*`), `minable_ideas_total`, the `minable_ideas` sentences, `themes`, and `model`; when
  it is skipped or unavailable it carries `scored: false` plus `skip_reason` or
  `census_failure_kind` / `census_error_detail` / `logic_depth_unavailable_reason`. It also carries
  a numbers-only `task_type_counts` summary mirroring the mining counts.
- `codebase_repo_mining.json` — the task-type census: `repo_id` (= `fake_repo_name`),
  `measurer_version`, `provider`, `model`, `mined_at`, `total_candidates`, the per-task-type counts
  `n_net_new` / `n_agentic` / `n_bug_repair` / `n_repo_evolution`,
  `scored`, and `mined_task_summaries` — one `"<task_type>: <sentence>"` line per
  mined idea, for example
  `net_new: add cursor pagination to a list endpoint backed by a relational store`. Each type's
  count is the number of sentences carrying its tag, so the numbers can be audited by reading the
  evidence for them.

Every document passes the emission allowlist before it is written.

## Miners (`miners/`)

`agentic_miner.py`, with its `agent_io.py` helper, is the mining lane. `measure.py` runs it as a
fixed-argv, `shell=False` subprocess with `cwd = miners/`; the miner puts `collectors/` on its own
path so `candidates.py`, `history_brief.py` and `emit_allowlist.py` resolve to the single copy that
lives there. The miner spawns one headless agent that reads the code and full history and proposes
long-horizon task candidates, classifying each into one of the five declared task types;
`measure.py` keeps only the counts and the validated one-line summaries. The paths and symbols the
agent cited never reach an ext artifact.

The lane's verdict comes from the miner's own completion marker, not its exit status: a run that
looked and found nothing is a real, reportable zero, and a run that never finished looking is null.

## Collectors (`collectors/`)

The ported deterministic collectors (`repo_stats.py`, `git_stats.py`, `candidates.py`,
`classify_repo.py`) and ext's signal collectors (`code_structure.py`, `git_history.py`,
`build_probe.py`, `material_census.py`, `company_identity.py`, `redact.py`, `models.py`). The
deterministic collectors run
on their deterministic paths only: `code_structure` and `git_history` are called with agentic
disabled, and `build_probe` runs with `agentic=False`, so none of them invokes a model.
`material_census.py` is the census lane; it invokes the chosen provider CLI as a fixed-argv,
`shell=False` subprocess with auth from the environment, redacts and sentence-validates every
sentence, and degrades to an unscored result rather than crashing. `emit_allowlist.py` is the
emission boundary every document passes through before it is written. `git_stats.py`,
`git_history.py`, and `measure.py` call `git` with fixed argument lists and `shell=False`.

## Privacy guarantee

The rule is "do not acquire" rather than "redact carefully". `collectors/emit_allowlist.py` declares
every emittable field and the kind of value it may hold — number, boolean, closed-vocabulary enum,
content digest, or one validated sentence — validates map KEYS as well as values, and raises
`EmissionRefused`, writing nothing, on anything undeclared. Behind it, `redact.py` plus the
`audit_no_leak` write-boundary audit act as a backstop and raise `LeakDetected`.

Nothing in this skill searches a repository for secret-shaped strings, and no such string is ever
matched, counted, recorded or emitted. No author name or address, no commit subject or message, no
branch or tag name, and no file path is emitted. Those keys remain in the schema as null or empty,
and `--review` prints the reason for each.

**Exactly two names leave, and the first is the repository's own.** `real_repo_name` carries
`owner/name` as your `origin` remote spells it, read with `git config --get remote.origin.url`.
It is emitted so the platform can tell which repository a measurement describes: `repo_digest`
identifies the *tree*, which cannot answer that question. If there is no `origin` remote, or the
remote is a local filesystem path, the field is null and no name is emitted. `--review` prints the
value after writing and before you send. The display handle
`fake_repo_name = "repo-<repo_digest[:12]>"` is still emitted alongside it.

**The second is the company the repository belongs to.** `company_identity` carries a short
candidate list, at most three, each name tagged with the signal FAMILIES that asserted it, plus one
outcome: `confident` when two or more families agree, `uncertain` for one family or for families
that disagree, `none` when nothing usable was found. The four families are a root licence or notice
file, a copyright header that recurs across at least two source files, the organisation in your
`origin` URL, and an organisation NAMESPACE in a root manifest (an npm scope, a Composer vendor, a
Go module path, a Maven groupId, a publisher). It also carries an `industry` guess from your README
and your declared dependencies, as one word from our own list rather than any text of yours.

This is for the broker flow, where the code being measured belongs to a company that is not the
firm submitting it, and the firm confirms or corrects what the skill read. Five things it does not
do:

* **No manifest `author`, `authors` or `maintainers` field is read.** Those hold a person's name.
* **No author email domains**, and no config or CI hostnames, registry paths or cloud project
  names. Both are declared and permanently empty, with the reason, in the review.
* **No number.** No score, no hit count, no confidence percentage. The family names are the
  provenance: "read from your licence file".
* **`none` rather than a guess.** No remote, generic manifests and no copyright header is a normal
  answer, and the licence steward in a licence file's own boilerplate is refused by name, so a GPL
  repository is not reported as belonging to the Free Software Foundation.
* **Nothing is executed and nothing is written.** It reads root manifests, root licence files, your
  README and the first few kilobytes of a capped sample of source files, and skips vendored trees.

Nothing else of yours is named: no path, no author, no branch, no commit subject, and no
repository other than this one. Technology names (languages, frameworks, CI systems, package
managers) do leave, as the public stack facts described above -- those name the tools, not you.

Three things sit next to that guarantee rather than inside it, and the client runbook states all
three because a reviewer finds them in twenty minutes either way.

* `repo_digest` in `measure.py` hashes the bytes of every file in the tree, a committed `.env`
  included. Only the sha256 is emitted and no value is retained, but the bytes are read.
* `build_probe._declares_private_registry`, reached only under `--build` and only after a dependency
  install has already failed on an authentication error, reads registry-configuration markers from
  `.npmrc`, `.netrc`, `settings.xml`, `gradle.properties` and their siblings **inside the checkout**
  to decide whether the failure is the repository's or the operator's. It retains nothing and returns
  one boolean. It is a narrow, disclosed exception, not a scanner.
* The model lanes read the source and the history. Anything committed to either — including a
  committed credential — is disclosed to the operator's own provider on every run.

## What the run does on the operator's machine

Separate from what the artifact contains, and the part a security reviewer will ask about first.

Both model lanes launch the provider CLI with the checkout as its working directory and
`--allowedTools "Read Grep Glob"`. Four controls bound what that session can do, and all four
are enforced by the CLI rather than requested in a prompt:

* **No shell.** `--add-dir` bounds `Read`, `Grep` and `Glob` to the checkout and to the scratch
  directory holding the prepared history. `Bash` used to be granted and `--add-dir` never bounded
  it: the agent reached the operator's home directory on the first try, and what stopped it going
  further was the model declining, which is not a control. The history that grant existed for is
  computed by `collectors/history_brief.py` with a fixed read-only `git` argv — carrying
  `--no-textconv` and `--no-ext-diff`, because a repository's own `.git/config` can otherwise run a
  command through `git show` — and handed over as files.
* **The grant is the tool set, not a pre-approval.** `--allowedTools` pre-approves the tools it
  names and withholds nothing, and whether a call outside it is denied would otherwise depend on
  the mode the session starts in and on the operator's own settings. So each lane also passes
  `--tools` with the same names, which offers the model those tools and no other, and
  `--permission-mode dontAsk`, which denies every call that would prompt whatever the session's
  start mode and whatever `~/.claude/settings.json` pre-approves. Both are checked against the
  installed CLI's `--help` like the flags below.
* **The repository cannot configure its own measurement.** Every provider launch carries
  `childenv.isolation_flags`: `--safe-mode --strict-mcp-config` for `claude`, `--ignore-rules
  -c project_doc_max_bytes=0` for `codex`. A committed `.claude/settings.json` supplied hooks and
  the CLI ran them, with no `--build` and no prompt; `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, project
  agents and project commands are ignored for the same reason. A CLI too old to offer the flags
  raises `ProviderNotIsolated` and stops the run. `gemini` offers no such control at all — verified
  against its source at v0.54.4 — so the model lanes refuse to run under it.
* **Nothing is written outside the output directory.** `--no-session-persistence` for `claude`,
  `--ephemeral` for `codex`. The prepared history is deleted when the lane returns.

`--build` additionally runs the repository's declared install, build and test commands. That fetches
from package registries and executes repository-authored install scripts, in a child with a scratch
`HOME` and no credentials. The checkout is modified; treat it as consumed.

## Sending your results

**Install the skill.** Unzip it into `~/.claude/skills/`, then `pip install -r requirements.txt`
from inside that directory.

**Then ask Claude**, from throwaway clones of the repositories you are licensing:

> Measure every repository under `~/code` with the codebase-quality skill, one output folder each
> under `./out`.

It runs the skill once per repository and names the folders for you.

**Use throwaway clones.** The run executes each project's own install, build and test commands and
leaves the checkout modified. Point it at a fresh clone, not at the tree you work in.

**Then drop the whole `out` folder on the portal's upload area.** It takes the two files each run
needs, pairs them up, and reads the repository name from the measurement, so a batch of any size is
one step with nothing to type.

If you would rather run it yourself, or want it in CI, it is one command per repository:
`python measure.py <repo> --out ./out/<name>`.

**If a run fails**, send the last 20 lines of terminal output, your Python version, and whether
`git` and `claude` are on your `PATH`.
