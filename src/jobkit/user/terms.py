"""Personal terms that must never be committed, and the scan that enforces it (for contributors who commit).

Two kinds of term, one list:
  derived  read each time from what is already stored: your name and header contact details, the resume folder,
           the employer names found by the resume scan, and the company folders of your resume files (never copied, so they cannot go stale)
  stored   the `term` table: products, extra clients and patterns you add, and the derived terms you ignore

Used through `profile terms ...` (see profile.py); the pre-commit hook runs `profile terms check --staged`.
Import it as `from jobkit.user import terms`; it does no work at import time.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from jobkit.common import ToolError
from jobkit.user import tables

MATCHES: Final[tuple[str, ...]] = ("word", "phrase", "regex")
KINDS: Final[tuple[str, ...]] = ("name", "contact", "path", "employer", "client", "product", "other")
SHORT_TERM: Final[int] = 4                 # a derived term this short is matched as a whole word (for example ACME)
MIN_TERM: Final[int] = 3
MAX_LISTED_LINES: Final[int] = 2           # a file with more matching lines than this shows a count, not every number
SKIP_SUFFIX: Final[frozenset[str]] = frozenset({".png", ".jpg", ".pdf", ".pyc"})
POSIX_CLASSES: Final[dict[str, str]] = {"[:alnum:]": "a-zA-Z0-9", "[:alpha:]": "a-zA-Z", "[:digit:]": "0-9",
                                        "[:space:]": r"\s", "[:punct:]": r"!-/:-@\[-`{-~"}
DATE_FOLDER: Final[re.Pattern[str]] = re.compile(
    r"((19|20)\d\d|q[1-4]|(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*)([ _.-]*(19|20)?\d\d)?", re.I)
REGEX_CHARS: Final[re.Pattern[str]] = re.compile(r"[\\^$|?*+()\[\]{}]")


@dataclass(frozen=True)
class Term:
    """One term: its text, what it is, how it matches, where it comes from, and whether it is ignored."""

    text: str
    kind: str
    match: str
    source: str            # "derived" or "stored"
    ignored: bool = False


def pattern(term: Term) -> re.Pattern[str]:
    """The case-insensitive pattern for a term (whole word, phrase, or the regular expression as written)."""
    if term.match == "regex":
        text = term.text
        for name, chars in POSIX_CLASSES.items():     # grep-style classes, as in a hand-written terms file
            text = text.replace(name, chars)
        return re.compile(text, re.I)
    body = re.escape(term.text)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])" if term.match == "word" else body, re.I)


def guess_match(text: str) -> str:
    """How a term with no stated mode is matched: regex when it looks like one, whole word when short."""
    if REGEX_CHARS.search(text):
        return "regex"
    return "word" if len(text) <= SHORT_TERM else "phrase"


def contact_terms(header: str | None) -> list[Term]:
    """The phone, email and LinkedIn parts of the header's contact line (the city is not a term)."""
    lines = (header or "").splitlines()
    parts = [p.strip() for p in lines[1].split("|")] if len(lines) > 1 else []
    keep = [p for p in parts if "@" in p or "linkedin" in p.lower() or sum(c.isdigit() for c in p) >= 7]
    return [Term(p, "contact", "phrase", "derived") for p in keep if len(p) >= MIN_TERM]


def folder_names(files: Iterable[str], skip: Iterable[str] = ()) -> list[str]:
    """The company a resume was written for: the first folder on the file's path that is not a date folder (a
    year, a quarter or a month) or one of the `skip` names (the resume folders chosen at setup). So
    "2026/Acme Air/me.docx", "Acme Air/me.docx" and "2026/Acme Air/October/me.pdf" all give "Acme Air". A folder
    joined with underscores ("Acme_Air_Co") gives each part; a file straight under the resume folder gives nothing."""
    skipped = {s.lower() for s in skip}
    names: set[str] = set()
    for file in files:
        folders = [f for f in file.split("/")[:-1] if f.lower() not in skipped and not DATE_FOLDER.fullmatch(f)]
        if folders:
            names |= {piece.strip() for piece in folders[0].split("_") if piece.strip()}
    return sorted(names)


