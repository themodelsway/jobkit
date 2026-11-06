#!/usr/bin/env python3
"""Build a simple markdown resume tailored to a job description (read-only on the resume data).

  build-resume jd.txt                       # writes output/resumes/<jd name>.md
  build-resume jd.txt -o out.md --top 5     # custom path / bullets per company
  build-resume - < jd.txt                   # job description from stdin

Picks, from the stored resume data: the best-fitting opening summary, the best bullets for each company
(same scoring as `query-resume for-jd`), the skills the JD asks for (grouped), certifications and education.

Name and contact lines are NOT stored in resume-data/. They come from profile/header.md; a template is created on first run. Output goes to output/.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from jobkit import common
from jobkit.resumes import query_resume as qr
from jobkit.resumes.resume_data import Bullet, Company, ResumeProfile
from jobkit.user import profile as up

OUTPUT_DIR: Path = common.output_dir() / "resumes"
HEADER_TEMPLATE: Final[str] = """# Your Name
City, ST | phone | email | linkedin.com/in/you
"""
OLD_YEAR: Final[int] = 2018          # companies that ended before this get fewer bullets
OLD_COMPANY_BULLETS: Final[int] = 2
SIMILARITY_LIMIT: Final[float] = 0.3


@dataclass(frozen=True)
class BuildOptions:
    """How to build: bullets per company, job-title overrides ({company id: title}), review and recency settings."""

    top: int = 4
    titles: Mapping[str, str] = field(default_factory=dict)
    include_review: bool = False
    recency: float = 2.0


@dataclass
class BuildNotes:
    """What the caller should tell the user after a build."""

    used_summary: str | None
    missing: list[str]
    hidden: int
    header_missing: bool


def header_file() -> Path:
    """Where the name and contact lines live (profile/header.md)."""
    return up.header_path()


def fmt_date(date: str | None) -> str:
    """'YYYY-MM' -> 'MM/YYYY'; None -> 'Present'."""
    if not date:
        return "Present"
    year, month = date.split("-")
    return f"{month}/{year}"


def company_line(company: Company, titles: Mapping[str, str]) -> tuple[str, str]:
    """(title, date range) for a company: latest role's title, span of all its roles."""
    latest = max(company["roles"], key=lambda r: r["start"] or "")
    title = titles.get(company["id"]) or min(latest["titles"], key=len)
    start = min(r["start"] for r in company["roles"] if r["start"])
    ends = [r["end"] for r in company["roles"]]
    end = None if None in ends else max(e for e in ends if e)
    return title, f"{fmt_date(start)} - {fmt_date(end)}"


def clean_education(profile: ResumeProfile) -> str | None:
    """The fullest education line, without bullet markers or a trailing year range."""
    lines = []
    for entry in profile["education"]:
        entry = re.sub(r"^[●•§]\s*", "", entry).strip()
        lines.append(re.sub(r",?\s*\d{4}\s*-\s*\d{4}$", "", entry))
    return max(lines, key=len) if lines else None


def too_similar(bullet: Bullet, chosen: Iterable[Bullet]) -> bool:
    """True if the bullet repeats a claim already chosen: same metric, or mostly the same words."""
    words = qr.words(bullet["text"])
    for other in chosen:
        other_words = qr.words(other["text"])
        if set(bullet["metrics"]) & set(other["metrics"]) or len(words & other_words) / max(1, len(words | other_words)) >= SIMILARITY_LIMIT:
            return True
    return False


def pick(candidates: Iterable[Bullet], n: int) -> list[Bullet]:
    """The first n candidates that do not repeat each other."""
    chosen: list[Bullet] = []
    for bullet in candidates:
        if len(chosen) < n and not too_similar(bullet, chosen):
            chosen.append(bullet)
    return chosen


def render_summary(result: qr.Analysis) -> list[str]:
    """The opening summary section (best-fitting summary, with the headline in bold)."""
    if not result.summaries:
        return []
    headlines = result.profile.get("headlines") or []
    lead = f"**{headlines[0]}**. " if headlines else ""
    return ["## Summary", "", lead + result.summaries[0]["text"], ""]


