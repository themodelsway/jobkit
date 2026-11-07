#!/usr/bin/env python3
"""Build a simple markdown resume tailored to a job description (read-only on the resume data).

  build-resume jd.txt                       # writes output/resumes/<jd name>.md (+ .build.json record; never overwrites: -2, -3 ...)
  build-resume jd.txt -o out.md --top 5     # custom path / bullets per company
  build-resume - < jd.txt                   # job description from stdin
  build-resume --approve out.md             # after you have reviewed it: record it as approved
  build-resume --status out.md              # draft | approved | changed (edited after approval)

Picks, from the stored resume data: the best-fitting opening summary, the best bullets for each company
(same scoring as `query-resume for-jd`), the skills the JD asks for (grouped), certifications and education.

Name and contact lines are NOT stored in resume-data/. They come from profile/header.md; a template is created on first run. Output goes to output/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date as calendar_date
from pathlib import Path
from typing import Final

from jobkit import common
from jobkit.resumes import evidence
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import query_resume as qr
from jobkit.resumes.resume_data import Bullet, Company, ResumeProfile, Role
from jobkit.user import profile as up

OUTPUT_DIR: Path = common.output_dir() / "resumes"
HEADER_TEMPLATE: Final[str] = """# Your Name
City, ST | phone | email | linkedin.com/in/you
"""
OLD_YEARS: Final[int] = 8            # companies that ended more than this many years ago get fewer bullets
OLD_COMPANY_BULLETS: Final[int] = 2
SIMILARITY_LIMIT: Final[float] = 0.3
SAME_FIGURE_SIMILARITY: Final[float] = 0.2   # a shared figure only means "same claim" when the wording also overlaps
REVIEW_CHECKLIST: Final[str] = ("This is a draft. Before sending, check: job titles and dates, every claim is yours "
                                "and still true, the name and contact lines, qualifications, and how it looks when opened.")


@dataclass(frozen=True)
class BuildOptions:
    """How to build: bullets per company, job-title overrides ({company id: title}), review and recency settings."""

    top: int = 4
    titles: Mapping[str, str] = field(default_factory=dict)
    include_review: bool = False
    recency: float = 2.0
    max_bullets: int | None = None
    requirements: Sequence[str] = ()


@dataclass
class BuildNotes:  # pylint: disable=too-many-instance-attributes
    """What the caller should tell the user after a build."""

    used_summary: str | None
    missing: list[str]
    hidden: int
    header_missing: bool
    selected: list[str] = field(default_factory=list)
    not_shown: list[str] = field(default_factory=list)
    shown_count: int = 0
    need_count: int = 0
    unplaced: int = 0
    requirements_given: bool = False
    possible: list[tuple[str, str]] = field(default_factory=list)
    set_aside: list[str] = field(default_factory=list)
    no_bullets: list[str] = field(default_factory=list)


def header_file() -> Path:
    """Where the name and contact lines live (profile/header.md)."""
    return up.header_path()


def fmt_date(date: str | None) -> str:
    """'YYYY-MM' -> 'MM/YYYY'; None -> 'Present'."""
    if not date:
        return "Present"
    year, month = date.split("-")
    return f"{month}/{year}"


def role_line(role: Role, title: str | None = None) -> str:
    """'Title | MM/YYYY - MM/YYYY' for one role; `title` overrides the shortest stored title."""
    shown = title or (min(role["titles"], key=len) if role["titles"] else "")
    return f"{shown} | {fmt_date(role['start'])} - {fmt_date(role['end'])}"


def roles_newest_first(company: Company) -> list[Role]:
    """The company's roles, newest start first (a role with no start sorts last)."""
    return sorted(company["roles"], key=lambda r: r["start"] or "", reverse=True)


def role_groups(company: Company, picks: Sequence[Bullet]) -> list[tuple[Role, list[Bullet]]]:
    """The chosen bullets grouped under the role they belong to, newest role first. A bullet whose role is not
    known goes under the latest role. Roles with no chosen bullet are left out."""
    roles = roles_newest_first(company)
    starts = {r["start"] for r in roles}
    groups: dict[int, list[Bullet]] = {}
    for bullet in picks:
        index = next((i for i, r in enumerate(roles) if r["start"] == bullet["role_start"]), 0) \
            if bullet["role_start"] in starts else 0
        groups.setdefault(index, []).append(bullet)
    return [(roles[i], groups[i]) for i in sorted(groups)]