def derive(name: str | None, resume_root: str | None, header: str | None, employers: Iterable[str],
           folders: Iterable[str] = ()) -> list[Term]:
    """The terms that come from stored data: names, contact details, resume folder, employer names and the
    companies named by the folders of your resume files."""
    found = [Term(n, "name", "phrase", "derived") for n in (name, _header_name(header)) if n]
    found += contact_terms(header)
    found += [Term(resume_root, "path", "phrase", "derived")] if resume_root else []
    found += [Term(e, "employer", "word" if len(e) <= SHORT_TERM else "phrase", "derived") for e in employers if e]
    found += [Term(f, "client", "word" if len(f) <= SHORT_TERM else "phrase", "derived") for f in folders if f]
    unique = {t.text.lower(): t for t in found if len(t.text.strip()) >= MIN_TERM and t.text.lower() != "your name"}
    return list(unique.values())


def _header_name(header: str | None) -> str | None:
    """The name on the first line of the header."""
    lines = (header or "").splitlines()
    return re.sub(r"^#\s*", "", lines[0]).strip() if lines else None


def merge(derived: Sequence[Term], stored: Iterable[Mapping[str, object]]) -> list[Term]:
    """Derived and stored terms in one list. A stored row marked ignored marks the derived term with the same text,
    or stands alone as a common word kept out of the normal check (`check --exhaustive` includes it)."""
    ignored = {str(r["text"]).lower() for r in stored if r["ignored"]}
    out = [Term(t.text, t.kind, t.match, t.source, t.text.lower() in ignored) for t in derived]
    seen = {t.text.lower() for t in out}
    for row in stored:
        text = str(row["text"])
        if text.lower() not in seen:
            out.append(Term(text, str(row["kind"]), str(row["match"]), "stored", bool(row["ignored"])))
    return out


def scan(text: str, terms: Iterable[Term]) -> list[tuple[int, Term]]:
    """Every (line number, term) where one of the given terms appears in the text (the caller picks the terms)."""
    patterns = [(t, pattern(t)) for t in terms]
    return [(n, t) for n, line in enumerate(text.splitlines(), 1) for t, rx in patterns
            if rx.search(line) or (t.match == "regex" and t.text.lower() in line.lower())]   # a pattern's own text leaks too