def company_bullets(company: Company, scored: Iterable[qr.ScoredBullet], options: BuildOptions) -> list[Bullet]:
    """The bullets to show for one company; at least one proven bullet even when nothing matched the JD."""
    old = max(role["end"] or "9999" for role in company["roles"]) < f"{OLD_YEAR}"
    picks = pick([item.bullet for item in scored], min(options.top, OLD_COMPANY_BULLETS) if old else options.top)
    if picks:
        return picks
    live = [b for b in company["bullets"] if not b.get("ignored") and not b.get("needs_review")]
    return pick(sorted(live, key=lambda b: -len(b["sources"])), 1)


def render_experience(result: qr.Analysis, options: BuildOptions) -> list[str]:
    """The experience section: one heading and bullet list per company."""
    lines = ["## Experience", ""]
    for company, scored in result.ranked:
        title, dates = company_line(company, options.titles)
        lines += [f"### {company['name']} | {title} | {dates}", ""]
        lines += [f"- {b['text']}" for b in company_bullets(company, scored, options)] + [""]
    return lines


def render_skills(result: qr.Analysis) -> list[str]:
    """The skills the JD asks for, by group."""
    groups = {g: [item["name"] for item in items if item["name"] in result.need]
              for g, items in result.skills["groups"].items()}
    shown = {g: names for g, names in groups.items() if names}
    return ["## Skills", ""] + [f"- **{g}:** {', '.join(names)}" for g, names in shown.items()] + [""] if shown else []


def render_credentials(profile: ResumeProfile) -> list[str]:
    """Certifications and education sections."""
    lines: list[str] = []
    certs = [c["name"] if isinstance(c, dict) else str(c) for c in profile.get("certifications", [])]   # curated: {"name"}
    if certs:
        lines += ["## Certifications", ""] + [f"- {c}" for c in certs] + [""]
    education = clean_education(profile)
    if education:
        lines += ["## Education", "", education, ""]
    return lines


def build(text: str, options: BuildOptions, header: str | None) -> tuple[str, BuildNotes]:
    """Markdown resume for the job description; `header` is the name/contact text (None: use the template)."""
    result = qr.analyze(text, (), options.include_review, options.recency)
    lines = [(header or HEADER_TEMPLATE).rstrip(), ""]
    lines += render_summary(result) + render_experience(result, options) + render_skills(result)
    lines += render_credentials(result.profile)
    notes = BuildNotes(used_summary=result.summaries[0]["id"] if result.summaries else None,
                       missing=[s for s in result.need if s not in result.covered], hidden=result.hidden,
                       header_missing=header is None)
    return "\n".join(lines).rstrip() + "\n", notes


def cmd_build(args: argparse.Namespace) -> None:
    """Build the resume, write it, and report gaps."""
    text = common.read_text_arg(args.jd)
    header_path = header_file()
    header = header_path.read_text(encoding="utf-8") if header_path.exists() else None
    options = BuildOptions(args.top, dict(t.split("=", 1) for t in args.title), args.include_review, args.recency)
    markdown, notes = build(text, options, header)

    name = "resume" if args.jd == "-" else Path(args.jd).stem
    out = Path(args.output) if args.output else OUTPUT_DIR / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")

    if notes.header_missing:
        header_path.write_text(HEADER_TEMPLATE, encoding="utf-8")
        print(f"Created {header_path.name} template: put your name and contact line there, then re-run.")
    print(f"Wrote {out}")
    print(f"Opening summary: {notes.used_summary}")
    print("JD skills with no supporting bullet: " + (", ".join(notes.missing) or "none"))
    if notes.hidden:
        print(f"{notes.hidden} bullet(s) flagged needs_review were left out.")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("jd", help="job description text file, or - for stdin")
    parser.add_argument("-o", "--output", help="output path (default output/resumes/<jd file name>.md)")
    parser.add_argument("--top", type=int, default=4, help="bullets per company (default 4; old companies get at most 2)")
    parser.add_argument("--title", action="append", default=[], metavar="COMPANY=TITLE",
                        help='override the job title shown for a company id, e.g. --title <company-id>="placeholder"')
    parser.add_argument("--recency", type=float, default=2.0, help="recency weight, as in query-resume for-jd")
    parser.add_argument("--include-review", action="store_true", help="allow bullets flagged needs_review")
    parser.set_defaults(fn=cmd_build)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