def unplaced(chosen: Iterable[tuple[Company, Sequence[Bullet]]]) -> int:
    """How many chosen bullets have no matching role and were put under the latest one."""
    return sum(1 for company, picks in chosen for b in picks
               if b["role_start"] not in {r["start"] for r in company["roles"]})


def clean_education(profile: ResumeProfile) -> list[str]:
    """Every education entry, without bullet markers or a trailing year range."""
    lines = []
    for entry in profile["education"]:
        entry = re.sub(r"^[●•§]\s*", "", entry).strip()
        entry = re.sub(r",?\s*\d{4}\s*-\s*\d{4}$", "", entry)
        if entry and entry not in lines:
            lines.append(entry)
    return lines


def relevant_projects(profile: ResumeProfile, need: Iterable[str]) -> list[str]:
    """The stored projects that mention a skill the posting asks for."""
    skills = list(need)
    return [p for p in profile.get("projects", []) if any(pr.term_found(skill, p) for skill in skills)]


def too_similar(bullet: Bullet, chosen: Iterable[Bullet]) -> bool:
    """True if the bullet repeats a claim already chosen: mostly the same words, or the same figure with some
    shared wording. Two different results that happen to share a number (20% and 20%) are both kept."""
    words = qr.words(bullet["text"])
    for other in chosen:
        other_words = qr.words(other["text"])
        overlap = len(words & other_words) / max(1, len(words | other_words))
        shared_figure = bool(set(bullet["metrics"]) & set(other["metrics"]))
        if overlap >= SIMILARITY_LIMIT or (shared_figure and overlap >= SAME_FIGURE_SIMILARITY):
            return True
    return False


def pick(candidates: Iterable[Bullet], n: int, already: Sequence[Bullet] = ()) -> list[Bullet]:
    """The first n candidates that do not repeat each other or a bullet already used elsewhere in the resume."""
    chosen: list[Bullet] = []
    for bullet in candidates:
        if len(chosen) < n and not too_similar(bullet, [*already, *chosen]):
            chosen.append(bullet)
    return chosen


def render_summary(result: qr.Analysis) -> list[str]:
    """The opening summary section (best-fitting summary, with the headline in bold)."""
    if not result.summaries:
        return []
    headline = best_headline(result)
    lead = f"**{headline}**. " if headline else ""
    return ["## Summary", "", lead + result.summaries[0]["text"], ""]


def best_headline(result: qr.Analysis) -> str | None:
    """The stored headline that shares the most words with the JD's skills and themes; None when none does,
    so an unrelated headline is not shown."""
    wanted = {w for term in [*result.need, *result.themes] for w in qr.words(term)}
    scored = [(len(qr.words(h) & wanted), h) for h in result.profile.get("headlines") or []]
    best = max(scored, default=(0, None), key=lambda pair: pair[0])
    return best[1] if best[0] else None


def bullet_cap(company: Company, options: BuildOptions) -> int:
    """The most bullets one company may show: `top`, or at most OLD_COMPANY_BULLETS when it ended long ago."""
    cutoff = f"{calendar_date.today().year - OLD_YEARS}"
    old = max(role["end"] or "9999" for role in company["roles"]) < cutoff
    return min(options.top, OLD_COMPANY_BULLETS) if old else options.top


def company_bullets(company: Company, scored: Iterable[qr.ScoredBullet], options: BuildOptions,
                    already: Sequence[Bullet] = ()) -> list[Bullet]:
    """The bullets to show for one company; at least one proven bullet even when nothing matched the JD."""
    picks = pick([item.bullet for item in scored], bullet_cap(company, options), already)
    if picks:
        return picks
    live = [b for b in company["bullets"] if evidence.admissible(b)]
    return pick(sorted(live, key=lambda b: -len(b["sources"])), 1, already)


def choose_experience(result: qr.Analysis, options: BuildOptions) -> list[tuple[Company, list[Bullet]]]:
    """The bullets for every company, with no claim repeated across employers and, when `max_bullets` is set,
    a total length limit (the longest lists lose their last bullet first; each company keeps at least one)."""
    chosen: list[tuple[Company, list[Bullet]]] = []
    used: list[Bullet] = []
    for company, scored in result.ranked:
        picks = company_bullets(company, scored, options, used)
        used += picks
        chosen.append((company, picks))
    cover_gaps(result, chosen, options)
    least = sum(1 for _, p in chosen if p)
    if options.max_bullets and options.max_bullets < least:
        raise common.ToolError(f"--max-bullets {options.max_bullets} is too small: each of the {least} employers "
                               f"keeps at least one bullet, so use {least} or more")
    while options.max_bullets and sum(len(p) for _, p in chosen) > options.max_bullets:
        longest = max(chosen, key=lambda pair: len(pair[1]))[1]
        if len(longest) <= 1:
            break
        longest.pop()
    return chosen


