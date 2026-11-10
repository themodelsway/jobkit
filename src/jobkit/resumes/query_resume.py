#!/usr/bin/env python3
"""Query the stored resume data (read-only, standard library only).

  query-resume for-jd jd.txt         # rank bullets per company for a job description ("-" = stdin; alias: match)
  query-resume search --skill Python    # filter bullets (also --company, --text, --theme)
  query-resume review                # bullets flagged needs_review, one-source skills, untagged themes
  query-resume stats                 # counts per company and skill group
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, NamedTuple, cast

from jobkit import common
from jobkit.resumes import evidence
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables
from jobkit.resumes.resume_data import Bullet, Company, ResumeProfile, Skills, Summary

STOP: Final[frozenset[str]] = frozenset("""a about above after all also an and any are as at be been being but by can could do
does for from had has have having how if in into is it its more most must of on or other our out over per should so such
than that the their them then there these they this those through to under up us use using was we were what when where
which while who will with within without would you your work working experience years year strong ability team teams
role roles including include etc new highly""".split())
MAX_OVERLAP: Final[int] = 8              # words shared with the JD that still add to a bullet's score
MAX_SKILL_MENTIONS: Final[int] = 3       # mentions of one JD skill that still add to the score
NEEDS_REVIEW_PENALTY: Final[float] = 6.0
SOURCE_STEP: Final[float] = 0.1          # repeats across resume files are provenance, not proof: a small, capped credit
SOURCE_STEPS: Final[int] = 5             # at most 5 extra files count, so repeats add at most 0.5
NOT_CHECKED: Final[str] = ("\nNo --requirement was given, so requirements outside your stored skills were not checked. Pass each "
                           "skill or duty the posting asks for as --requirement NAME to see it as a gap.")
MIN_EVIDENCE: Final[int] = 2             # theme hits needed to list a bullet that matches no skill (or OVERLAP_ENOUGH words)
OVERLAP_ENOUGH: Final[int] = 4

# JD wording that implies a theme (themes are tagged on bullets with `process-resumes curate add theme`)
THEME_HINTS: Final[dict[str, list[str]]] = {
    "topic-06": ["placeholder", "topic-09", "placeholder", "placeholder", "placeholder"], "topic-09": ["topic-09"],
    "topic-12": ["topic-12", "placeholder", "placeholder", "placeholder"], "topic-01": ["placeholder"],
    "topic-19": ["topic-19", "placeholder"], "topic-04": ["placeholder", "placeholder", "placeholder"],
    "topic-03": ["placeholder", "placeholder"], "topic-16": ["topic-16", "placeholder", "placeholder"],
    "mentoring": ["mentor", "coach"], "executive-advisory": ["executive", "c-suite", "senior leadership"],
    "workshops": ["workshop"], "topic-18": ["topic-18", "placeholder", "placeholder"],
    "governance-compliance": ["governance", "compliance", "regulat"], "topic-20": ["placeholder"],
    "topic-17": ["topic-17", "placeholder", "placeholder"], "topic-13": ["placeholder"],
    "topic-15": ["topic-15", "placeholder"], "topic-14": ["placeholder", "placeholder"],
    "topic-07": ["placeholder"], "topic-02": ["placeholder", "placeholder", "placeholder"],
    "team-leadership": ["manage a team", "lead a team", "people manag", "engineering manager", "build and lead"],
    "budget-financial": ["budget", "p&l"], "topic-08": ["developer productivity", "placeholder"],
    "strategy-roadmap": ["roadmap", "strategy"], "topic-05": ["placeholder", "placeholder", "placeholder"],
}

# JD wording that implies which angle the opening summary should take
ANGLE_HINTS: Final[dict[str, list[str]]] = {
    "focus-3": ["placeholder", "placeholder", "placeholder", "placeholder",
                                "business capabilit"],
    "focus-1": ["cloud", "aws", "azure", "gcp"],
    "focus-4": ["topic-12", "placeholder", "placeholder", "placeholder", "placeholder", "placeholder", "placeholder",
                 " ai "],
    "focus-2": ["placeholder", "placeholder", "lead a team", "people manag",
                               "build and lead", "mentor", "direct reports"],
    "topic-17": ["topic-17", "placeholder", "placeholder", "placeholder", "topic-15"],
}


class ScoredBullet(NamedTuple):
    """A bullet that matched the JD: its score, the bullet, and the skills/themes that matched."""

    score: float
    bullet: Bullet
    why: list[str]


@dataclass
class Analysis:
    """Result of scoring a job description against the resume data.

    Also readable like a dict (`analysis["ranked"]`) for callers that predate the dataclass.
    """

    need: Counter[str]
    themes: set[str]
    angles: dict[str, int]
    summaries: list[Summary]
    ranked: list[tuple[Company, list[ScoredBullet]]]
    covered: set[str] = field(default_factory=set)
    hidden: int = 0
    possible: list[tuple[str, str]] = field(default_factory=list)   # (skill, sentence) to confirm: see parse_resume
    skills: Skills = field(default_factory=lambda: Skills(groups={}))
    profile: ResumeProfile = field(default_factory=rd.empty_profile)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass(frozen=True)
class JdContext:
    """What a bullet is scored against."""

    need: Counter[str]
    words: set[str]
    themes: set[str]
    recency: Mapping[str, float]
    recency_weight: float
    plain: tuple[str, ...] = ()        # requirements that are not stored skills, found by their words in a bullet
    terms: Mapping[str, str] = field(default_factory=dict)   # {name or alias: canonical skill}


def load() -> tuple[dict[str, Company], Skills]:
    """(companies by id, skills) from the stored data. Raises OSError when there is no resume data."""
    skills = cast("Skills | None", tables.load_skills())
    if skills is None:
        raise FileNotFoundError(rd.MISSING_DATA)
    return rd.load_companies(), skills


def load_or_fail() -> tuple[dict[str, Company], Skills]:
    """Like `load`, but a missing data folder becomes a ToolError with the instruction to build it."""
    if not tables.has_resume_data():
        raise common.ToolError(rd.MISSING_DATA)
    return load()


def newest_first(companies: Mapping[str, Company]) -> list[Company]:
    """The companies ordered by their most recent role, newest first."""
    return rd.newest_first(companies.values())


def words(text: str) -> set[str]:
    """Lower-case content words (4+ characters, no stop words)."""
    return {w for w in re.findall(r"[a-z][a-z0-9+#.\-]{3,}", text.lower()) if w not in STOP}


def vocabulary(skills: Skills) -> dict[str, str]:
    """{term: canonical name} from skill names, aliases and tag-only terms."""
    terms = pr.skill_terms(skills["groups"])
    terms.update({t: t for t in skills.get("tag_only", [])})
    return terms


def jd_skills(text: str, terms: Mapping[str, str]) -> Counter[str]:
    """Canonical skills mentioned in the JD, with mention counts."""
    counts: Counter[str] = Counter()
    for term, name in terms.items():
        found = pr.term_count(term, text)
        if found:
            counts[name] += found
    return counts


def add_requirements(need: Counter[str], text: str, requirements: Iterable[str], terms: Mapping[str, str]) -> tuple[str, ...]:
    """Add the requirements the assistant took from the posting to `need`. A name that is a stored skill or alias
    (any capitalisation) counts as that skill; any other name is kept as plain text and returned, to be searched
    for in the bullets. Each requirement counts at least once."""
    lower = {t.lower(): n for t, n in terms.items()}
    plain: list[str] = []
    for raw in requirements:
        name = raw.strip()
        if not name:
            continue
        stored = lower.get(name.lower())
        if stored is not None:
            need[stored] = max(need[stored], 1)
        elif name not in need:
            need[name] = max(1, pr.term_count(name, text))
            plain.append(name)
    return tuple(plain)


def month_number(date: str | None) -> int | None:
    """Months since year 0 for a 'YYYY-MM' date, else None."""
    found = re.fullmatch(r"(\d{4})-(\d{2})", date or "")
    return int(found.group(1)) * 12 + int(found.group(2)) if found else None


def recency_scores(companies: Mapping[str, Company]) -> dict[str, float]:
    """{bullet id: 0..1}: how recent the role the bullet belongs to is, from the role's own start date (the newest
    role scores 1, the oldest 0). A bullet with no known role takes its company's latest role. The date of the
    resume file that holds the bullet plays no part."""
    starts = [m for c in companies.values() for r in c["roles"] if (m := month_number(r["start"])) is not None]
    low, high = (min(starts), max(starts)) if starts else (0, 0)
    out: dict[str, float] = {}
    for company in companies.values():
        latest = max((m for r in company["roles"] if (m := month_number(r["start"])) is not None), default=None)
        for bullet in company["bullets"]:
            when = month_number(bullet["role_start"]) or latest
            out[bullet["id"]] = (when - low) / (high - low) if when is not None and high > low else 1.0
    return out


def show(bullet: Bullet, why: Iterable[str] | None = None) -> None:
    """Print one bullet with its id, source count, metrics and what matched."""
    flag = "  [NEEDS REVIEW]" if bullet.get("needs_review") else ""
    print(f"  - {bullet['text']}{flag}")
    meta = [f"id {bullet['id']}", f"in {len(bullet['sources'])} resume file(s)"]
    if bullet["metrics"]:
        meta.append("metrics: " + ", ".join(bullet["metrics"]))
    if why:
        meta.append("matches: " + ", ".join(why))
    print("    " + " | ".join(meta))


# ---------------------------------------------------------------- scoring

def infer_themes(low: str, extra: Iterable[str]) -> set[str]:
    """Themes the JD implies (from THEME_HINTS) plus any the user asked to favour."""
    return {t.lower() for t in extra} | {t for t, keys in THEME_HINTS.items() if any(k in low for k in keys)}


def jd_angles(low: str) -> dict[str, int]:
    """{summary angle: mentions} for the angles the JD talks about."""
    counts = {g: sum(low.count(k) for k in keys) for g, keys in ANGLE_HINTS.items()}
    return {g: n for g, n in counts.items() if n}


def rank_summaries(summaries: Iterable[Summary], angles: Mapping[str, int]) -> list[Summary]:
    """Opening summaries, best fit for the JD's angles first."""
    def fit(summary: Summary) -> float:
        wanted = sum(angles.get(g, 0) for g in summary["angles"])
        return -(wanted - 0.5 * len([g for g in summary["angles"] if g not in angles]))
    return sorted(summaries, key=fit)


