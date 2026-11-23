#!/usr/bin/env python3
"""
company_identity.py -- which COMPANY a repository belongs to, read out of the code.

Usage:
    python company_identity.py <repo-path> [--repo-full-name owner/name]

Positional arguments:
    repo-path           A checkout to read. Nothing is written to it and no command is
                        run inside it.

Options:
    --repo-full-name    The value ``measure.py::repo_full_name`` already derived from the
                        ``origin`` remote, as ``owner/name``. Passed IN rather than read
                        here on purpose: that function is where the hardened remote parse
                        lives, and it is the part that refuses a ``file://`` remote and a
                        local filesystem path so an operator's home directory cannot ride
                        through as an organisation. A second copy of that logic here is a
                        second copy to keep right.

Environment variables: none. Read-only, no network, no model call, no secrets.

WHY THIS EXISTS
---------------
A vendor's measurement is implicitly about the vendor. A BROKER's measurement is about a
third party, and until this existed nothing in the output said who. The question then fell
to whoever read the report, who cannot answer it: a repository called ``payments-core``
belongs to whichever company wrote it, and a person looking at the numbers has no way to
tell that from a fork.

The code knows, so this reads it and the firm confirms it. The confirmation matters more
than the reading: everything here is evidence offered to a human who can overrule it, and
the honest answer when the tree holds nothing is ``none`` rather than a guess.

WHAT IT MAY EMIT, AND WHY THAT IS A CHANGE
------------------------------------------
The external variant's rule is "do not acquire", and its identity rule is written down in
``emit_allowlist.py`` as::

    _NO_IDENTITY = "author names, addresses and repository names are not collected"

Company identity is a SECOND deliberate exception to that rule, alongside the repository's
own name. It was approved for this variant specifically (internal ticket): the submitter is a
firm that consents to naming the companies whose code it resells, and knowing whose code is
being bought is the entire point of the flow. The privacy model protects the SUBMITTER, and
here the submitter is the party making the assertion.

That approval is to a CLASS, not to a field. ``emit_allowlist.py`` still declares every
field individually and still fails the run rather than write anything undeclared. Nothing
in this module reaches an artifact on its own account.

THE FOUR FAMILIES THIS READS, AND THE TWO IT DOES NOT
-----------------------------------------------------
    git_remote          the owning organisation in the ``origin`` URL
    licence_file        the legal entity named in LICENCE / NOTICE / COPYING
    copyright_header    the entity named in copyright headers, where it repeats
    package_manifest    an ORGANISATION NAMESPACE in a manifest -- an npm scope, a Go
                        module path, a Maven groupId, a Composer vendor, a publisher

The manifest family reads organisation namespaces ONLY, and never a manifest's ``author``,
``authors``, ``maintainers`` or ``contact`` field. Those hold a person's name, and
``_NO_IDENTITY`` forbids author names in the same breath as author addresses; a person's
name is not made emittable by arriving in a file rather than in a commit. That is also why
Cargo and PyPI manifests contribute nothing here: those ecosystems are flat, so the only
name in them IS the author's.

Two of the six signals the ticket lists are deliberately NOT collected, and both refusals
are declared in ``emit_allowlist.py`` so they appear in the ``--review`` the repository
owner reads before deciding to send anything:

  * **Author email domains.** The most common non-public domain across committers is
    derived from author ADDRESSES, which the identity rule forbids by name. It is the only
    one of the six the rule names, and the four families above settle the answer without
    it.
  * **Config and CI hostnames, registry paths and cloud project names.** These collide
    with the no-paths rule as well as the identity one, and they are the weakest of the six
    -- corroborating at best. The widest widening for the least evidence.

THREE OUTCOMES
--------------
    confident   two or more INDEPENDENT families agree on one name
    uncertain   one family only, or families disagree
    none        nothing usable

``none`` is a first-class answer, not a failure. A repository with no remote, generic
manifests and no copyright header returns it, and the product's confirm step renders that
as its ordinary case: the firm types the name.

NO SCORE, AND NO CONFIDENCE NUMBER
----------------------------------
Nothing here is quality-bearing and no number leaves. In particular the copyright family
counts occurrences internally to decide whether a header repeats, and that count is NOT
emitted: a hit count is a confidence number wearing different clothes, and a percentage
beside a name reads as a grade. What leaves is the outcome and the family names, which is
provenance -- "read from your licence file" -- and is the only form the product wants.

The record is deliberately flat and stdlib-only so it can be read without pulling the rest
of the skill along with it, the same reason ``candidates.py`` gives next door. That module
is unrelated: it holds the TASK-candidate record for the mining lane.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# The closed vocabularies. `emit_allowlist.py` imports these rather than restating them,
# so the emission boundary cannot drift away from the thing it is guarding.
# ---------------------------------------------------------------------------

#: Ordered STRONGEST FIRST, which is the order the ticket ranks them in and the order
#: candidates are tie-broken by. It is not a score and nothing multiplies it.
SIGNAL_FAMILIES = ("licence_file", "copyright_header", "git_remote", "package_manifest")

#: Which family's SPELLING of an agreed name is shown. Different from the strength order:
#: this asks which source writes a company's name the way a human would, and a licence file
#: usually carries the exact registered name while a remote carries a URL slug.
_DISPLAY_PREFERENCE = ("licence_file", "copyright_header", "package_manifest", "git_remote")

OUTCOMES = ("confident", "uncertain", "none")

INDUSTRY_SIGNALS = ("readme", "dependencies")

#: What the code catalogue sorts by. OUR vocabulary, not the repository's: the industry
#: that leaves is one of these words or nothing at all, so no README prose is ever emitted
#: under this field.
INDUSTRIES = (
    "fintech", "healthcare", "insurance", "ecommerce", "logistics", "real_estate",
    "legal", "education", "gaming", "media", "travel", "telecom", "energy",
    "manufacturing", "automotive", "agriculture", "government", "security", "devtools",
    "data_infrastructure", "marketing", "hr_recruiting", "crm_sales", "productivity",
    "social", "crypto", "biotech",
)

# ---------------------------------------------------------------------------
# The name pattern. This is the privacy control, and it is the same shape of control as
# REPO_FULL_NAME in emit_allowlist.py: bounded, and restricted to the characters the thing
# it names may actually hold, so that something else cannot ride through wearing its name.
#
# What it refuses, and why each one matters:
#
#   /  \      a filesystem path. An absolute path is exactly what must not leave, and
#             `/home/jane/work/acme` would otherwise pass any "looks like a name" test.
#   @         an email address or a handle. A committer's address is forbidden identity,
#             and `jane@acme.com` must not become a company called `jane@acme.com`.
#   :         a URL, a scheme or a host:port.
#   _         a snake_case identifier, which is code rather than a name.
#
# And the rule that does the most work: A DOT MAY END A WORD BUT MAY NEVER JOIN TWO
# CHARACTERS. `Acme Systems, Inc.` passes. `acme.com` does not, nor does
# `com.acme.payments`, nor `payments_core.py`, nor any other dotted identifier, module
# path, filename or domain. One rule, four classes of thing kept out.
#
# The letter class includes the Latin-1 supplement, so a European legal entity is spelled
# rather than mangled. Widening the LETTERS is not widening the class of thing emitted: a
# letter is not a path and it is not an address.
#
# What it cannot represent, it refuses, and `collect()` drops the candidate rather than
# handing the boundary something that would fail the whole run. `U.S. Steel` is the honest
# casualty: a dot joining two characters is the domain-and-identifier shape this exists to
# refuse, and a name we cannot spell is a name the firm types in the confirm step instead.
# ---------------------------------------------------------------------------

_LETTER = "A-Za-zÀ-ÖØ-öø-ÿ"
#: A word: starts alphanumeric, may hold letters, digits, ``&``, ``'`` and ``-``, and may
#: end with a single ``.`` or ``,``.
_WORD = rf"[{_LETTER}0-9][{_LETTER}0-9&'-]{{0,39}}[.,]?"
#: A standalone ampersand is a word in its own right in ``The Procter & Gamble Company``.
#: It may not START a name, because a name beginning with punctuation is not a name.
NAME_PATTERN = rf"(?:{_WORD})(?: (?:{_WORD}|&)){{0,7}}"

_NAME = re.compile(NAME_PATTERN)

#: A total ceiling on top of the pattern's own bounds. Eight words of forty characters is
#: 320, and nothing that long is a company name -- it is a sentence out of a licence file.
MAX_NAME_CHARS = 120

#: A SHORT list. The confirm step offers these as choices to a human, and a fifth choice
#: is not more information, it is a worse question.
MAX_CANDIDATES = 3


def is_emittable_name(text: object) -> bool:
    """Whether ``text`` is a company name this variant may emit.

    The single gate. ``collect()`` calls it on every candidate before returning, and
    ``emit_allowlist.COMPANY_NAME`` applies the same pattern at the write boundary as the
    backstop. Anything this refuses is dropped, never repaired: a half-cleaned name is a
    made-up company.
    """
    return (
        isinstance(text, str)
        and 0 < len(text) <= MAX_NAME_CHARS
        and _NAME.fullmatch(text) is not None
    )


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

#: Stripped before two spellings are compared. LEGAL-ENTITY suffixes only, and no
#: descriptive words: dropping `inc` lets the licence's `Acme Systems, Inc.` agree with the
#: remote's `acme-systems`, while dropping `systems` too would make `Acme Systems` agree
#: with `Acme Labs`, which is a different company.
_LEGAL_SUFFIXES = frozenset({
    "inc", "incorporated", "llc", "lllp", "llp", "lp", "ltd", "ltda", "limited", "plc",
    "corp", "corporation", "co", "company", "gmbh", "mbh", "ag", "kg", "sa", "sas",
    "sarl", "srl", "spa", "bv", "nv", "ab", "as", "asa", "oy", "oyj", "aps", "pty",
    "pte", "kk", "kft", "zoo", "doo", "ou", "sro", "ug",
})

#: Entities that are never the company whose repository this is, keyed on ``normalise()``.
#:
#: This list is what stops a GPL repository being attributed to the Free Software Foundation.
#: A licence FILE carries the licence's own boilerplate, and that boilerplate has a copyright
#: line in it: GPLv3 opens with "Copyright (C) 2007 Free Software Foundation, Inc.", and the
#: MIT and BSD templates carry a placeholder where the name goes. Reading the first copyright
#: line in a licence file is the right thing to do and it needs this list to be right, because
#: without it every copyleft repository in the world names the same wrong company, twice over
#: (the licence file and every vendored header agree, so it would come out "confident").
_NOT_A_COMPANY = frozenset({
    # Licence and language stewards, which appear in boilerplate rather than in ownership.
    "freesoftwarefoundation", "fsf", "pythonsoftwarefoundation", "apachesoftwarefoundation",
    "openjsfoundation", "eclipsefoundation", "linuxfoundation", "thelinuxfoundation",
    "softwarefreedomconservancy", "unicodeconsortium", "theunicodeconsortium",
    "rustprojectdevelopers", "therustprojectdevelopers", "goauthors", "thegoauthors",
    "nodejscontributors", "openssfoundation", "openssl", "opensslproject",
    "regentsoftheuniversityofcalifornia", "universityofcalifornia", "mit",
    # Collective and placeholder names, which name nobody in particular.
    "authors", "theauthors", "contributors", "thecontributors", "projectcontributors",
    "theproject", "project", "copyrightholder", "copyrightholders", "owner", "theowner",
    "author", "me", "myself", "you", "yourname", "yournamehere", "companyname",
    "yourcompany", "yourcompanyname", "nameofcopyrightowner", "opensource",
    "opensourcecommunity", "everyone", "anonymous", "developers", "thedevelopers",
    "maintainers", "themaintainers", "team", "theteam", "community", "thecommunity",
})

#: Dropped wholesale from a copyright line before the entity is read.
_RIGHTS_NOISE = re.compile(
    r"\ball rights? reserved\b|\bsome rights reserved\b|\band contributors?\b"
    r"|\band others\b|\bet al\.?", re.IGNORECASE)

# A copyright NOTICE, and deliberately not the word "copyright" wherever it appears. Two
# guards, and both were put here by a licence text that defeated the version without them:
#
#   1. LINE-INITIAL, after at most a short run of comment punctuation (`#`, `//`, `/*`, ` *`).
#      A notice is its own line; a prose mention sits mid-sentence. Apache-2.0's own
#      definitions say "the copyright owner or entity authorized by the copyright owner",
#      which without this anchor yields a company called "owner or entity authorized by" --
#      on a very large share of real repositories.
#   2. A YEAR OR A (c)/© MARKER is required, checked on `marker` below. That is what a real
#      notice carries and what CC0's line-initial "Copyright and Related Rights ..." does
#      not, so the guard costs us "Copyright Acme Systems" with no year at all and buys back
#      every licence whose body opens with the bare word.
_COPYRIGHT = re.compile(
    r"^[^\w\n]{0,24}copyright\b"
    r"(?P<marker>[\s.:]*(?:\(c\)|\(co\)|©|&copy;)?[\s.:]*"
    r"(?:\d{4}(?:\s*[-–—]\s*(?:\d{4}|present))?[\s,;]*)*"       # any run of years
    r"(?:\(c\)|©)?[\s,;]*)"
    r"(?:by\s+)?"
    r"(?P<entity>[^\n]{2,160})",
    re.IGNORECASE | re.MULTILINE)

_HAS_YEAR_OR_MARKER = re.compile(r"\d{4}|\(c\)|\(co\)|©|&copy;", re.IGNORECASE)


def normalise(name: str) -> str:
    """The key two spellings are compared on. Empty when the name says nothing.

    Case-folded, legal suffixes dropped, everything that is not a letter or a digit
    removed. ``Acme Systems, Inc.`` and ``acme-systems`` both key to ``acmesystems``,
    which is what lets the licence file and the git remote count as two families agreeing.
    """
    words = [w for w in re.split(r"[^0-9A-Za-zÀ-ÿ]+", name.casefold()) if w]
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return "".join(words)


# ---------------------------------------------------------------------------
# Bounded reading. Every reader here is capped, because a repository is untrusted input:
# it is as large as somebody else decided, and it may be adversarial.
# ---------------------------------------------------------------------------

#: Never walked into. Vendored trees are the live hazard for the copyright family: a
#: bundled dependency's header names ITS author, and reporting that as the company whose
#: repository this is would be confidently wrong.
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "vendored", "third_party",
    "thirdparty", "third-party", "external", "externals", "bower_components", "Pods",
    ".venv", "venv", "env", "site-packages", "dist", "build", "out", "target",
    ".next", ".nuxt", ".tox", "__pycache__", ".gradle", ".idea", ".mypy_cache",
})

#: Matched as a PREFIX against the upper-cased filename.
_LICENCE_FILES = ("LICENSE", "LICENCE", "NOTICE", "COPYING", "COPYRIGHT")

_SOURCE_SUFFIXES = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".scala", ".rb",
    ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".m", ".mm", ".sh",
    ".sql", ".tf", ".vue", ".svelte", ".ex", ".exs", ".erl", ".clj", ".groovy", ".pl",
})

_MAX_FILES_SCANNED = 600
_MAX_HEADER_BYTES = 4096
#: More than a header, because a licence file carries the licence's whole text and a project
#: routinely appends its own notice AFTER it -- Apache-2.0's appendix sits about ten kilobytes
#: in. Still bounded: this is somebody else's file.
_MAX_LICENCE_BYTES = 65_536
_MAX_MANIFEST_BYTES = 262_144
_MAX_README_BYTES = 40_960
#: A copyright entity has to REPEAT to count. One file's header is as likely to be a single
#: copied-in file's author as it is to be this repository's owner, and "strong at scale,
#: because it repeats" is the whole reason this family is worth reading.
_MIN_COPYRIGHT_FILES = 2


def _read(path: Path, max_bytes: int) -> str:
    """A bounded read that never raises. Empty string for anything unreadable."""
    try:
        with path.open("rb") as fh:
            raw = fh.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def _source_files(repo: Path) -> list[Path]:
    """Up to ``_MAX_FILES_SCANNED`` source files, in a deterministic order.

    Sorted, so the same tree always yields the same sample and the same answer. A cap plus
    an arbitrary walk order would make this collector non-deterministic, which every other
    deterministic collector in this skill would then be lying about.
    """
    found: list[Path] = []
    for directory, subdirs, filenames in _sorted_walk(repo):
        subdirs[:] = [d for d in subdirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if Path(filename).suffix.lower() in _SOURCE_SUFFIXES:
                found.append(directory / filename)
                if len(found) >= _MAX_FILES_SCANNED:
                    return found
    return found


def _sorted_walk(repo: Path):
    """``os.walk``-shaped, sorted at every level, and silent on an unreadable directory."""
    stack = [repo]
    while stack:
        directory = stack.pop(0)
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        subdirs = [e.name for e in entries if e.is_dir() and not e.is_symlink()]
        files = [e.name for e in entries if e.is_file()]
        yield directory, subdirs, files
        stack.extend(directory / name for name in subdirs)


# ---------------------------------------------------------------------------
# The four families
# ---------------------------------------------------------------------------

def _entity_from_copyright_line(text: str) -> str | None:
    """The entity out of one ``Copyright (c) 2024 Acme Systems, Inc.`` line, or None."""
    match = _COPYRIGHT.search(text)
    if not match or not _HAS_YEAR_OR_MARKER.search(match.group("marker")):
        return None
    entity = _RIGHTS_NOISE.sub("", match.group("entity"))
    # A licence file routinely continues into prose on the same line, and the sentence that
    # follows is not part of the name. Cut at the punctuation that ends a name.
    # `*/` and `-->` matter as much as the sentence punctuation: a C, Java, JS or HTML
    # header closes its comment on the same line, and "Acme Systems */" is refused by the
    # name pattern outright -- so leaving them in loses the whole signal rather than
    # trimming it.
    entity = re.split(r"\s*\*/|\s*-->|\s*[;:<(\[]|\s+-\s+|\s{2,}", entity, maxsplit=1)[0]
    # A full stop is the one cut that has to keep what it cuts at: `Inc.` and `Ltd.` end in
    # one, so a dot is only the end of the NAME when prose follows it. Splitting on the dot
    # instead turns every incorporated company into an unincorporated one.
    sentence_end = re.search(r"\.\s+\S", entity)
    if sentence_end:
        entity = entity[:sentence_end.start() + 1]
    entity = entity.strip().strip(",").strip()
    if not entity:
        return None
    # A copyright line with no entity on it -- "Copyright (c) 2024" -- leaves the year behind
    # once the optional year run has nothing after it to hand the rest of the line to. A
    # company called 2024 is precisely the bad guess this must never make, so an entity has
    # to contain a letter.
    if not re.search(rf"[{_LETTER}]", entity):
        return None
    if normalise(entity) in _NOT_A_COMPANY:
        return None
    return entity


def from_remote(repo_full_name: str | None) -> list[str]:
    """The owning organisation out of ``owner/name``, or nothing.

    A one-segment full name is a repository with no owner in its URL, which names nobody.
    A nested group path (``group/subgroup/name``) is owned by its FIRST segment.
    """
    if not repo_full_name:
        return []
    parts = [p for p in repo_full_name.split("/") if p]
    if len(parts) < 2:
        return []
    # A remote slug is a URL word: `acme-systems` is how a company spells itself to a git
    # host, and `normalise()` is what makes it agree with the licence file's spelling.
    return [parts[0]]


def from_licence(repo: Path) -> list[str]:
    """The entity named in a root licence or notice file.

    Root only. A licence file deeper in the tree belongs to whatever is around it, which on
    the evidence available here is as likely to be vendored code as it is to be this
    company's own.
    """
    names: list[str] = []
    try:
        entries = sorted(repo.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    for entry in entries:
        # A PREFIX, not the dotted stem: `LICENSE-MIT` and `LICENSE-APACHE` are how a
        # dual-licensed repository spells it, and `COPYING.LESSER` is how the LGPL does.
        upper = entry.name.upper()
        if upper.startswith(_LICENCE_FILES) and entry.is_file():
            entity = _entity_from_copyright_line(_read(entry, _MAX_LICENCE_BYTES))
            if entity:
                names.append(entity)
    return names


def from_copyright(repo: Path) -> list[str]:
    """The entity that RECURS in source-file copyright headers.

    Only the most common one, and only when it appears in at least ``_MIN_COPYRIGHT_FILES``
    files. A tie returns every tied entity, which then reads as families disagreeing rather
    than as one of them having been picked arbitrarily.

    The counts stay here. They are how this decides, and they are not evidence anybody
    outside this function is entitled to: a per-name hit count is a confidence number.
    """
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for path in _source_files(repo):
        entity = _entity_from_copyright_line(_read(path, _MAX_HEADER_BYTES))
        if not entity:
            continue
        key = normalise(entity)
        if not key:
            continue
        counts[key] += 1
        spelling.setdefault(key, entity)
    if not counts:
        return []
    top = max(counts.values())
    if top < _MIN_COPYRIGHT_FILES:
        return []
    return [spelling[key] for key, n in sorted(counts.items()) if n == top]


def from_manifests(repo: Path) -> list[str]:
    """Organisation NAMESPACES out of root manifests. Never an author or maintainer field.

    An npm scope, a Composer vendor, a Go module path's organisation segment, a Maven
    groupId's organisation segment and a VS Code publisher are all namespaces a company
    registered under its own name. ``author``, ``authors`` and ``maintainers`` are a
    person, and a person's name is forbidden identity wherever it is written down.
    """
    names: list[str] = []

    package_json = _json(repo / "package.json")
    if isinstance(package_json, dict):
        name = package_json.get("name")
        if isinstance(name, str) and name.startswith("@") and "/" in name:
            names.append(name[1:].split("/", 1)[0])
        publisher = package_json.get("publisher")
        if isinstance(publisher, str):
            names.append(publisher)

    composer = _json(repo / "composer.json")
    if isinstance(composer, dict):
        name = composer.get("name")
        if isinstance(name, str) and "/" in name:
            names.append(name.split("/", 1)[0])

    go_mod = _read(repo / "go.mod", _MAX_MANIFEST_BYTES)
    module = re.search(r"^\s*module\s+(\S+)", go_mod, re.MULTILINE)
    if module:
        org = _org_from_module_path(module.group(1))
        if org:
            names.append(org)

    # A bounded regex rather than an XML parser. `pom.xml` is a file somebody else wrote,
    # and `xml.etree` will expand entities in it; reading two tags does not justify handing
    # an untrusted document to a parser that can be made to allocate without bound.
    pom = _read(repo / "pom.xml", _MAX_MANIFEST_BYTES)
    if pom:
        names.extend(_from_pom(pom))

    return [n.strip() for n in names if n and n.strip()]


#: POM elements that carry SOMEBODY ELSE'S identity. Removed before the project's own is read.
#:
#: `developers` and `contributors` are PERSON records, and a developer's `<organization>` is
#: that person's employer rather than this project's owner -- so reading it is the same mistake
#: as reading a manifest's `author` field, which this collector already refuses.
#: `distributionManagement` can carry a `<relocation><groupId>`, which is the coordinates the
#: artifact MOVED FROM: a real pom with one returned "oldvendor" as the company.
_POM_FOREIGN_BLOCKS = (
    "parent", "dependencies", "dependencyManagement", "plugins", "pluginManagement",
    "profiles", "build", "reporting", "modules", "extensions",
    "developers", "contributors", "distributionManagement",
)


def _from_pom(pom: str) -> list[str]:
    """The project's OWN organisation out of a `pom.xml`. Two elements, both easy to misread.

    **`<groupId>` must be the project's, and in a conventional POM the FIRST one is not.**
    Maven puts `<parent>` ahead of the project's own coordinates, so the first `<groupId>` in
    a Spring Boot pom is `org.springframework.boot` -- and a naive read names the framework
    every Java web project in the world is built on as the company that wrote it. A parent
    groupId is an ECOSYSTEM and is never the answer, so the foreign blocks are removed and
    there is no fallback to one: a project that inherits its groupId names nobody here, which
    is the honest result.

    **`<organization><name>` must be read INSIDE that element.** A lazy `.*?<name>` walks out
    of it and matches the next `<name>` anywhere in the file, which in practice is
    `<licenses><license><name>` -- returning "MIT License" as the company.
    """
    stripped = pom
    for block in _POM_FOREIGN_BLOCKS:
        stripped = re.sub(rf"<{block}\b[^>]*>.*?</{block}>", " ", stripped,
                          flags=re.DOTALL | re.IGNORECASE)

    names: list[str] = []
    group = re.search(r"<groupId>\s*([^<\s]{1,200})\s*</groupId>", stripped)
    if group:
        org = _org_from_group_id(group.group(1))
        if org:
            names.append(org)

    # EVERY `<organization>`, not just the first. A string-valued one (a person's employer,
    # in a block this does not strip) has no `<name>` child, and stopping at it drops the
    # project's real organisation entirely -- silently, which is worse than reading the wrong
    # one because nothing downstream can tell the signal was lost.
    for element in re.finditer(r"<organization\b[^>]*>(.*?)</organization>", stripped, re.DOTALL):
        organisation = re.search(r"<name>\s*([^<]{1,200}?)\s*</name>", element.group(1))
        if organisation:
            names.append(organisation.group(1))
            break
    return names


def _org_from_module_path(path: str) -> str | None:
    """``github.com/acme/payments`` -> ``acme``. A bare module name names nobody."""
    segments = [s for s in path.strip().strip("/").split("/") if s]
    # A host, an organisation, then the module. Fewer segments than that is either a local
    # module path or a host-level module, and neither identifies an organisation.
    if len(segments) < 3 or "." not in segments[0]:
        return None
    return segments[1]


def _org_from_group_id(group_id: str) -> str | None:
    """``com.acme.payments`` -> ``acme``. The reverse-domain second segment is the company.

    A two-segment groupId (``com.acme``) resolves the same way. One segment names nobody,
    and a groupId that does not start with a domain-shaped word is not reverse-domain, so
    guessing which of its parts is the company would be inventing an answer.
    """
    segments = [s for s in group_id.strip().split(".") if s]
    if len(segments) < 2 or segments[0].lower() not in {
            "com", "org", "net", "io", "co", "dev", "ai", "app", "cloud", "eu", "uk", "de"}:
        return None
    return segments[1]


def _json(path: Path) -> object:
    text = _read(path, _MAX_MANIFEST_BYTES)
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return None


# ---------------------------------------------------------------------------
# Industry
#
# A hint for the code catalogue, which has nothing else that supplies it. Deterministic
# keyword matching over the README and the declared dependencies -- no model call, and
# nothing read from the repository is emitted: the answer is one of OUR words or nothing.
#
# Whether this is the right PLACE for it is still open (there is also a path where a
# rep sets it once per company). Emitting it as a nullable hint forecloses neither: a rep's
# value overrides a guess, and a guess where there is no rep is better than a blank.
# ---------------------------------------------------------------------------

#: Matched on WORD BOUNDARIES against the README. Distinctive words only: a single
#: keyword must never name an industry, which is the same rule `classify_repo.py` states
#: about naming a repository.
_README_WORDS: dict[str, tuple[str, ...]] = {
    "fintech": ("payments", "payment", "invoicing", "invoices", "ledger", "banking",
                "lending", "underwriting", "brokerage", "kyc", "aml", "payroll",
                "settlement", "chargeback"),
    "healthcare": ("patient", "patients", "clinical", "ehr", "emr", "fhir", "hl7",
                   "diagnosis", "prescription", "telehealth", "hipaa"),
    "insurance": ("policyholder", "underwriter", "claims", "actuarial", "premiums",
                  "reinsurance"),
    "ecommerce": ("checkout", "storefront", "cart", "catalogue", "catalog", "sku",
                  "merchandising", "fulfilment", "fulfillment"),
    "logistics": ("shipment", "shipments", "freight", "warehouse", "dispatch", "courier",
                  "tracking", "carrier", "fleet"),
    "real_estate": ("listings", "property", "properties", "tenant", "landlord",
                    "mortgage", "escrow", "leasing"),
    "legal": ("contract", "contracts", "clause", "litigation", "counsel", "docket",
              "paralegal", "compliance"),
    "education": ("student", "students", "curriculum", "courses", "enrolment",
                  "enrollment", "grading", "classroom", "lms"),
    "gaming": ("gameplay", "player", "players", "multiplayer", "matchmaking", "leaderboard",
               "sprites", "shader"),
    "media": ("streaming", "playback", "subtitles", "transcoding", "editorial",
              "publishing", "podcast"),
    "travel": ("booking", "bookings", "itinerary", "flights", "hotels", "reservations",
               "traveller", "traveler"),
    "telecom": ("subscriber", "roaming", "sim", "provisioning", "voip", "sms", "lte"),
    "energy": ("grid", "metering", "kwh", "turbine", "solar", "photovoltaic", "emissions",
               "utility"),
    "manufacturing": ("assembly", "factory", "shopfloor", "mes", "bom", "tooling",
                      "throughput"),
    "automotive": ("vehicle", "vehicles", "telematics", "adas", "can bus", "powertrain",
                   "dealership"),
    "agriculture": ("crop", "crops", "harvest", "irrigation", "agronomy", "livestock",
                    "yield"),
    "government": ("citizen", "municipal", "procurement", "permits", "constituency",
                   "regulatory"),
    "security": ("vulnerability", "vulnerabilities", "malware", "intrusion", "siem",
                 "threat", "forensics", "pentest"),
    "devtools": ("linter", "compiler", "sdk", "cli", "debugger", "scaffolding",
                 "codegen", "boilerplate"),
    "data_infrastructure": ("etl", "pipeline", "pipelines", "warehouse", "lakehouse",
                            "ingestion", "orchestration", "dbt"),
    "marketing": ("campaign", "campaigns", "attribution", "segmentation", "funnel",
                  "impressions", "adtech", "newsletter"),
    "hr_recruiting": ("candidate", "candidates", "applicant", "recruiter", "onboarding",
                      "payroll", "sourcing", "ats"),
    "crm_sales": ("leads", "pipeline", "quota", "opportunity", "opportunities",
                  "prospect", "crm"),
    "productivity": ("workspace", "notes", "kanban", "calendar", "reminders", "todo",
                     "collaboration"),
    "social": ("followers", "feed", "timeline", "messaging", "profiles", "hashtag"),
    "crypto": ("blockchain", "wallet", "onchain", "smart contract", "staking", "defi",
               "tokenomics"),
    "biotech": ("genome", "genomic", "sequencing", "assay", "molecule", "proteomics",
                "clinical trial"),
}

#: Matched as SUBSTRINGS against declared dependency names, which is how a Go module path
#: and an npm package resolve to the same signal.
_DEPENDENCY_WORDS: dict[str, tuple[str, ...]] = {
    "fintech": ("stripe", "plaid", "braintree", "adyen", "razorpay", "paypal",
                "quickbooks", "xero", "moneyed"),
    "healthcare": ("fhir", "hl7", "pydicom", "dicom", "smart-on-fhir"),
    "ecommerce": ("shopify", "woocommerce", "magento", "bigcommerce", "medusa"),
    "logistics": ("easypost", "shippo", "aftership", "gtfs"),
    "gaming": ("unity", "godot", "pygame", "phaser", "bevy", "raylib"),
    "media": ("ffmpeg", "gstreamer", "hls", "shaka-player", "mux"),
    "telecom": ("twilio", "vonage", "asterisk", "kamailio"),
    "energy": ("pvlib", "modbus", "iec61850"),
    "security": ("yara", "scapy", "volatility", "semgrep", "trivy", "osquery"),
    "data_infrastructure": ("airflow", "dagster", "dbt-core", "kafka", "spark", "flink",
                            "clickhouse", "duckdb"),
    "marketing": ("segment", "mixpanel", "amplitude", "customerio", "mailchimp",
                  "sendgrid"),
    "crm_sales": ("salesforce", "hubspot", "pipedrive"),
    "crypto": ("web3", "ethers", "solana", "wagmi", "viem", "bitcoinlib"),
    "biotech": ("biopython", "rdkit", "scanpy", "pysam", "anndata"),
    "devtools": ("tree-sitter", "libcst", "babel", "rollup", "esbuild"),
}

#: Two hits, not one. One keyword in a README is a coincidence.
_MIN_INDUSTRY_HITS = 2


def _readme_text(repo: Path) -> str:
    try:
        entries = sorted(repo.iterdir(), key=lambda p: p.name)
    except OSError:
        return ""
    for entry in entries:
        if entry.is_file() and entry.name.upper().split(".")[0] == "README":
            return _read(entry, _MAX_README_BYTES).casefold()
    return ""


def _dependency_names(repo: Path) -> list[str]:
    """Declared dependency names from the root manifests, lowercased.

    Names only. A version constraint is not a signal about an industry, and a lockfile is
    thousands of transitive names that say more about a package manager than a business.
    """
    found: list[str] = []

    package_json = _json(repo / "package.json")
    if isinstance(package_json, dict):
        for block in ("dependencies", "devDependencies", "peerDependencies"):
            section = package_json.get(block)
            if isinstance(section, dict):
                found.extend(str(k) for k in section)

    composer = _json(repo / "composer.json")
    if isinstance(composer, dict):
        for block in ("require", "require-dev"):
            section = composer.get(block)
            if isinstance(section, dict):
                found.extend(str(k) for k in section)

    requirements = _read(repo / "requirements.txt", _MAX_MANIFEST_BYTES)
    for line in requirements.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-")):
            found.append(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0])

    for manifest in ("pyproject.toml", "Cargo.toml"):
        found.extend(_toml_dependency_names(repo / manifest))

    go_mod = _read(repo / "go.mod", _MAX_MANIFEST_BYTES)
    found.extend(re.findall(
        r"^\s*(?:require\s+)?([\w.\-/]+)\s+v[\w.\-+]+", go_mod, re.MULTILINE))

    gemfile = _read(repo / "Gemfile", _MAX_MANIFEST_BYTES)
    found.extend(re.findall(r"^\s*gem\s+['\"]([^'\"]+)", gemfile, re.MULTILINE))

    return [name.casefold() for name in found if name]


def _toml_dependency_names(path: Path) -> list[str]:
    """Dependency names out of a pyproject or Cargo manifest, or nothing.

    ``tomllib`` is stdlib from 3.11 and ``repo_stats.py`` already depends on it, so the
    floor this assumes is the floor the skill already has.
    """
    text = _read(path, _MAX_MANIFEST_BYTES)
    if not text:
        return []
    try:
        parsed = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, RecursionError):
        return []
    found: list[str] = []
    project = parsed.get("project")
    if isinstance(project, dict):
        declared = project.get("dependencies")
        if isinstance(declared, list):
            found.extend(
                re.split(r"[<>=!~\[; ]", str(item), maxsplit=1)[0] for item in declared)
    for section in (
            _table(_table(_table(parsed, "tool"), "poetry"), "dependencies"),
            _table(parsed, "dependencies"),
            _table(parsed, "dev-dependencies"),
    ):
        found.extend(str(k) for k in section)
    return [name for name in found if name]


def _table(parsed: object, key: str) -> dict:
    """One level of a TOML table, or an empty one.

    Every level is checked rather than assumed. `tool = "x"` is legal TOML, so chaining
    `.get("tool", {}).get("poetry", {})` raises `AttributeError` on a string and takes the
    whole measurement down over somebody else's malformed manifest -- which is the one thing
    this collector must never do.
    """
    if not isinstance(parsed, dict):
        return {}
    value = parsed.get(key)
    return value if isinstance(value, dict) else {}


def industry_of(repo: Path) -> tuple[str | None, list[str]]:
    """A best-guess industry and which of the two sources contributed to it.

    ``(None, [])`` whenever the evidence does not clear ``_MIN_INDUSTRY_HITS`` or two
    industries tie. A tie is genuinely no answer, and the catalogue is better served by a
    blank it can fill than by whichever of two words sorted first.
    """
    readme = _readme_text(repo)
    dependencies = _dependency_names(repo)

    per_source: dict[str, Counter[str]] = {"readme": Counter(), "dependencies": Counter()}
    for industry, words in _README_WORDS.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", readme):
                per_source["readme"][industry] += 1
    for industry, words in _DEPENDENCY_WORDS.items():
        for word in words:
            if any(word in dep for dep in dependencies):
                per_source["dependencies"][industry] += 1

    totals: Counter[str] = Counter()
    for counts in per_source.values():
        totals.update(counts)
    if not totals:
        return None, []
    top = max(totals.values())
    if top < _MIN_INDUSTRY_HITS:
        return None, []
    winners = [industry for industry, n in totals.items() if n == top]
    if len(winners) != 1:
        return None, []
    winner = winners[0]
    signals = [source for source in INDUSTRY_SIGNALS if per_source[source][winner]]
    return winner, signals


# ---------------------------------------------------------------------------
# The collector
# ---------------------------------------------------------------------------

def collect(repo: Path, repo_full_name: str | None = None) -> dict:
    """Read every family and return the block ``measure.py`` emits.

    Shape::

        {
          "outcome": "confident" | "uncertain" | "none",
          "company_candidates": [{"company_name": str, "signal_families": [str, ...]}],
          "industry": str | None,
          "industry_signals": [str, ...],
        }

    Never raises on a repository's content. Every reader here is bounded and every one of
    them returns nothing rather than failing, because a tree that cannot be read is a
    ``none``, and a collector that stops the run over somebody's malformed ``pom.xml``
    would cost the whole measurement to answer a question the firm can answer by typing.
    """
    repo = Path(repo)
    per_family = {
        "git_remote": from_remote(repo_full_name),
        "licence_file": from_licence(repo),
        "copyright_header": from_copyright(repo),
        "package_manifest": from_manifests(repo),
    }

    # key -> {"families": set, "spellings": {family: name}}
    grouped: dict[str, dict] = {}
    for family in SIGNAL_FAMILIES:
        for name in per_family[family]:
            if not is_emittable_name(name):
                continue                      # unrepresentable, so it is not offered at all
            key = normalise(name)
            if not key or key in _NOT_A_COMPANY:
                continue                      # nothing left, or it names nobody in particular
            entry = grouped.setdefault(key, {"families": set(), "spellings": {}})
            entry["families"].add(family)
            entry["spellings"].setdefault(family, name)

    ranked = [
        {
            "company_name": _display(entry["spellings"]),
            "signal_families": [f for f in SIGNAL_FAMILIES if f in entry["families"]],
        }
        for _, entry in sorted(grouped.items(), key=lambda kv: _rank(kv[0], kv[1]))
    ]

    # `confident` needs agreement, and TWO corroborated names is a disagreement rather than
    # two agreements. A fork is exactly that shape -- the original licence and headers naming
    # one company while the new remote and manifest scope name another -- and it is the case
    # this whole feature opens with, so reporting it `confident` would pre-fill one of two
    # contradictory answers into a modal whose confident rows are accepted in bulk.
    #
    # Counted over EVERY candidate, before the display cap, so a name held back by the cap
    # still costs the run its confidence.
    corroborated = [c for c in ranked if len(c["signal_families"]) >= 2]
    if not ranked:
        outcome = "none"
    elif len(corroborated) == 1:
        outcome = "confident"
    else:
        outcome = "uncertain"           # one family only, or corroborated names disagree

    candidates = ranked[:MAX_CANDIDATES]

    industry, industry_signals = industry_of(repo)
    return {
        "outcome": outcome,
        "company_candidates": candidates,
        "industry": industry,
        "industry_signals": industry_signals,
    }


def _display(spellings: dict[str, str]) -> str:
    for family in _DISPLAY_PREFERENCE:
        if family in spellings:
            return spellings[family]
    return next(iter(spellings.values()))


def _rank(key: str, entry: dict) -> tuple:
    """Most corroborated first, then strongest family, then the key, so ties are stable."""
    strongest = min(SIGNAL_FAMILIES.index(f) for f in entry["families"])
    return (-len(entry["families"]), strongest, key)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Infer which company a repository belongs to, from the code.")
    parser.add_argument("repo_path", help="Path to a checkout.")
    parser.add_argument(
        "--repo-full-name",
        help="`owner/name` as measure.py::repo_full_name already parsed it from the remote.")
    args = parser.parse_args()

    repo = Path(args.repo_path)
    if not repo.is_dir():
        print(json.dumps({"error": f"not a directory: {repo}"}))
        return 1
    print(json.dumps(collect(repo, args.repo_full_name), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