def _git(*args: str) -> bytes:
    """Output of a git command in the repository the command is run from."""
    done = subprocess.run(["git", *args], capture_output=True, check=False)
    if done.returncode:
        raise ToolError(f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def _repository_files(root: str, args: argparse.Namespace) -> list[tuple[str, str]]:
    """(path, content) pairs from the repository: every committable file (--all) or the staged files as staged (added, copied,
    modified, renamed - under their new name - or type-changed)."""
    if args.all:
        names = _git("-C", root, "ls-files", "-co", "--exclude-standard", "-z").decode().split("\0")
        return [(n, (Path(root) / n).read_text(encoding="utf-8", errors="ignore")) for n in names
                if n and (Path(root) / n).is_file() and Path(n).suffix not in SKIP_SUFFIX]
    names = _git("-C", root, "diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z").decode().split("\0")
    return [(n, _git("-C", root, "show", f":{n}").decode("utf-8", "ignore")) for n in names
            if n and Path(n).suffix not in SKIP_SUFFIX]


def files_to_check(args: argparse.Namespace) -> list[tuple[str, str]]:
    """(path, content) pairs: the paths given, every committable file (--all), or the staged files as staged."""
    if args.values:
        return [(p, Path(p).read_text(encoding="utf-8", errors="ignore")) for p in args.values]
    return _repository_files(_git("rev-parse", "--show-toplevel").decode().strip(), args)


def check(args: argparse.Namespace, terms: Sequence[Term]) -> int:
    """Print each hit as path:line and the term; status 1 when there is any. Says how many files were read.

    With `--exhaustive` the ignored (common-word) terms are checked too and marked in the output: for a manual
    review, not for the pre-commit hook.
    """
    active = [t for t in terms if args.exhaustive or not t.ignored]
    files = files_to_check(args)
    hits = [(path, n, t) for path, text in files for n, t in scan(text, active)]
    real = [h for h in hits if not h[2].ignored]
    for path, n, t in real:
        print(f"{path}:{n}: {t.kind} term {t.text!r}")
    for t in active:
        if t.ignored:
            _print_common_word(t, [(path, n) for path, n, hit in hits if hit is t])
    if hits:
        print(f"{len(real)} personal term hit(s), {len(hits) - len(real)} common-word hit(s). Remove personal terms, "
              "or if one is a false alarm: profile terms ignore TEXT", flush=True)
        return 1
    if not files:
        print("personal terms: no files to check. Nothing is staged; use --all for every file, or give paths.")
        return 0
    common = sum(t.ignored for t in active)
    print(f"personal terms: none found ({len(active)} terms, {len(files)} files checked)")
    if args.exhaustive and not common:
        print("No common words are recorded, so --exhaustive checked nothing extra. "
              "Record them with: profile terms ignore WORD")
    return 0


def _print_common_word(term: Term, found: Sequence[tuple[str, int]]) -> None:
    """One block per common word: `Word: X`, then one line per file with its line numbers, or how many lines
    when there are more than two."""
    if not found:
        return
    print(f"\nWord: {term.text}")
    for path in sorted({p for p, _ in found}):
        lines = [n for p, n in found if p == path]
        print(f"  {path} ({', '.join(map(str, lines)) if len(lines) <= MAX_LISTED_LINES else f'multiple lines: {len(lines)}'})")


def import_file(path: str) -> int:
    """Store the terms in a text file, one per line (a line with regular-expression characters is a pattern)."""
    count = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            add(text, "other", guess_match(text))
            count += 1
    return count


def add(text: str, kind: str, match: str) -> None:
    """Store a term after checking its kind, mode and (for a pattern) that the expression is valid."""
    if kind not in KINDS or match not in MATCHES:
        raise ToolError(f"kind is one of {', '.join(KINDS)}; match is one of {', '.join(MATCHES)}")
    if len(text.strip()) < MIN_TERM:
        raise ToolError(f"A term needs at least {MIN_TERM} characters.")
    try:
        pattern(Term(text.strip(), kind, match, "stored"))
    except re.error as exc:
        raise ToolError(f"Not a valid pattern: {exc}") from exc
    tables.save_term(text.strip(), kind, match, False)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The arguments of `profile terms`."""
    parser.add_argument("action", nargs="?", choices=["list", "add", "ignore", "rm", "import", "check"])
    parser.add_argument("values", nargs="*", help="the term (add, ignore, rm), a file (import) or paths (check)")
    parser.add_argument("--kind", default="other", choices=KINDS)
    parser.add_argument("--match", choices=MATCHES, help="default: a pattern if it looks like one, a whole word if short")
    parser.add_argument("--staged", action="store_true", help="check: the staged files as staged (the pre-commit hook)")
    parser.add_argument("--all", action="store_true", help="check: every file git would commit")
    parser.add_argument("--exhaustive", action="store_true",
                        help="check: also the ignored common words (for a manual review, never the hook)")


def run(args: argparse.Namespace, derived: Sequence[Term]) -> int:
    """The `profile terms` actions: list, add, ignore, rm, import, check."""
    action = args.action or "list"
    if action == "add":
        add(_one(args), args.kind, args.match or guess_match(_one(args)))
    elif action == "ignore":
        tables.save_term(_one(args), args.kind, args.match or guess_match(_one(args)), True)
    elif action == "rm":
        if not tables.delete_term(_one(args)):
            raise ToolError(f"No stored term {_one(args)!r}. `profile terms list` shows them.")
    elif action == "import":
        print(f"Imported {import_file(_one(args))} term(s).")
    else:
        terms = merge(derived, tables.load_terms())
        return check(args, terms) if action == "check" else _list(terms)
    return 0


def _one(args: argparse.Namespace) -> str:
    """The single argument these actions need."""
    if len(args.values) != 1:
        raise ToolError(f"profile terms {args.action} needs exactly one value")
    return str(args.values[0])


def _list(terms: Sequence[Term]) -> int:
    """Print every term with where it comes from; ignored terms are marked."""
    for t in terms:
        print(f"{t.kind:9} {t.match:6} {t.source:8} {t.text}{'   (common word: skipped by the hook)' if t.ignored else ''}")
    print(f"{len(terms)} term(s).")
    return 0