def score_bullet(bullet: Bullet, ctx: JdContext) -> ScoredBullet | None:
    """Score a bullet for the JD; None when it is not relevant enough to list."""
    tagged = bullet["skills"]
    shared = [s for s in tagged if s in ctx.need and evidence.use_state(bullet["text"], s, tagged, ctx.terms) != evidence.NOT_DEMONSTRATED]
    shared += [t for t in ctx.plain if pr.term_found(t, bullet["text"])
               and evidence.use_state(bullet["text"], t, tagged, ctx.terms) != evidence.NOT_DEMONSTRATED]
    overlap = len(words(bullet["text"]) & ctx.words)
    theme_hits = [t for t in bullet["themes"] if t.lower() in ctx.themes]
    score = 3 * sum(min(ctx.need[s], MAX_SKILL_MENTIONS) for s in shared) + min(overlap, MAX_OVERLAP)
    score += 2 * len(theme_hits)
    score += SOURCE_STEP * min(len(bullet["sources"]) - 1, SOURCE_STEPS) + (1 if bullet["metrics"] else 0)
    if bullet.get("needs_review"):
        score -= NEEDS_REVIEW_PENALTY                                         # unverified ranks below confirmed
    score += ctx.recency_weight * ctx.recency[bullet["id"]]                   # nudge toward recent roles
    if shared or len(theme_hits) >= MIN_EVIDENCE or overlap >= OVERLAP_ENOUGH:
        return ScoredBullet(score, bullet, shared + theme_hits)
    return None


