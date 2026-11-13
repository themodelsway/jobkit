#!/usr/bin/env python3
"""Build a simple markdown resume tailored to a job description (read-only on the resume data).

  build-resume jd.txt                       # writes output/resumes/<jd name>.md (+ .build.json record; never overwrites: -2, -3 ...)
  build-resume jd.txt -o out.md --top 5     # custom path / bullets per company
  build-resume - < jd.txt                   # job description from stdin
  build-resume --approve out.md             # after you have reviewed it: record it as approved
  build-resume --status out.md              # draft | approved | changed (edited after approval)

Picks, from the stored resume data: the best-fitting opening summary, the best bullets for each company
(same scoring as `query-resume for-jd`), the skills the JD asks for (grouped), certifications and education.

Name and contact lines are NOT stored in the resume data. They come from the saved header (`profile header set`); output goes to output/.
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

from jk import common
from jk.resumes import evidence
from jk.resumes import parse_resume as pr
from jk.resumes import query_resume as qr
from jk.resumes import lines as line_rules
from jk.resumes import resume_data as rd
from jk.resumes.resume_data import LINE_LIMIT, LINE_WARN, SUMMARY_LIMIT, Bullet, Company, ResumeProfile, Role, SkillEntry, Summary
from jk.user import profile as up

OUTPUT_DIR: Path = common.output_dir() / "resumes"
HEADER_TEMPLATE: Final[str] = """# Your Name
City, ST | phone | email | linkedin.com/in/you
"""
OLD_YEARS: Final[int] = 8            # companies that ended more than this many years ago get fewer bullets
OLD_COMPANY_BULLETS: Final[int] = 2
SIMILARITY_LIMIT: Final[float] = 0.3
SAME_FIGURE_SIMILARITY: Final[float] = 0.2   # a shared figure only means "same claim" when the wording also overlaps
SAME_FIGURE_WORDS: Final[int] = 4             # ...or this many shared words, which is the same topic told twice
REWORDED_SHARE: Final[float] = 0.5            # a line whose words are at least this share inside another line is a rewording
REWORDED_WORDS: Final[int] = 5                # ...and shares at least this many words with it
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
    too_long: list[str] = field(default_factory=list)


def stored_header() -> str | None:
    """The name and contact lines saved with `profile header set` (None when none is saved)."""
    return up.header_text()


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


def figures(bullet: Bullet) -> set[str]:
    """The bullet's figures in one spelling, so "70 percent" and "70%" are the same figure."""
    found = {re.sub(r"\s+", "", m.lower().replace("percent", "%")) for m in bullet["metrics"]}
    return found | {f"{n}%" for n in re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", bullet["text"], re.I)}


def plain_words(text: str) -> set[str]:
    """Content words with hyphens and dashes removed, so "Rails-based" and "Rails–based" are the same word."""
    return qr.words(re.sub(r"[\-\u2010-\u2015]", "", text))


def too_similar(bullet: Bullet, chosen: Iterable[Bullet]) -> bool:
    """True if the bullet repeats a claim already chosen: mostly the same words, or the same figure with some
    shared wording (a fifth of the words, or SAME_FIGURE_WORDS words). Two different results that happen to
    share a number (20% and 20%) are both kept."""
    words = plain_words(bullet["text"])
    for other in chosen:
        other_words = plain_words(other["text"])
        shared = len(words & other_words)
        if shared >= REWORDED_WORDS and shared / max(1, min(len(words), len(other_words))) >= REWORDED_SHARE:
            return True
        overlap = len(words & other_words) / max(1, len(words | other_words))
        shared_figure = bool(figures(bullet) & figures(other))
        same_topic = len(words & other_words) >= SAME_FIGURE_WORDS
        if overlap >= SIMILARITY_LIMIT or (shared_figure and (overlap >= SAME_FIGURE_SIMILARITY or same_topic)):
            return True
    return False


def pick(candidates: Iterable[Bullet], n: int, already: Sequence[Bullet] = ()) -> list[Bullet]:
    """The first n candidates that do not repeat each other or a bullet already used elsewhere in the resume."""
    chosen: list[Bullet] = []
    for bullet in candidates:
        if len(chosen) < n and not too_similar(bullet, [*already, *chosen]):
            chosen.append(bullet)
    return chosen


def best_summary(result: qr.Analysis) -> Summary | None:
    """The best-fitting summary that is within SUMMARY_LIMIT characters; when none is, the best-fitting one."""
    fitting = [s for s in result.summaries if len(s["text"]) <= SUMMARY_LIMIT]
    return (fitting or result.summaries or [None])[0]


YEARS_PHRASE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<n>\d{1,2}\+?)(?P<tail>\s+years)(?P<kind>\s+of\s+(?P<what>(?:[\w-]+\s+){0,3}?)experience)?", re.I)
TOTAL_WORDS: Final[frozenset[str]] = frozenset({
    "professional", "industry", "total", "combined", "progressive", "hands-on", "related", "relevant", "software",
    "it", "technology", "technical", "engineering", "leadership", "management", "work", "working"})