def shows(bullet: Bullet, skill: str, terms: Mapping[str, str] | None = None) -> bool:
    """True when the bullet shows the skill: it is tagged with it, or (for a requirement that is not a stored
    skill) its words name it, and the line does not explicitly deny professional use of that skill."""
    named = skill in bullet["skills"] or pr.term_found(skill, bullet["text"])
    return named and evidence.use_state(bullet["text"], skill, bullet["skills"], terms) != evidence.NOT_DEMONSTRATED


def set_aside_lines(companies: Iterable[Company], need: Iterable[str],
                    terms: Mapping[str, str] | None = None) -> list[str]:
    """One plain sentence for each stored line that is not demonstrated for, or reads like training for, a skill
    the posting asks for; nothing is dropped without being listed."""
    notes: list[str] = []
    for company in companies:
        for bullet in company["bullets"]:
            for skill in need:
                if skill not in bullet["skills"] and not pr.term_found(skill, bullet["text"]):
                    continue
                state = evidence.line_state(bullet, skill, terms)
                if state == evidence.NOT_DEMONSTRATED:
                    how = "not demonstrated in your profile, because the line says it was not used at work"
                elif state == evidence.CONFIRM_USE:
                    how = "the line reads like training, so it counts for at most partial; confirm whether you also used it at work"
                else:
                    continue
                notes.append(f"{skill}: {how}: \u201c{bullet['text'][:100]}\u201d ({company['name']})")
    return notes


def shown_skills(chosen: Sequence[tuple[Company, list[Bullet]]], need: Iterable[str] = (),
                 terms: Mapping[str, str] | None = None) -> set[str]:
    """The skills that the chosen bullets show, including requirements named in a bullet's words; a tag on a line
    that denies using that skill does not count."""
    bullets = [b for _, picks in chosen for b in picks]
    tagged = {skill for b in bullets for skill in b["skills"] if shows(b, skill, terms)}
    return tagged | {n for n in need if any(shows(b, n, terms) for b in bullets)}


def cover_gaps(result: qr.Analysis, chosen: list[tuple[Company, list[Bullet]]], options: BuildOptions) -> None:
    """Make the whole resume cover the posting: for each JD skill you have evidence for but the picks do not
    show, bring in the best-ranked bullet that shows it. It is added to its employer when that employer has
    room, or takes the place of that employer's last bullet when that bullet shows no needed skill that
    nothing else shows. The most-asked skills go first; a bullet that repeats a claim already chosen is not used."""
    room = {company["id"]: bullet_cap(company, options) for company, _ in chosen}
    terms = qr.vocabulary(result.skills)
    picks_of = {company["id"]: picks for company, picks in chosen}
    for skill, _count in result.need.most_common():
        if skill not in result.covered or skill in shown_skills(chosen, result.need, terms):
            continue
        for company, scored in result.ranked:
            used = [b for _, picks in chosen for b in picks]
            pool = [item.bullet for item in scored if shows(item.bullet, skill, terms) and item.bullet not in used
                    and not too_similar(item.bullet, used)]
            picks = picks_of[company["id"]]
            if not pool:
                continue
            if len(picks) < room[company["id"]]:
                picks.append(pool[0])
                break
            rest = [(c, p[:-1] if p is picks else p) for c, p in chosen]
            if not {n for n in result.need if shows(picks[-1], n, terms)} - shown_skills(rest, result.need, terms):
                picks[-1] = pool[0]
                break


def render_experience(result: qr.Analysis, options: BuildOptions,
                      chosen: Sequence[tuple[Company, list[Bullet]]] | None = None) -> list[str]:
    """The experience section: each company once, then each role with its own title and dates and its bullets."""
    lines = ["## Experience", ""]
    for company, picks in chosen if chosen is not None else choose_experience(result, options):
        latest = roles_newest_first(company)[0] if company["roles"] else None
        if not picks and latest is None:
            continue                    # no bullet and no role: nothing to show under the employer
        lines += [f"### {company['name']}", ""]
        groups = role_groups(company, picks) or ([(latest, [])] if latest is not None else [])
        for role, group in groups:
            override = options.titles.get(company["id"]) if role is latest else None
            lines += [f"#### {role_line(role, override)}", ""]
            lines += [f"- {b['text']}" for b in group] + [""]
    return lines