def rank_company(company: Company, ctx: JdContext, include_review: bool,
                 view: Callable[[Bullet], Bullet] | None = None) -> tuple[list[ScoredBullet], int]:
    """(scored bullets best first, number of needs_review bullets left out) for one company.

    With `view` (the line as it will be printed), a bullet is still listed for what its stored line shows, but is
    ranked by what the printed wording shows; a printed wording that shows nothing of the posting ranks last."""
    scored: list[ScoredBullet] = []
    hidden = 0
    for bullet in (b for b in company["bullets"] if not b.get("ignored")):
        if bullet.get("needs_review") and not include_review:
            hidden += 1
            continue
        result = score_bullet(bullet, ctx)
        if result and view:
            printed = score_bullet(view(bullet), ctx)
            result = result._replace(score=printed.score if printed else 0.0)
        if result:
            scored.append(result)
    scored.sort(key=lambda s: -s.score)
    return scored, hidden


def analyze(text: str, extra_themes: Iterable[str] = (), include_review: bool = False,
            recency_weight: float = 2.0, requirements: Iterable[str] = (),
            view: Callable[[Bullet], Bullet] | None = None) -> Analysis:
    """Score a job description against the resume data. Shared by `for-jd` and build_resume.py.
    `requirements` are skills the assistant took from the posting; each one is searched for and reported.
    `view` turns a stored line into the line as it will be printed, so bullets are ranked by what the resume shows."""
    companies, skills = load_or_fail()
    terms = vocabulary(skills)
    need = jd_skills(text, terms)
    plain = add_requirements(need, text, requirements, terms)
    low = text.lower()
    angles = jd_angles(low)
    profile: ResumeProfile = rd.load_profile()
    ctx = JdContext(need, words(text), infer_themes(low, extra_themes), recency_scores(companies), recency_weight,
                    plain, terms)
    result = Analysis(need, ctx.themes, angles, rank_summaries(profile["summaries"], angles), [], skills=skills,
                      profile=profile, possible=pr.possible_matches(text, terms))
    for company in newest_first(companies):
        scored, hidden = rank_company(company, ctx, include_review, view)
        result.hidden += hidden
        result.covered.update(s for item in scored for s in item.why if s in need)
        result.ranked.append((company, scored))
    return result


