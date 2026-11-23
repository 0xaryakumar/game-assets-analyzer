"""Sourcing metadata: counts a buyer filters repositories on before a purchase.

Every value is a number or a flag read from the checkout and its history on `HEAD`.
No path, author, commit subject or file content leaves this module, and nothing is sent
over a network. A value this module cannot measure is null, never a zero: a git call
that fails or runs out of time, a shallow clone, a cap or a spent budget all read as unknown.
The whole lane shares one budget, so it never runs past what the run gave it.

- AI-AUTHORED COMMITS. A commit counts when a `Co-authored-by` trailer, or the commit's
  author or committer, is an AI tool's own identity: its address (`noreply@anthropic.com`,
  `cursoragent@cursor.com`), its agent account (Devin's bot, Copilot's coding agent and
  similar), or a product name that is not also a person's name (`Copilot`, `ChatGPT`,
  `Codex`, `Gemini`, `Claude Code`). A bare first name such as Devin or Claude is not
  enough, because people have those names. A tool that leaves none of these marks is not
  visible here, so the count is a floor. It is stricter than
  `authenticity.explicit_ai_coauthor_ratio`, which matches the whole trailer line, so the
  two can differ for one repository.
- MERGED PULL REQUESTS. The distinct pull-request numbers in the subjects of the
  first-parent history: `Merge pull request #N` and Bitbucket's `Merged in ... (pull request
  #N)`; a squash subject ending `(#N)` only when GitHub itself committed it, because a
  subject pushed straight to the branch can end in an issue reference; and GitLab's `See
  merge request ...!N` in a merge commit's body. A pull request merged with a plain
  fast-forward leaves no trace and is not counted.
- LINES WRITTEN SINCE FEB 2025. `git blame` gives the author date of each non-empty line of
  first-party source at `HEAD`. Third-party, generated and test files are not counted, by the
  same rules as CODE MAKEUP and the test-file patterns. A line dated on or after 2025-02-01 was written in the period when
  coding assistants were in wide use. That is a date, not proof a model wrote the line. A
  shallow clone or a single-commit snapshot dates every line to the commit that brought it,
  so neither is measured, and the counts are reported only when blame reached every file.
- SEEDED DATABASE. Whether the repository ships data meant to be loaded into its own
  database: data files in seed, seeder, sample-data and demo-data directories or named as
  such, and seed code only where a framework looks for it (Prisma, Rails, Laravel, Knex
  and Django). A file named `seed.py` elsewhere is usually a random-seed helper and is not
  counted, and fixture, test and migration paths are left out.
- CODE MAKEUP. Non-empty lines of tracked source at `HEAD` in three classes. Third-party
  means code under a directory that holds someone else's code (`node_modules`, `vendor`,
  `third_party`, `Pods` and similar), and it includes dependencies copied into the tree.
  Generated means build output directories, files that carry a generated marker in their
  first bytes, and minified files. Everything else is first-party. Public code is not
  separated out here: that needs a lookup in a public archive, which is a network call. The
  counts are reported only when every file was read.
- HISTORY SHAPE. Whether the checkout is a shallow clone or a single commit, which is what
  "full git history" asks; `git.full_history_scanned` only says the scan was not capped.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from authenticity import _SOURCE_SUFFIXES
from repo_stats import VB6_HEADER_EXTENSIONS, is_generated, is_test_file, is_vb6_source

AI_ERA_START = datetime(2025, 2, 1, tzinfo=UTC)
LANE_SECONDS = 300
BLAME_FILE_SECONDS = 30
GIT_SECONDS = 120
MAX_BLAME_BYTES = 1_000_000
MAX_COMMITS = 200_000

_AI_ACCOUNT = re.compile(
    r"noreply@anthropic\.com|cursoragent@cursor\.com"
    r"|devin-ai-integration|copilot-swe-agent|copilot\[bot\]|cursor-?agent\b"
    r"|google-labs-jules|jules\[bot\]|openai-codex|chatgpt-codex-connector|codex\[bot\]"
    r"|claude\[bot\]|amazon-q-developer|sweep-ai|codegen-sh|aider\[bot\]|windsurf\[bot\]",
    re.IGNORECASE,
)
_AI_PRODUCT_NAME = re.compile(
    r"(?<![a-z0-9])(github copilot|copilot|chatgpt|gpt-?[0-9]|codex|gemini|codeium"
    r"|windsurf|aider|claude code|claude opus|claude sonnet|devin ai|cursor agent)(?![a-z0-9])",
    re.IGNORECASE,
)


def _is_ai(identity: str) -> bool:
    """An AI tool's own identity: its address or account anywhere, or its product name as the
    NAME. A product word in someone's email domain (`alice@gemini.com`) is a person."""
    name = identity.split("<", 1)[0]
    return bool(_AI_ACCOUNT.search(identity) or _AI_PRODUCT_NAME.search(name))