def is_total(match: re.Match[str]) -> bool:
    """False for "N years of <something specific> experience" (a skill's own duration, not the whole career)."""
    if not match["kind"]:
        return True
    return all(w.lower() in TOTAL_WORDS for w in match["what"].split())


def with_years(text: str, years: int | None) -> str:
    """The summary with its career-length phrase ("N years" / "N+ years") changed to the user's own figure "YEARS+".
    Only the longest duration that is not a specific skill's ("5 years of Kubernetes experience") is changed; a
    summary with no such phrase is left as it is."""
    totals = [m for m in YEARS_PHRASE.finditer(text) if is_total(m)] if years else []
    if not totals:
        return text
    top = max(totals, key=lambda m: int(m["n"].rstrip("+")))
    return f"{text[:top.start('n')]}{years}+{text[top.end('n'):]}"


def render_summary(result: qr.Analysis) -> list[str]:
    """The opening summary section: one summary of at most SUMMARY_LIMIT characters, with no job title in front
    (the titles are in the experience section) and the years of experience the user gave."""
    summary = best_summary(result)
    return ["## Summary", "", with_years(summary["text"], up.years_experience()), ""] if summary else []


def fitting_text(bullet: Bullet, approved: Mapping[str, str]) -> str:
    """The wording to print for a line, within LINE_LIMIT characters when possible and always the user's own:
    their approved shorter wording (only while it still passes the checks against the stored line), else the line itself when it fits, else the longest stored wording of
    the same line that fits, else the line as stored (the build report lists it as too long)."""
    if approved.get(bullet["id"]) and not line_rules.problems(bullet["text"], approved[bullet["id"]])[0]:
        return approved[bullet["id"]]
    options = [bullet["text"], *bullet.get("variants", []), *(w for ws in bullet.get("wordings", {}).values() for w in ws)]
    fits = [o for o in options if len(o) <= LINE_LIMIT]
    return bullet["text"] if len(bullet["text"]) <= LINE_LIMIT else max(fits, key=len, default=bullet["text"])


def approved_wordings() -> dict[str, str]:
    """{bullet id: the shorter wording the user approved}."""
    return dict(rd.load_curated().get("short_wording", {}))


def printed(bullet: Bullet, approved: Mapping[str, str]) -> Bullet:
    """The line as the resume prints it: the wording that is used, and only the skill tags whose words are still in
    it (a tag is no proof that a requirement is visible once the wording that named it was shortened away)."""
    text = fitting_text(bullet, approved)
    if text == bullet["text"]:
        return bullet
    return {**bullet, "text": text, "skills": [s for s in bullet["skills"] if pr.term_found(s, text)]}


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
                 terms: Mapping[str, str] | None = None, approved: Mapping[str, str] | None = None) -> set[str]:
    """The skills that the printed lines show (their wording as it will be printed), including requirements named
    in a line's words; a tag on a line that denies using that skill does not count."""
    wording = approved_wordings() if approved is None else approved
    bullets = [printed(b, wording) for _, picks in chosen for b in picks]
    tagged = {skill for b in bullets for skill in b["skills"] if shows(b, skill, terms)}
    return tagged | {n for n in need if any(shows(b, n, terms) for b in bullets)}