# ---------------------------------------------------------------- commands

def print_jd_overview(result: Analysis, summaries: int) -> None:
    """The themes, skills and angles found in the JD, and the suggested opening summaries."""
    need = result.need
    print("Themes inferred from JD: " + (", ".join(sorted(result.themes)) or "none"))
    print(f"JD skills found ({len(need)}): "
          + ", ".join(f"{k}" + (f" x{v}" if v > 1 else "") for k, v in need.most_common()))
    angles = sorted(result.angles.items(), key=lambda x: -x[1])
    print("Summary angles in JD: " + (", ".join(f"{g} x{n}" for g, n in angles) or "none"))
    print("\n== Suggested opening summaries")
    for summary in result.summaries[:summaries]:
        print(f"  - {summary['text']}\n    id {summary['id']} | angles: {', '.join(summary['angles'])} "
              f"| {len(summary['sources'])} resume(s)")


def print_company(company: Company, scored: Sequence[ScoredBullet], top: int) -> None:
    """One company's heading and best bullets."""
    titles = "; ".join(sorted({t for role in company["roles"] for t in role["titles"]}))[:70]
    print(f"\n== {company['name']}  ({titles})")
    if not scored:
        print("  (no matching bullets)")
    for item in scored[:top]:
        show(item.bullet, item.why)


def print_possible(possible: Sequence[tuple[str, str]]) -> None:
    """Skill names that are also ordinary words, used where they cannot be told apart: for a person to confirm."""
    if not possible:
        return
    print("\n== Possible matches to confirm (the word is also an ordinary one; pass the real ones with --requirement):")
    for name, sentence in possible:
        print(f'  {name}: "{sentence}"')


def print_skill_coverage(result: Analysis) -> None:
    """JD skills with no matching bullet, and the skills worth featuring by group."""
    need, skills = result.need, result.skills
    missing = [s for s in need if s not in result.covered]
    print("\n== JD skills with no matching bullet:", ", ".join(missing) or "none")
    in_list = {item["name"] for group in skills["groups"].values() for item in group}
    print("== of those, in your skills list anyway:", ", ".join(s for s in missing if s in in_list) or "none")
    print("\n== Skills to feature, by group:")
    for group, items in skills["groups"].items():
        names = [item["name"] for item in items if item["name"] in need]
        if names:
            print(f"  {group}: " + ", ".join(names))


def cmd_for_jd(args: argparse.Namespace) -> None:
    """Rank bullets per company for a job description."""
    result = analyze(common.read_text_arg(args.jd), args.theme, args.include_review, args.recency, args.requirement)
    print_jd_overview(result, args.summaries)
    for company, scored in result.ranked:
        print_company(company, scored, args.top)
    if result.hidden:
        print(f"\n({result.hidden} unverified bullet(s) flagged needs_review were left out; "
              "use --include-review to see them)")
    print_skill_coverage(result)
    print_possible(result.possible)
    if not args.requirement:
        print(NOT_CHECKED)


def skill_aliases(skills: Skills) -> dict[str, str]:
    """{lower-case name or alias: canonical skill name}."""
    return {n.lower(): item["name"] for items in skills["groups"].values() for item in items
            for n in [item["name"], *item["aliases"]]}


def bullet_matches(bullet: Bullet, skill: str | None, text: str | None, theme: str | None) -> bool:
    """Whether the bullet passes the search filters."""
    return ((not skill or skill in bullet["skills"])
            and (not text or text.lower() in bullet["text"].lower())
            and (not theme or theme.lower() in (t.lower() for t in bullet["themes"])))


def print_group(company: Company, bullets: Sequence[Bullet], with_skills: bool = False) -> None:
    """The company's name once, then its bullets; nothing when there are no bullets."""
    if bullets:
        print(f"== {company['name']}")
    for bullet in bullets:
        show(bullet, bullet["skills"] if with_skills else None)


def search_matches(companies: Mapping[str, Company], args: argparse.Namespace,
                   skill: str | None) -> list[tuple[Company, list[Bullet]]]:
    """(company, its bullets that pass the filters) for each company with a match, newest company first."""
    found: list[tuple[Company, list[Bullet]]] = []
    for company in newest_first(companies):
        if args.company and args.company.lower() not in (company["id"], company["name"].lower()):
            continue
        bullets = [b for b in company["bullets"]
                   if not b.get("ignored") and bullet_matches(b, skill, args.text, args.theme)]
        if bullets:
            found.append((company, bullets))
    return found