def render_skills(result: qr.Analysis) -> list[str]:
    """The skills the JD asks for, by group."""
    groups = {g: [item["name"] for item in items if item["name"] in result.need]
              for g, items in result.skills["groups"].items()}
    shown = {g: names for g, names in groups.items() if names}
    return ["## Skills", ""] + [f"- **{g}:** {', '.join(names)}" for g, names in shown.items()] + [""] if shown else []


def render_credentials(profile: ResumeProfile, need: Iterable[str] = ()) -> list[str]:
    """Certifications, education and (when the posting asks for a skill a project shows) projects."""
    lines: list[str] = []
    certs = [c["name"] if isinstance(c, dict) else str(c) for c in profile.get("certifications", [])]   # curated: {"name"}
    if certs:
        lines += ["## Certifications", ""] + [f"- {c}" for c in certs] + [""]
    education = clean_education(profile)
    if education:
        lines += ["## Education", ""] + [f"- {e}" for e in education] + [""]
    projects = relevant_projects(profile, need)
    if projects:
        lines += ["## Projects", ""] + [f"- {p}" for p in projects] + [""]
    return lines


def build(text: str, options: BuildOptions, header: str | None) -> tuple[str, BuildNotes]:
    """Markdown resume for the job description; `header` is the name/contact text (None: use the template)."""
    result = qr.analyze(text, (), options.include_review, options.recency, options.requirements)
    lines = [(header or HEADER_TEMPLATE).rstrip(), ""]
    chosen = choose_experience(result, options)
    lines += render_summary(result) + render_experience(result, options, chosen) + render_skills(result)
    lines += render_credentials(result.profile, result.need)
    terms = qr.vocabulary(result.skills)
    shown = shown_skills(chosen, result.need, terms)
    missing = [s for s in result.need if s not in result.covered]
    notes = BuildNotes(used_summary=result.summaries[0]["id"] if result.summaries else None,
                       missing=missing, hidden=result.hidden, header_missing=header is None,
                       selected=[b["id"] for _, picks in chosen for b in picks],
                       not_shown=[s for s in result.need if s in result.covered and s not in shown],
                       shown_count=len([s for s in result.need if s in shown]), need_count=len(result.need),
                       unplaced=unplaced(chosen), requirements_given=bool(options.requirements), possible=result.possible,
                       set_aside=set_aside_lines((company for company, _ in result.ranked), result.need, terms),
                       no_bullets=[company["name"] for company, picks in chosen if not picks and company["roles"]])
    return "\n".join(lines).rstrip() + "\n", notes


def next_revision(directory: Path, name: str) -> Path:
    """`<name>.md` in `directory`, or `<name>-2.md`, `-3.md` ... when that file exists: a new build never
    overwrites an earlier application's resume."""
    out, n = directory / f"{name}.md", 2
    while out.exists():
        out, n = directory / f"{name}-{n}.md", n + 1
    return out


def write_record(out: Path, args: argparse.Namespace, text: str, notes: BuildNotes) -> Path:
    """Save `<resume>.build.json` next to the resume: the job description's fingerprint, the settings and the
    ids of the chosen bullets, so a later review can tell what the draft was built from."""
    record = {"built": common.now(), "review": None, "jd": "stdin" if args.jd == "-" else Path(args.jd).name,
              "jd_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
              "settings": {"top": args.top, "titles": args.title, "recency": args.recency, "requirements": args.requirement,
                           "include_review": args.include_review, "max_bullets": args.max_bullets},
              "summary": notes.used_summary, "bullets": notes.selected, "header_present": not notes.header_missing,
              "no_supporting_bullet": notes.missing, "not_shown": notes.not_shown,
              "possible_matches": [{"skill": n, "sentence": q} for n, q in notes.possible]}
    path = out.with_suffix(".build.json")
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def record_path(resume: Path) -> Path:
    """The `.build.json` record that belongs to a resume file."""
    return resume.with_suffix(".build.json")