def cover_gaps(result: qr.Analysis, chosen: list[tuple[Company, list[Bullet]]], options: BuildOptions) -> None:
    """Make the whole resume cover the posting: for each JD skill you have evidence for but the picks do not
    show, bring in the best-ranked bullet that shows it. It is added to its employer when that employer has
    room, or takes the place of that employer's last bullet when that bullet shows no needed skill that
    nothing else shows. The most-asked skills go first; a bullet that repeats a claim already chosen is not used."""
    room = {company["id"]: bullet_cap(company, options) for company, _ in chosen}
    terms = qr.vocabulary(result.skills)
    approved = approved_wordings()
    picks_of = {company["id"]: picks for company, picks in chosen}
    for skill, _count in result.need.most_common():
        if skill not in result.covered or skill in shown_skills(chosen, result.need, terms, approved):
            continue
        for company, scored in result.ranked:
            used = [b for _, picks in chosen for b in picks]
            pool = [item.bullet for item in scored if shows(printed(item.bullet, approved), skill, terms)
                    and item.bullet not in used
                    and not too_similar(item.bullet, used)]
            picks = picks_of[company["id"]]
            if not pool:
                continue
            if len(picks) < room[company["id"]]:
                picks.append(pool[0])
                break
            rest = [(c, p[:-1] if p is picks else p) for c, p in chosen]
            last = printed(picks[-1], approved)
            if not {n for n in result.need if shows(last, n, terms)} - shown_skills(rest, result.need, terms, approved):
                picks[-1] = pool[0]
                break


def render_experience(result: qr.Analysis, options: BuildOptions,
                      chosen: Sequence[tuple[Company, list[Bullet]]] | None = None) -> list[str]:
    """The experience section: each company once, then each role with its own title and dates and its bullets."""
    lines = ["## Experience", ""]
    approved = approved_wordings()
    for company, picks in chosen if chosen is not None else choose_experience(result, options):
        latest = roles_newest_first(company)[0] if company["roles"] else None
        if not picks and latest is None:
            continue                    # no bullet and no role: nothing to show under the employer
        lines += [f"### {company['name']}", ""]
        groups = role_groups(company, picks) or ([(latest, [])] if latest is not None else [])
        for role, group in groups:
            override = options.titles.get(company["id"]) if role is latest else None
            lines += [f"#### {role_line(role, override)}", ""]
            lines += [f"- {fitting_text(b, approved)}" for b in group] + [""]
    return lines


SKILL_CAP: Final[int] = 10                    # most skills shown per group
ECHO_MIN_LENGTH: Final[int] = 5               # a shared word this long (or longer) counts as an echo
ECHO_IGNORED: Final[frozenset[str]] = frozenset({
    "building", "strategic", "creative", "problem", "solving", "collaborative", "impactful", "allocation",
    "growth", "mindset", "process", "design", "execution", "delivery", "continuous", "improvement", "cloud",
    "systems", "software", "platform", "business", "management", "team", "data", "model", "models", "large", "language", "engineering"})


def stem(word: str) -> str:
    """A word without a plural or -ing ending, so "stakeholders" and "stakeholder" compare equal."""
    return re.sub(r"(ing|s)$", "", word.lower())


def echoed(name: str, posting_words: set[str]) -> bool:
    """True when a stored skill shares a meaningful word with the posting (Stakeholder management / "stakeholders")."""
    posting = {stem(w.strip(".-")) for w in posting_words}   # `words` keeps a sentence's final full stop
    return any(len(w) >= ECHO_MIN_LENGTH and w.lower() not in ECHO_IGNORED and stem(w) in posting
               for w in re.findall(r"[A-Za-z]+", name))


def skill_tier(item: SkillEntry, result: qr.Analysis, posting: set[str]) -> int | None:
    """0 the posting names it, 1 it shares a meaningful word with the posting, None not shown."""
    name = item["name"]
    if name in result.need:
        return 0
    if echoed(name, posting):
        return 1
    return None