def search_footer(matched: int, limit: int, hidden: Mapping[str, int]) -> str:
    """The closing line: the total, and when the limit cut the list, how many matches each company has left."""
    line = f"\n{matched} bullet(s) matched"
    if matched <= limit:
        return line
    return line + f" (showing {limit}). Not shown: " + "; ".join(f"{name} {n}" for name, n in hidden.items())


def cmd_search(args: argparse.Namespace) -> None:
    """Filter bullets by skill, company, text and theme; `--limit` caps the total printed, newest company first."""
    companies, skills = load_or_fail()
    skill = skill_aliases(skills).get(args.skill.lower(), args.skill) if args.skill else None
    left = max(args.limit, 0)
    matched = 0
    hidden: dict[str, int] = {}
    for company, bullets in search_matches(companies, args, skill):
        matched += len(bullets)
        print_group(company, bullets[:left], with_skills=True)
        if len(bullets) > left:
            hidden[company["name"]] = len(bullets) - left
        left = max(left - len(bullets), 0)
    print(search_footer(matched, max(args.limit, 0), hidden))


def cmd_review(args: argparse.Namespace) -> None:
    """Things that need a human look: flagged bullets, one-source skills, untagged themes."""
    companies, skills = load_or_fail()
    print("Bullets flagged needs_review:")
    for company in newest_first(companies):
        print_group(company, [b for b in company["bullets"] if b.get("needs_review")])
    print("\nSkills seen in only one resume (possible typos):")
    for group, items in skills["groups"].items():
        one = [item["name"] for item in items if len(item["sources"]) == 1]
        if one:
            print(f"  {group}: " + ", ".join(one))
    total = sum(len(c["bullets"]) for c in companies.values())
    live = [b for c in companies.values() for b in c["bullets"] if not b.get("ignored")]
    orphans = rd.orphan_curation(companies, rd.load_profile(), rd.load_themes_file(), rd.load_curated())
    print("\nCuration entries that match no bullet or summary:" + ("" if orphans else " none"))
    for orphan in orphans:
        print(f"  {orphan}")
    print(f"\nBullets without themes: {sum(1 for b in live if not b['themes'])} of {len(live)} "
          f"(ignored fragments: {total - len(live)})")


def cmd_stats(args: argparse.Namespace) -> None:
    """Counts per company and skill group."""
    companies, skills = load_or_fail()
    ledger = rd.load_ledger()
    resumes = sum(1 for v in ledger.values() if v["kind"] == "resume")
    print(f"Resumes processed: {resumes} (+{len(ledger) - resumes} non-resume files skipped)")
    for company in newest_first(companies):
        print(f"  {company['name']:<30} {len(company['bullets']):>3} bullets, {len(company['roles'])} role(s)")
    print("Skill groups: " + ", ".join(f"{g} {len(v)}" for g, v in skills["groups"].items()))


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    match = sub.add_parser("for-jd", aliases=["match"], help="rank bullets per company for a job description")
    match.add_argument("jd", help="path to a text file with the job description, or - for stdin")
    match.add_argument("--top", type=int, default=3, help="bullets per company (default 3)")
    match.add_argument("--recency", type=float, default=2.0,
                       help="max score bonus for bullets from recent roles (default 2.0; 0 turns it off)")
    match.add_argument("--summaries", type=int, default=2, help="opening summaries to suggest (default 2)")
    match.add_argument("--include-review", action="store_true", help="also show bullets flagged needs_review")
    match.add_argument("--theme", action="append", default=[], help="extra theme to favour (repeatable)")
    match.add_argument("--requirement", action="append", default=[], metavar="NAME",
                       help="a skill or duty the posting asks for, even if it is not a stored skill (repeatable); "
                       "one with no supporting bullet is reported as a gap")
    match.set_defaults(fn=cmd_for_jd)
    search = sub.add_parser("search", help="filter bullets")
    for flag in ("--skill", "--company", "--text", "--theme"):
        search.add_argument(flag)
    search.add_argument("--limit", type=int, default=20,
                        help="most bullets to print across all companies (default 20); the last line says "
                        "how many matches each company has that were not shown")
    search.set_defaults(fn=cmd_search)
    sub.add_parser("review", help="things that need a human look").set_defaults(fn=cmd_review)
    sub.add_parser("stats", help="counts").set_defaults(fn=cmd_stats)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