_PR_SUBJECT = (
    re.compile(r"^Merge pull request #(\d+)"),
    re.compile(r"^Merged in .*\(pull request #(\d+)\)"),
)
_PR_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_GITHUB_COMMITTER = "noreply@github.com"
_PR_MERGE_BODY = re.compile(r"See merge request [\w./-]*!(\d+)")

_CODE_SUFFIXES = frozenset(
    _SOURCE_SUFFIXES
    | {".cbl", ".cob", ".cpy", ".f", ".for", ".f77", ".f95", ".f03", ".f08"}
    | {".lisp", ".lsp", ".lean", ".bas"}
    | VB6_HEADER_EXTENSIONS
)
_SKIP_SEGMENTS = frozenset({
    ".git", "node_modules", "vendor", "vendored", "third_party", "thirdparty", "third-party",
    "bower_components", "pods", ".venv", "venv", "site-packages", "dist", ".next", ".nuxt",
    "__pycache__", ".tox", ".gradle", ".mypy_cache",
})  # fmt: skip
"""Only directories that hold someone else's code or generated output. Narrower than
`authenticity._SKIP_DIRS` on purpose: `env`, `build`, `out` and `external` are often
first-party source, and leaving them out would undercount a blame reported complete."""
_THIRD_PARTY_SEGMENTS = frozenset({
    "node_modules", "vendor", "vendored", "third_party", "thirdparty", "third-party",
    "bower_components", "pods", "carthage", "site-packages", ".venv", "venv",
})  # fmt: skip
_GENERATED_SEGMENTS = frozenset({
    "dist", ".next", ".nuxt", ".output", "generated", "__generated__",
})  # fmt: skip
_MINIFIED = (".min.js", ".min.mjs", ".min.cjs")
_NOT_SEED_SEGMENTS = frozenset({
    "test", "tests", "spec", "specs", "__tests__", "testdata", "testing", "e2e", "cypress",
    "playwright", "mocks", "__mocks__", "fixtures", "migrations", "migrate",
})  # fmt: skip

_SEED_DATA = r"\.(sql|sql\.gz|json|ya?ml|csv)$"
_SEED_PATH = re.compile(
    r"(^|/)(seeds?|seeders?|seed[-_]?data|sample[-_]?data|demo[-_]?data)/[^/]+" + _SEED_DATA
    + r"|(^|/)(seeds?|seed[-_]?data|sample[-_]?data|demo[-_]?data)[^/]*" + _SEED_DATA
    + r"|(^|/)prisma/seed\.(ts|js|mjs|cjs)$"
    r"|(^|/)db/seeds\.rb$|(^|/)db/seeds/[^/]+\.rb$"
    r"|(^|/)database/seeders/[^/]+\.php$"
    r"|(^|/)seeds/[^/]+\.(js|ts|mjs|cjs)$"
    r"|(^|/)management/commands/seed[^/]*\.py$",
    re.IGNORECASE,
)


class _Git:
    """git calls for one repository, all inside the time this lane was given."""

    def __init__(self, repo: Path, budget: float) -> None:
        self.repo = repo
        self.deadline = time.monotonic() + max(0.0, budget)

    def left(self) -> float:
        return self.deadline - time.monotonic()

    def __call__(self, *args: str, cap: float = GIT_SECONDS) -> str | None:
        left = self.left()
        if left <= 0:
            return None
        try:
            done = subprocess.run(
                ["git", "-C", str(self.repo), *args],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=True, timeout=min(cap, left),
            )  # fmt: skip
            return done.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            sys.stderr.write(f"sourcing: git {args[0]} unavailable: {type(exc).__name__}\n")
            return None