def render_skills(result: qr.Analysis, posting: str = "") -> list[str]:
    """The skills that matter for this posting, by group: the ones it names first, then skills that share a
    meaningful word with it; at most SKILL_CAP per group, the best-evidenced first, groups with the most posting skills first."""
    groups: dict[str, list[tuple[int, str]]] = {}
    posting_words = qr.words(posting)
    for group, items in result.skills["groups"].items():
        ranked = [(tier, -len(item.get("sources", [])), item["name"]) for item in items
                  if (tier := skill_tier(item, result, posting_words)) is not None]
        if ranked:
            groups[group] = [(t, n) for t, _, n in sorted(ranked)][:SKILL_CAP]
    order = sorted(groups, key=lambda g: (-sum(1 for t, _ in groups[g] if t == 0), g))
    if not order:
        return []
    return ["## Skills", ""] + [f"- **{g}:** {', '.join(n for _, n in groups[g])}" for g in order] + [""]


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


def too_long_lines(chosen: Sequence[tuple[Company, list[Bullet]]], summary: Summary | None) -> list[str]:
    """One note for each printed line (and the summary) that is over its limit, with the id to curate it by."""
    approved = approved_wordings()
    notes = [f"{b['id']} ({len(text)} characters{', FAR OVER' if len(text) > LINE_WARN else ''}, {company['name']}): {text}"
             for company, picks in chosen for b in picks if len(text := fitting_text(b, approved)) > LINE_LIMIT]
    notes += [f"{b['id']} (approved wording ignored, it no longer keeps this line's figures or fits {LINE_LIMIT} characters): {b['text']}"
              for _, picks in chosen for b in picks
              if approved.get(b["id"]) and line_rules.problems(b["text"], approved[b["id"]])[0]]
    shown = with_years(summary["text"], up.years_experience()) if summary else ""
    if summary and len(shown) > SUMMARY_LIMIT:
        notes.append(f"{summary['id']} (summary, {len(shown)} characters, limit {SUMMARY_LIMIT}): {shown}")
    return notes


def build(text: str, options: BuildOptions, header: str | None) -> tuple[str, BuildNotes]:
    """Markdown resume for the job description; `header` is the name/contact text (None: use the template)."""
    approved = approved_wordings()
    result = qr.analyze(text, (), options.include_review, options.recency, options.requirements,
                        lambda b: printed(b, approved))
    lines = [(header or HEADER_TEMPLATE).rstrip(), ""]
    chosen = choose_experience(result, options)
    lines += render_summary(result) + render_experience(result, options, chosen) + render_skills(result, text)
    lines += render_credentials(result.profile, result.need)
    terms = qr.vocabulary(result.skills)
    shown = shown_skills(chosen, result.need, terms)
    missing = [s for s in result.need if s not in result.covered]
    summary = best_summary(result)
    notes = BuildNotes(used_summary=summary["id"] if summary else None,
                       missing=missing, hidden=result.hidden, header_missing=header is None,
                       selected=[b["id"] for _, picks in chosen for b in picks],
                       not_shown=[s for s in result.need if s in result.covered and s not in shown],
                       shown_count=len([s for s in result.need if s in shown]), need_count=len(result.need),
                       unplaced=unplaced(chosen), requirements_given=bool(options.requirements), possible=result.possible,
                       set_aside=set_aside_lines((company for company, _ in result.ranked), result.need, terms),
                       no_bullets=[company["name"] for company, picks in chosen if not picks and company["roles"]],
                       too_long=too_long_lines(chosen, summary))
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
        raise common.ToolError("This resume still has the placeholder name and contact line. Save them with "
                               "`profile header set NAME CONTACT_LINE`, build again, then approve.")
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
    header = stored_header()
    options = BuildOptions(args.top, dict(t.split("=", 1) for t in args.title), args.include_review, args.recency,
                           args.max_bullets, tuple(args.requirement))
    markdown, notes = build(text, options, header)

    name = "resume" if args.jd == "-" else Path(args.jd).stem
    out = Path(args.output) if args.output else next_revision(OUTPUT_DIR, name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    record = write_record(out, args, text, notes)

    if notes.header_missing:
        print("No name and contact line is saved yet, so this draft has a placeholder. Save them with "
              "`profile header set NAME CONTACT_LINE`, then build again.")
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
    if notes.too_long:
        print(f"Lines over the {LINE_LIMIT}-character limit (say how many are long and stop there: offer shorter wording only if the user asks; never change a stored line):")
        print("\n".join(f"  - {note}" for note in notes.too_long))
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