def file_sha(path: Path) -> str:
    """Fingerprint of a resume file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_status(resume: Path) -> str:
    """draft (built, not approved), approved, or changed (edited after approval, so approval no longer holds)."""
    if not resume.is_file():
        raise common.ToolError(f"{resume} does not exist.")
    try:
        review = json.loads(record_path(resume).read_text(encoding="utf-8")).get("review")
    except (OSError, ValueError):
        review = None
    if not review:
        return "draft"
    return "approved" if review.get("sha256") == file_sha(resume) else "changed"


def cmd_approve(args: argparse.Namespace) -> None:
    """Record that the user has reviewed this resume and says it is ready. Run it only after they confirm."""
    resume = Path(args.approve)
    review_status(resume)                                   # fails when the file is missing
    if HEADER_TEMPLATE.splitlines()[0] in resume.read_text(encoding="utf-8").splitlines():
        raise common.ToolError("This resume still has the placeholder name and contact line. Fill in header.md, "
                               "build again, then approve.")
    path = record_path(resume)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    record["review"] = {"status": "approved", "at": common.now(), "sha256": file_sha(resume)}
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Approved {resume.name}. Editing it afterwards makes its status 'changed'.")


def cmd_status(args: argparse.Namespace) -> None:
    """Print the review status of a built resume."""
    print(f"{Path(args.status).name}: {review_status(Path(args.status))}")


def cmd_build(args: argparse.Namespace) -> None:
    """Build a resume, or with --approve / --status record or show a built resume's review."""
    if args.approve:
        cmd_approve(args)
    elif args.status:
        cmd_status(args)
    elif args.jd:
        build_and_write(args)
    else:
        raise common.ToolError("give a job description file (or -), or --approve FILE, or --status FILE")


def build_and_write(args: argparse.Namespace) -> None:
    """Build the resume for the job description in `args.jd`, write it with its record, and report gaps."""
    text = common.read_text_arg(args.jd)
    header_path = header_file()
    header = header_path.read_text(encoding="utf-8") if header_path.exists() else None
    options = BuildOptions(args.top, dict(t.split("=", 1) for t in args.title), args.include_review, args.recency,
                           args.max_bullets, tuple(args.requirement))
    markdown, notes = build(text, options, header)

    name = "resume" if args.jd == "-" else Path(args.jd).stem
    out = Path(args.output) if args.output else next_revision(OUTPUT_DIR, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    record = write_record(out, args, text, notes)

    if notes.header_missing:
        header_path.write_text(HEADER_TEMPLATE, encoding="utf-8")
        print(f"Created {header_path.name} template: put your name and contact line there, then re-run "
              "(this draft still has the placeholder name and contact line).")
    print(f"Wrote {out} (record: {record.name})")
    print(f"Opening summary: {notes.used_summary}")
    print("JD skills with no supporting bullet: " + (", ".join(notes.missing) or "none"))
    print(f"JD skills shown in this resume: {notes.shown_count} of {notes.need_count}")
    qr.print_possible(notes.possible)
    if not notes.requirements_given:
        print(qr.NOT_CHECKED.strip())
    if notes.not_shown:
        print("JD skills you have evidence for that this draft does not show: " + ", ".join(notes.not_shown))
    if notes.set_aside:
        print("Lines set aside or capped for the skills the posting asks for:")
        print("\n".join(f"  - {note}" for note in notes.set_aside))
    if notes.unplaced:
        print(f"{notes.unplaced} bullet(s) have no matching role and sit under the employer's latest role: check them.")
    if notes.no_bullets:
        print("No usable bullet for " + ", ".join(notes.no_bullets) + ": the resume shows only its role line. "
              "Check these employers.")
    if notes.hidden:
        print(f"{notes.hidden} bullet(s) flagged needs_review were left out.")
    print(REVIEW_CHECKLIST)
    print(f"Status: draft. After you have reviewed it: build-resume --approve {out}")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("jd", nargs="?", help="job description text file, or - for stdin")
    parser.add_argument("--approve", metavar="RESUME", help="record that you reviewed this built resume and it is ready "
                        "(refused while it has the placeholder header; editing it later makes the status 'changed')")
    parser.add_argument("--status", metavar="RESUME", help="show whether a built resume is draft, approved or changed")
    parser.add_argument("-o", "--output", help="output path (default output/resumes/<jd file name>.md, "
                        "or -2, -3 ... when that file exists; an explicit path is overwritten)")
    parser.add_argument("--top", type=int, default=4, help="bullets per company (default 4; old companies get at most 2)")
    parser.add_argument("--title", action="append", default=[], metavar="COMPANY=TITLE",
                        help='override the job title shown for a company id, e.g. --title <company-id>="placeholder"')
    parser.add_argument("--max-bullets", type=int, help="limit the total number of bullets in the resume")
    parser.add_argument("--recency", type=float, default=2.0, help="recency weight, as in query-resume for-jd")
    parser.add_argument("--include-review", action="store_true", help="allow bullets flagged needs_review")
    parser.add_argument("--requirement", action="append", default=[], metavar="NAME",
                        help="a skill or duty the posting asks for, even if it is not a stored skill (repeatable); "
                        "one with no supporting bullet is reported as a gap")
    parser.set_defaults(fn=cmd_build)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