def _segments(rel: str) -> set[str]:
    return {part.lower() for part in rel.split("/")[:-1]}


def _tracked(git: _Git) -> list[str] | None:
    raw = git("ls-files", "-z")
    return None if raw is None else sorted(p for p in raw.split("\0") if p)


def _shape(git: _Git) -> tuple[bool | None, int | None]:
    raw = git("rev-parse", "--is-shallow-repository")
    shallow = None if raw is None else raw.strip() == "true"
    count = (git("rev-list", "--count", "HEAD") or "").strip()
    return shallow, int(count) if count.isdigit() else None


def history_shape(shallow: bool | None, commits: int | None) -> dict[str, Any]:
    return {
        "history_shallow": shallow,
        "history_single_commit": None if commits is None else commits == 1,
    }


_NO_AI = {
    "ai_authored_commit_count": None,
    "ai_authored_commit_share": None,
    "ai_coauthored_commit_count": None,
    "ai_agent_commit_count": None,
}


def ai_authored_commits(git: _Git, shallow: bool | None, commits: int | None) -> dict[str, Any]:
    """Commits on HEAD whose co-author, author or committer is an AI tool's own identity.

    Only identity fields and `Co-authored-by` trailer values are read, never the message.
    A shallow clone, or a history past `MAX_COMMITS`, would give a share of an unmarked
    subset, so neither is measured.
    """
    if shallow is not False or not commits:
        return dict(_NO_AI)
    if commits > MAX_COMMITS:
        sys.stderr.write(f"sourcing: {commits} commits exceed {MAX_COMMITS}; AI commits not measured\n")
        return dict(_NO_AI)
    raw = git(
        "log",
        "--format=%an <%ae>%x1f%cn <%ce>%x1f%(trailers:key=Co-authored-by,valueonly,separator=%x1d)%x1e",
        "HEAD",
    )
    if raw is None:
        return dict(_NO_AI)
    coauthored = agent = either = 0
    for record in raw.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) < 3:
            continue
        by_trailer = any(_is_ai(v) for v in fields[2].split("\x1d") if v.strip())
        by_account = _is_ai(fields[0]) or _is_ai(fields[1])
        coauthored += by_trailer
        agent += by_account
        either += by_trailer or by_account
    return {
        "ai_authored_commit_count": either,
        "ai_authored_commit_share": round(either / commits, 4),
        "ai_coauthored_commit_count": coauthored,
        "ai_agent_commit_count": agent,
    }


def merged_pull_requests(git: _Git, shallow: bool | None, commits: int | None) -> int | None:
    """Distinct pull-request numbers in the merge and squash subjects of HEAD's first-parent history."""
    if shallow is not False or commits is None or commits > MAX_COMMITS:
        return None
    raw = git("log", "--first-parent", "--format=%s%x1f%ce%x1e", "HEAD")
    bodies = git("log", "--first-parent", "--merges", "--format=%b%x1e", "HEAD")
    if raw is None or bodies is None:
        return None
    numbers: set[str] = set()
    for record in raw.split("\x1e"):
        subject, _, committer = record.strip("\n").partition("\x1f")
        for pattern in _PR_SUBJECT:
            numbers.update(pattern.findall(subject))
        if committer.strip().lower() == _GITHUB_COMMITTER:
            numbers.update(_PR_SQUASH.findall(subject))
    for body in bodies.split("\x1e"):
        numbers.update(_PR_MERGE_BODY.findall(body))
    return len(numbers)


def _blame_dates(git: _Git, rel: str) -> tuple[int, int] | None:
    raw = git("blame", "--line-porcelain", "-w", "HEAD", "--", rel, cap=BLAME_FILE_SECONDS)
    if raw is None:
        return None
    total = recent = 0
    cutoff = int(AI_ERA_START.timestamp())
    written = 0
    for line in raw.splitlines():
        if line.startswith("author-time "):
            value = line[len("author-time "):].strip()
            written = int(value) if value.isdigit() else 0
        elif line.startswith("\t") and line[1:].strip():
            total += 1
            recent += written >= cutoff
    return total, recent


_NO_AGE = {
    "loc_blamed": None,
    "loc_written_since_2025_02": None,
    "loc_written_since_2025_02_share": None,
    "loc_age_complete": False,
}


def lines_since_ai_era(
    git: _Git, tracked: list[str] | None, shallow: bool | None, commits: int | None
) -> dict[str, Any]:
    """Blamed non-empty lines of first-party, non-test source at HEAD, and how many are dated on
    or after 2025-02-01.

    Every count is null unless blame reached every file in the lane's time: a count over the
    first folders in alphabetical order describes those folders and not the repository.
    """
    if shallow is not False or (commits or 0) < 2 or tracked is None:
        return dict(_NO_AGE)
    blamed = recent = 0
    for rel in tracked:
        if Path(rel).suffix.lower() not in _CODE_SUFFIXES or _segments(rel) & _SKIP_SEGMENTS:
            continue
        path = git.repo / rel
        try:
            if path.is_symlink() or path.stat().st_size > MAX_BLAME_BYTES:
                continue
        except OSError:
            continue
        if Path(rel).suffix.lower() in VB6_HEADER_EXTENSIONS and not is_vb6_source(path):
            continue
        if is_test_file(rel) or _makeup_key(rel, path) != "loc_first_party":
            continue
        counts = _blame_dates(git, rel)
        if counts is None:
            sys.stderr.write("sourcing: blame did not reach every file; line counts not reported\n")
            return dict(_NO_AGE)
        blamed += counts[0]
        recent += counts[1]
    return {
        "loc_blamed": blamed,
        "loc_written_since_2025_02": recent,
        "loc_written_since_2025_02_share": round(recent / blamed, 4) if blamed else None,
        "loc_age_complete": True,
    }


_NO_MAKEUP = {"loc_first_party": None, "loc_third_party": None, "loc_generated": None}


def _non_empty_lines(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return None


def _makeup_key(rel: str, path: Path) -> str:
    segments = _segments(rel)
    if segments & _THIRD_PARTY_SEGMENTS:
        return "loc_third_party"
    if segments & _GENERATED_SEGMENTS or rel.lower().endswith(_MINIFIED) or is_generated(path):
        return "loc_generated"
    return "loc_first_party"


def loc_makeup(git: _Git, tracked: list[str] | None) -> dict[str, Any]:
    """Non-empty lines of tracked source at HEAD: first-party, third-party and generated.

    Every count is null unless every file was read in the lane's time.
    """
    if tracked is None:
        return dict(_NO_MAKEUP)
    counts = {"loc_first_party": 0, "loc_third_party": 0, "loc_generated": 0}
    for rel in tracked:
        if Path(rel).suffix.lower() not in _CODE_SUFFIXES:
            continue
        if git.left() <= 0:
            sys.stderr.write("sourcing: line count did not reach every file; makeup not reported\n")
            return dict(_NO_MAKEUP)
        path = git.repo / rel
        if path.is_symlink() or not path.is_file():
            continue
        if Path(rel).suffix.lower() in VB6_HEADER_EXTENSIONS and not is_vb6_source(path):
            continue
        lines = _non_empty_lines(path)
        if lines is None:
            return dict(_NO_MAKEUP)
        counts[_makeup_key(rel, path)] += lines
    return counts


def seeded_database(tracked: list[str] | None) -> dict[str, Any]:
    """Files the repository ships to load into its own database, outside tests and migrations."""
    if tracked is None:
        return {"seeded_database": None, "seed_file_count": None}
    count = sum(
        1
        for rel in tracked
        if not (_segments(rel) & (_NOT_SEED_SEGMENTS | _SKIP_SEGMENTS)) and _SEED_PATH.search(rel)
    )
    return {"seeded_database": count > 0, "seed_file_count": count}


def collect(repo: Path, budget: float = LANE_SECONDS) -> dict[str, Any]:
    """Every sourcing signal, each read without a network call, all inside `budget` seconds."""
    git = _Git(Path(repo), budget)
    shallow, commits = _shape(git)
    tracked = _tracked(git)
    out: dict[str, Any] = {}
    out.update(history_shape(shallow, commits))
    out.update(ai_authored_commits(git, shallow, commits))
    out["pr_merged_count"] = merged_pull_requests(git, shallow, commits)
    out.update(loc_makeup(git, tracked))
    out.update(lines_since_ai_era(git, tracked, shallow, commits))
    out.update(seeded_database(tracked))
    return out
