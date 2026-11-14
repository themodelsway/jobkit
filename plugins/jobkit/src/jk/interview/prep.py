#!/usr/bin/env python3
"""Interview-prep stories and engagements, kept in the database. Standard library only.

Stories (STAR narratives)
  prep init              # (alias: skeleton) create/extend the stories and themes from resume data
  prep status            # stories per company: how many are filled
  prep list [--company <company-id>]    # every story: id, status, headline
  prep next [--company <company-id>]   # next empty story to work on (prints it)
  prep show STORY_ID [--style star|soar|carl]
  prep set STORY_ID FIELD VALUE [--style star|soar|carl] [--merge]
        FIELD: situation task action result metric lessons notes status | spoken.60s spoken.2min
               follow_ups likely_questions never_say also_themes   (lists: separate items with ' | ')
               a style's own part names: obstacle (soar), challenge and learning (carl)
        A style is a view of one stored story: obstacle is the task, learning is the lessons, and a challenge is
        the situation followed by the task. Saving a challenge writes the situation; when the task has text it is
        refused unless --merge is given, which empties the task. Spoken versions are shown as written.
  prep styles            # the three answer styles with their parts and a use for each
  prep new STORY_ID --company C --theme T [--headline H] [--engagement E]   # extra story beyond the skeleton
  prep for-jd jd.txt     # ("-" = stdin) stories ranked for a job description (+ typical questions)

Engagements (one real project: facts with a basis, decisions, people), reusable by several stories
  prep engagement add ID --company C --title T [--role R] [--period P] [--summary S]
  prep engagement list|show ID
  prep engagement set ID title|my_role|period|summary|notes VALUE
  prep fact add ENG "text" --basis stated|estimate|unsure|verified-doc|proposed [--source URL] [--note N]
  prep fact set ENG FACT_ID [--text T] [--basis B] [--source URL] [--note N]
  prep fact rm ENG FACT_ID
  prep decision add ENG --what W [--why Y] [--alternatives "a | b"] [--tradeoffs T] [--ownership mine|team|client|shared|unsure]
  prep decision rm ENG DECISION_ID
  prep person add ENG --role R [--note N]

Linking, numbers, follow-ups
  prep link STORY ENG [--facts f1,f2]       # attach engagement and the facts the story relies on
  prep unlink STORY [--facts f1,f2]         # no --facts: detach the engagement entirely
  prep metric add STORY --name N --value V --basis measured|estimated|stated|unknown [--note N]
  prep metric rm STORY NAME
  prep followup add STORY "question"
  prep followup resolve STORY INDEX_OR_TEXT --answer "what the user said"

Reading and checking
  prep search TEXT                           # across stories and engagements
  prep validate [ID] [--style S]             # errors block 'done'; warnings are advice; exit 1 on errors
  prep export [--story S | --engagement E] [--format json|md] [--style S] [-o FILE]
  prep evidence STORY                        # dates the story was practised in sessions (read-only)

The style in force is --style, then the profile's answer_style, then star. A story marked done must be complete in
the style in force; a story already done stays valid while it is complete in any style.

Fact basis: stated (user said it), estimate, unsure (user doubts it), verified-doc (needs a URL), proposed (an
idea the assistant suggested; never the user's claim). Only stated, estimate and verified-doc may back a story.
`init` never overwrites answers you already filled in; it only adds new stories and refreshes the anchors.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from jk import common
from jk.common import ToolError
from jk.interview import story_model as sm
from jk.interview import styles, tables
from jk.interview.story_model import Engagement, Story
from jk.resumes import query_resume as qr
from jk.resumes.resume_data import Bullet, Company, newest_start

FIELDS: Final[tuple[str, ...]] = sm.TEXT_FIELDS
UMBRELLA: Final[frozenset[str]] = frozenset({"topic-12"})     # too broad to be a story on its own
MIN_BULLETS: Final[int] = 4
CAP_RECENT: Final[int] = 12
CAP_OLD: Final[int] = 3
RECENT_YEARS: Final[int] = 5          # companies with a role starting within this many years are "recent"
THEME_BONUS: Final[int] = 3
NO_STORIES: Final[str] = "No stories yet: run `prep init` first."

# Typical questions per theme (extend freely; unknown themes simply get none)
QUESTIONS: Final[dict[str, list[str]]] = {
    "topic-19": ["placeholder",
            "placeholder"],
    "topic-01": ["Tell me about a goal you helped define.", "How did you assess the result?"],
    "topic-11": ["How did you choose what to prioritize?", "What would you do differently next time?"],
    "topic-03": ["Tell me about making a decision with incomplete information.", "How did you check your assumptions?"],
    "topic-04": ["Describe a change you helped make.", "What feedback did you receive?"],
    "topic-06": ["placeholder"],
    "topic-09": ["How did you explain a trade-off to a colleague?", "What changed after the conversation?"],
    "topic-10": ["placeholder"],
    "strategy-roadmap": ["Tell me about a roadmap you built and how you got buy-in."],
    "workshops": ["Describe an executive workshop you ran. What changed afterward?"],
    "executive-advisory": ["Tell me about advising a senior executive who disagreed with you."],
    "topic-17": ["placeholder"],
    "mentoring": ["How do you grow engineers and architects? Give an example."],
    "team-leadership": ["Tell me about leading a team through a difficult delivery."],
    "delivery-leadership": ["Tell me about a delivery that was at risk and how you recovered it."],
    "stakeholder-alignment": ["Tell me about aligning stakeholders who wanted different things."],
    "governance-compliance": ["How did you work with risk, legal and security without slowing delivery?"],
    "topic-20": ["What did you learn from a challenging assignment?"],
    "topic-13": ["placeholder"],
    "topic-05": ["How did you organize a project with competing deadlines?"],
    "topic-16": ["When did you ask for feedback about your work?"],
    "vendor-management": ["How do you manage vendors and hold them accountable?"],
    "topic-18": ["Tell me about improving a process with a colleague."],
}

touch_time = common.now


class Health(TypedDict):
    """Read-only summary of one story, for readiness.py, sessions.py and lead.py."""

    errors: list[str]
    warnings: list[str]
    linked: bool
    open_followups: int
    weak_facts: int
    spoken: list[str]
    metrics_unknown: int


# ---- storage -------------------------------------------------------------------------------------------------------

def load_story_data() -> dict[str, Any]:
    """The stored stories with every story normalized; fails when `init` has not run."""
    data = tables.load_stories()
    if data is None:
        raise ToolError(NO_STORIES)
    data["stories"] = [sm.normalize_story(s) for s in data["stories"]]
    return cast(dict[str, Any], data)


def load_eng_data() -> dict[str, Any]:
    """The stored engagements with every engagement normalized (empty before the first one)."""
    data = tables.load_engagements()
    data["engagements"] = [sm.normalize_engagement(e) for e in data["engagements"]]
    return cast(dict[str, Any], data)


def stories() -> list[Story]:
    """All stories."""
    return cast(list[Story], load_story_data()["stories"])


def engagements() -> list[Engagement]:
    """All engagements."""
    return cast(list[Engagement], load_eng_data()["engagements"])


def save_stories(data: dict[str, Any]) -> None:
    """Store the stories with the current schema version."""
    data["schema_version"] = sm.SCHEMA_VERSION
    tables.replace_stories(data)


def save_engs(data: dict[str, Any]) -> None:
    """Store the engagements with the current schema version."""
    data["schema_version"] = sm.SCHEMA_VERSION
    tables.replace_engagements(data)


def find[T: Mapping[str, object]](items: Iterable[T], ident: str, what: str) -> T:
    """The item whose id is `ident`."""
    for item in items:
        if item["id"] == ident:
            return item
    raise ToolError(f"No {what} {ident}")


def eng_of(story: Story, engs: Iterable[Engagement]) -> Engagement | None:
    """The engagement a story is linked to."""
    if not story["engagement"]:
        return None
    return next((e for e in engs if e["id"] == story["engagement"]), None)


def health(story: Story, engs: Iterable[Engagement] | None = None, style: str | None = None) -> Health:
    """Read-only summary of the v2 fields of one story, judged in the style in force."""
    eng = eng_of(story, engagements() if engs is None else engs)
    issues = sm.validate_story(story, eng, styles.in_force(style))
    facts = sm.fact_map(eng)
    return {"errors": [m for level, m in issues if level == "error"],
            "warnings": [m for level, m in issues if level == "warn"],
            "linked": bool(eng), "open_followups": len(story["follow_ups"]),
            "weak_facts": sum(1 for i in story["uses_facts"] if i in facts and facts[i]["basis"] not in sm.USABLE_BASES),
            "spoken": [k for k in sm.SPOKEN_LIMITS if story["spoken"].get(k)],
            "metrics_unknown": sum(1 for m in story["metrics"] if m.get("basis") in sm.HEDGED_METRIC_BASES)}


def split_list(value: str) -> list[str]:
    """'a | b' -> ['a', 'b']."""
    return [x.strip() for x in value.split(" | ") if x.strip()]


def split_ids(value: str | None) -> list[str]:
    """'f1, f2' -> ['f1', 'f2']."""
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def touch(item: Any) -> None:
    """Stamp the item as updated now."""
    item["updated"] = touch_time()


def ranked_scores(analysis: qr.Analysis) -> dict[str, float]:
    """{bullet id: score} for every bullet that matched a job description."""
    return {item.bullet["id"]: item.score for _, scored in analysis.ranked for item in scored}


def story_relevance(story: Story, ranked: Mapping[str, float], themes: Iterable[str]) -> float:
    """How well a story fits a JD: its best anchor bullet's score, plus a bonus for a matching theme."""
    best = max((ranked.get(i, 0) for i in story["anchor_bullets"]), default=0)
    return best + (THEME_BONUS if {story["theme"], *story["also_themes"]} & set(themes) else 0)


# ---- init (skeleton) -----------------------------------------------------------------------------------------------

def new_story(company: Company, theme: str, bullets: Sequence[Bullet]) -> Story:
    """A story for a theme of a company, anchored on its bullets."""
    best = max(bullets, key=lambda b: (len(b["sources"]), bool(b["metrics"])))
    return sm.normalize_story({
        "id": f"{company['id']}-{theme}", "company": company["id"], "company_name": company["name"],
        "theme": theme, "headline": best["text"],
        "metrics_on_resume": sorted({m for b in bullets for m in b["metrics"]}),
        "anchor_bullets": [b["id"] for b in bullets]})


def recent_cutoff() -> str:
    """Earliest start date (YYYY) that makes a company 'recent'."""
    return str(date.today().year - RECENT_YEARS)


def is_recent(company: Company, cutoff: str) -> bool:
    """Whether a role started since the cutoff, or is still current."""
    return newest_start(company) >= cutoff or any(r["end"] is None for r in company["roles"])


def bullets_by_theme(company: Company) -> dict[str, list[Bullet]]:
    """Live bullets (not ignored, not under review) grouped by theme, without umbrella themes."""
    by_theme: dict[str, list[Bullet]] = {}
    for bullet in company["bullets"]:
        if bullet.get("ignored") or bullet.get("needs_review"):
            continue
        for theme in bullet["themes"]:
            if theme not in UMBRELLA:
                by_theme.setdefault(theme, []).append(bullet)
    return by_theme


def themes_to_keep(by_theme: Mapping[str, list[Bullet]], recent: bool) -> list[tuple[str, list[Bullet]]]:
    """The themes that get a story: the best-supported ones, more of them for recent companies."""
    ranked = sorted(by_theme.items(), key=lambda kv: -len(kv[1]))
    keep = [(t, bs) for t, bs in ranked if len(bs) >= MIN_BULLETS] if recent else ranked
    return (keep or ranked)[:CAP_RECENT if recent else CAP_OLD]


def company_stories(company: Company, old: dict[str, Story], cutoff: str) -> tuple[list[Story], int]:
    """(stories for the company, number that are new). Existing answers are kept; `old` loses the ones reused."""
    out: list[Story] = []
    added = 0
    for theme, bullets in themes_to_keep(bullets_by_theme(company), is_recent(company, cutoff)):
        fresh = new_story(company, theme, bullets)
        previous = old.pop(fresh["id"], None)
        if previous is None:
            added += 1
            out.append(fresh)
            continue
        previous["anchor_bullets"] = fresh["anchor_bullets"]
        previous["headline"] = fresh["headline"]
        previous["metrics_on_resume"] = fresh["metrics_on_resume"]
        out.append(sm.normalize_story(previous))       # keep answers; refresh anchors and headline
    return out, added


def cmd_init(args: argparse.Namespace) -> None:
    """Create or extend the stories and themes from the resume data."""
    companies, _ = qr.load()
    old = {s["id"]: s for s in (tables.load_stories() or {"stories": []})["stories"]}
    out: list[Story] = []
    added = 0
    cutoff = recent_cutoff()
    for company in qr.newest_first(companies):
        stories_here, new = company_stories(company, old, cutoff)
        out += stories_here
        added += new
    out += [sm.normalize_story(s) for s in old.values()]     # no longer produced but possibly filled in: keep
    save_stories({"stories": out})
    themes: dict[str, dict[str, Any]] = {}
    for story in out:
        themes.setdefault(story["theme"], {"stories": [], "questions": QUESTIONS.get(story["theme"], [])})["stories"].append(story["id"])
    tables.replace_themes(dict(sorted(themes.items())))
    print(f"{len(out)} stories ({added} new); {len(themes)} themes")


# ---- stories: read -------------------------------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    """Stories per company by status, plus engagement and fact counts."""
    by_company: dict[str, list[str]] = {}
    for story in stories():
        by_company.setdefault(story["company_name"], []).append(story["status"])
    for company, statuses in by_company.items():
        print(f"  {company:<30} {statuses.count('done')} done, {statuses.count('draft')} draft, "
              f"{statuses.count('empty')} empty")
    engs = engagements()
    if engs:
        unsure = sum(1 for e in engs for f in e["facts"] if f["basis"] == "unsure")
        print(f"  engagements: {len(engs)}, facts: {sum(len(e['facts']) for e in engs)} ({unsure} unsure)")


def cmd_list(args: argparse.Namespace) -> None:
    """Every story with its status and headline."""
    for story in stories():
        if not args.company or args.company == story["company"]:
            print(f"  {story['id']:<40} {story['status']:<6} {story['headline'][:70]}")


def _style_lines(story: Story, style: str) -> list[str]:
    """The text of the story grouped as the parts of `style`, then the stored fields no part reads."""
    fields: Mapping[str, Any] = story
    chosen = styles.get(style)
    lines = [f"  {part.name}: {styles.part_text(part, story) or '-'}" for part in chosen.parts]
    covered = styles.stored_fields(style)
    return lines + [f"  {name}: {fields[name] or '-'}" for name in FIELDS if name not in covered]


def show(story: Story, eng: Engagement | None = None, style: str | None = None) -> None:
    """Print one story with its numbers, spoken versions and facts, grouped as the style in force."""
    story = sm.normalize_story(story)
    fields: Mapping[str, Any] = story
    chosen = styles.in_force(style)
    print(f"[{story['id']}] {story['company_name']} | {story['theme']} | status: {story['status']}")
    print(f"  resume line: {story['headline']}")
    if story["metrics_on_resume"]:
        print("  metrics on resume: " + ", ".join(story["metrics_on_resume"]))
    if story["engagement"]:
        print(f"  engagement: {story['engagement']}" + (f" ({eng['title']})" if eng and eng.get("title") else ""))
    print(f"  style: {chosen}")
    print("\n".join(_style_lines(story, chosen)))
    if story["metrics"]:
        print("  numbers: " + "; ".join(f"{m['name']} = {m['value']} ({m['basis']})" for m in story["metrics"]))
    for key in sm.SPOKEN_LIMITS:
        if story["spoken"].get(key):
            print(f"  spoken {key}: {story['spoken'][key]}")
    if any(story["spoken"].get(key) for key in sm.SPOKEN_LIMITS):
        print(f"  (spoken versions are shown as written; they are not rearranged to {chosen})")
    for name in ("likely_questions", "never_say", "also_themes"):
        if fields[name]:
            print(f"  {name}: " + " | ".join(fields[name]))
    if eng and story["uses_facts"]:
        facts = sm.fact_map(eng)
        print("  relies on facts: " + "; ".join(f"{i} [{facts[i]['basis']}] {facts[i]['text']}"
                                                 for i in story["uses_facts"] if i in facts))
    print("  follow_ups: " + (" | ".join(story["follow_ups"]) or "-"))
    if story["resolved"]:
        print("  resolved: " + " | ".join(f"{r['q']} -> {r['answer']}" for r in story["resolved"]))


def cmd_styles(args: argparse.Namespace) -> None:
    """The three answer styles."""
    del args
    print("\n".join(styles.listing()))
    print(f"In force: {styles.in_force()} (--style, then the profile's answer_style, then star).")


def cmd_next(args: argparse.Namespace) -> None:
    """Show the next story that is not done."""
    engs = engagements()
    for story in stories():
        if story["status"] != "done" and (not args.company or args.company == story["company"]):
            show(story, eng_of(story, engs))
            return
    print("Nothing left to fill" + (f" for {args.company}" if args.company else "") + ".")


def cmd_show(args: argparse.Namespace) -> None:
    """Show one story."""
    story = find(stories(), args.id, "story")
    show(story, eng_of(story, engagements()), args.style)


# ---- stories: write ------------------------------------------------------------------------------------------------

def set_status_done(story: dict[str, Any], previous: str, style: str) -> None:
    """Refuse to mark a story done while it has rule errors in the style in force (the status is restored first)."""
    errors = [m for level, m in sm.validate_story(cast(Story, story), eng_of(cast(Story, story), engagements()),
                                                  style, marking=True) if level == "error"]
    if errors:
        story["status"] = previous           # nothing was saved yet; the file is untouched
        raise ToolError("Cannot mark done:\n  " + "\n  ".join(errors))


def _is_part_name(field: str) -> bool:
    """Whether `field` is the name of a part in any style."""
    return any(part.name == field for style in styles.STYLES.values() for part in style.parts)


def _set_text(story: dict[str, Any], field: str, value: str, style: str) -> str:
    """Set one text field or style part; return the message for the user."""
    if field == "status":
        if value not in sm.STATUSES:
            raise ToolError("status must be empty, draft or done")
        previous = story["status"]
        story["status"] = value
        if value == "done":
            set_status_done(story, previous, style)
    else:
        story[field] = value
    return f"Updated {story['id']}.{field}"


def apply_field(story: dict[str, Any], field: str, value: str, style: str | None = None, merge: bool = False) -> str:
    """Set one field of a story from the command line; return the message for the user.

    A part name of a style (obstacle, challenge, learning, or any part when `--style` is given) is saved to the
    stored field it maps to. The stored field names keep working as before when no style is given.
    """
    if field in sm.LIST_FIELDS:
        story[field] = split_list(value)
    elif field.startswith("spoken."):
        key = field.split(".", 1)[1]
        if key not in sm.SPOKEN_LIMITS:
            raise ToolError("spoken field must be spoken.60s or spoken.2min")
        story["spoken"][key] = value
    elif _is_part_name(field) and (style is not None or field not in sm.STAR):
        return f"Updated {story['id']}: " + styles.save_part(story, styles.in_force(style), field, value, merge)
    elif field in FIELDS or field == "status":
        return _set_text(story, field, value, styles.in_force(style))
    else:
        raise ToolError(f"Unknown field {field}")
    return f"Updated {story['id']}.{field}"


def cmd_set(args: argparse.Namespace) -> None:
    """Set a story field (STAR text, spoken versions, lists, status) or a part of the style in force."""
    data = load_story_data()
    story = find(data["stories"], args.id, "story")
    message = apply_field(story, args.field, args.value, args.style, args.merge)
    if args.field != "status" and story["status"] == "empty":
        story["status"] = "draft"
    touch(story)
    save_stories(data)
    print(message)
    for level, text in sm.validate_story(story, eng_of(story, engagements()), styles.in_force(args.style)):
        if level == "error" and story["status"] != "done" and (
                "never_say" in text or "basis" in text or "does not exist" in text):
            print("  Note:", text)


def cmd_new(args: argparse.Namespace) -> None:
    """Add an extra story beyond the generated ones."""
    data = load_story_data()
    if any(x["id"] == args.id for x in data["stories"]):
        raise ToolError(f"Story {args.id} already exists")
    companies, _ = qr.load()
    company = companies.get(args.company)
    if not company:
        raise ToolError(f"Unknown company {args.company}. Known: " + ", ".join(sorted(companies)))
    if args.engagement:
        find(engagements(), args.engagement, "engagement")
    story = sm.normalize_story({"id": args.id, "company": company["id"], "company_name": company["name"],
                                "theme": args.theme, "headline": args.headline or args.theme,
                                "engagement": args.engagement})
    touch(story)
    data["stories"].append(story)
    save_stories(data)
    print(f"Created story {args.id} ({company['name']} / {args.theme})")


def cmd_link(args: argparse.Namespace) -> None:
    """Attach an engagement to a story, and the facts the story relies on."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    eng = find(engagements(), args.engagement, "engagement")
    if story["engagement"] and story["engagement"] != eng["id"] and story["uses_facts"]:
        raise ToolError(f"{story['id']} already relies on facts of {story['engagement']}: "
                        f"run `unlink {story['id']}` first")
    story["engagement"] = eng["id"]
    facts = sm.fact_map(eng)
    for fid in split_ids(args.facts):
        if fid not in facts:
            raise ToolError(f"No fact {fid} in {eng['id']}")
        if fid not in story["uses_facts"]:
            story["uses_facts"].append(fid)
    touch(story)
    save_stories(data)
    print(f"Linked {story['id']} -> {eng['id']}; facts: {', '.join(story['uses_facts']) or '-'}")
    for level, message in sm.validate_story(story, eng, styles.in_force()):
        if level == "error":
            print("  Note:", message)


def cmd_unlink(args: argparse.Namespace) -> None:
    """Detach some facts from a story, or the whole engagement when no facts are named."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    drop = split_ids(args.facts)
    if drop:
        story["uses_facts"] = [f for f in story["uses_facts"] if f not in drop]
    else:
        story["engagement"], story["uses_facts"] = None, []
    touch(story)
    save_stories(data)
    print(f"Updated {story['id']}: engagement {story['engagement'] or '-'}, "
          f"facts {', '.join(story['uses_facts']) or '-'}")


def save_metrics(data: dict[str, Any], story: Story) -> None:
    """Save after a metric change and print the story's numbers."""
    touch(story)
    save_stories(data)
    numbers = "; ".join(f"{m['name']} = {m['value']} ({m['basis']})" for m in story["metrics"])
    print(f"Updated {story['id']} numbers: " + (numbers or "-"))


def cmd_metric_add(args: argparse.Namespace) -> None:
    """Add (or replace) a number on a story; it needs a name, value and basis."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    if not args.name or args.value is None or not args.basis:
        raise ToolError("metric add needs --name, --value and --basis")
    story["metrics"] = [m for m in story["metrics"] if m["name"] != args.name]
    story["metrics"].append({"name": args.name, "value": args.value, "basis": args.basis,
                             **({"note": args.note} if args.note else {})})
    save_metrics(data, story)


def cmd_metric_rm(args: argparse.Namespace) -> None:
    """Remove a number from a story."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    before = len(story["metrics"])
    story["metrics"] = [m for m in story["metrics"] if m["name"] != args.name]
    if len(story["metrics"]) == before:
        raise ToolError(f"No metric named {args.name}")
    save_metrics(data, story)


def save_followups(data: dict[str, Any], story: Story) -> None:
    """Save after a follow-up change and report the counts."""
    touch(story)
    save_stories(data)
    print(f"{story['id']}: {len(story['follow_ups'])} open, {len(story['resolved'])} resolved")


def cmd_followup_add(args: argparse.Namespace) -> None:
    """Add an open follow-up question to a story."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    story["follow_ups"].append(args.text)
    save_followups(data, story)


def follow_up_index(follow_ups: Sequence[str], ref: str) -> int:
    """Position of the follow-up named by 1-based number or by a fragment of its text (-1 when none)."""
    if ref.isdigit():
        return int(ref) - 1
    return next((i for i, q in enumerate(follow_ups) if ref.lower() in q.lower()), -1)


def cmd_followup_resolve(args: argparse.Namespace) -> None:
    """Resolve a follow-up with the user's own answer."""
    data = load_story_data()
    story = find(data["stories"], args.story, "story")
    if not args.answer:
        raise ToolError("followup resolve needs --answer (the user's own words)")
    index = follow_up_index(story["follow_ups"], args.text)
    if not 0 <= index < len(story["follow_ups"]):
        raise ToolError("No such follow-up. Open: " + " | ".join(f"{i + 1}. {q}" for i, q in enumerate(story["follow_ups"])))
    question = story["follow_ups"].pop(index)
    story["resolved"].append({"q": question, "answer": args.answer, "at": touch_time()})
    save_followups(data, story)


# ---- engagements ---------------------------------------------------------------------------------------------------

def show_eng(eng: Engagement) -> None:
    """Print an engagement with its facts, decisions, people and the stories that use it."""
    fields: Mapping[str, Any] = eng
    print(f"[{eng['id']}] {eng.get('company') or '-'} | {eng.get('title') or '-'}")
    for name in ("my_role", "period", "summary", "notes"):
        print(f"  {name}: {fields.get(name) or '-'}")
    print(f"  facts ({len(eng['facts'])}):")
    for fact in eng["facts"]:
        print(f"    {fact['id']} [{fact['basis']}] {fact['text']}" + (f"  <{fact['source']}>" if "source" in fact else "")
              + (f"  ({fact['note']})" if "note" in fact else ""))
    print(f"  decisions ({len(eng['decisions'])}):")
    for dec in eng["decisions"]:
        alternatives = ", ".join(dec.get("alternatives") or [])
        print(f"    {dec['id']} [{dec.get('ownership', '?')}] {dec['what']}" + (f" | why: {dec['why']}" if "why" in dec else "")
              + (f" | alternatives: {alternatives}" if alternatives else "")
              + (f" | trade-offs: {dec['tradeoffs']}" if "tradeoffs" in dec else ""))
    if eng["people"]:
        print("  people: " + "; ".join(p["role"] + (f" ({p['note']})" if p.get("note") else "") for p in eng["people"]))
    used = [s["id"] for s in stories() if s["engagement"] == eng["id"]] if tables.has_stories() else []
    print("  stories: " + (", ".join(used) or "-"))


def cmd_engagement_list(args: argparse.Namespace) -> None:
    """List engagements."""
    engs = engagements()
    for eng in engs:
        print(f"  {eng['id']:<32} {eng.get('company') or '-':<12} {len(eng['facts'])} facts, "
              f"{len(eng['decisions'])} decisions | {eng.get('title') or '-'}")
    if not engs:
        print("  (none yet)")


def cmd_engagement_show(args: argparse.Namespace) -> None:
    """Show one engagement."""
    show_eng(find(engagements(), args.id, "engagement"))


def cmd_engagement_add(args: argparse.Namespace) -> None:
    """Create an engagement."""
    data = load_eng_data()
    if any(e["id"] == args.id for e in data["engagements"]):
        raise ToolError(f"Engagement {args.id} already exists")
    eng = sm.normalize_engagement({"id": args.id, "company": args.company, "title": args.title,
                                   "my_role": args.role, "period": args.period, "summary": args.summary})
    touch(eng)
    data["engagements"].append(eng)
    save_engs(data)
    print(f"Created engagement {args.id}")


def cmd_engagement_set(args: argparse.Namespace) -> None:
    """Set a text field of an engagement."""
    data = load_eng_data()
    eng = find(data["engagements"], args.id, "engagement")
    if args.field not in sm.ENG_TEXT_FIELDS:
        raise ToolError("field must be one of " + ", ".join(sm.ENG_TEXT_FIELDS))
    cast(dict[str, Any], eng)[args.field] = args.value
    touch(eng)
    save_engs(data)
    print(f"Updated {args.id}.{args.field}")


def finish_eng(data: dict[str, Any], eng: Engagement, message: str) -> None:
    """Stamp and save an engagement, then print the message."""
    touch(eng)
    save_engs(data)
    print(message)


def check_fact_or_fail(fact: sm.Fact) -> None:
    """Fail with the fact's problems, if any."""
    problems = sm.check_fact(fact)
    if problems:
        raise ToolError("; ".join(problems))


def cmd_fact_add(args: argparse.Namespace) -> None:
    """Add a fact (with how we know it) to an engagement."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    fact: sm.Fact = {"id": sm.next_id(eng, "facts", "f"), "text": args.text, "basis": args.basis,
                     "added": touch_time()[:10]}
    if args.source:
        fact["source"] = args.source
    if args.note:
        fact["note"] = args.note
    check_fact_or_fail(fact)
    eng["facts"].append(fact)
    finish_eng(data, eng, f"Added {eng['id']}.{fact['id']} [{fact['basis']}]")


def cmd_fact_set(args: argparse.Namespace) -> None:
    """Change a fact's text, basis, source or note."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    fact = cast(dict[str, Any], find(eng["facts"], args.fact_id, "fact"))
    for key in ("text", "basis", "source", "note"):
        if getattr(args, key) is not None:
            fact[key] = getattr(args, key)
    check_fact_or_fail(cast(sm.Fact, fact))
    finish_eng(data, eng, f"Updated {eng['id']}.{fact['id']} [{fact['basis']}]")


def cmd_fact_rm(args: argparse.Namespace) -> None:
    """Remove a fact that no story relies on."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    find(eng["facts"], args.fact_id, "fact")
    users = [s["id"] for s in stories() if s["engagement"] == eng["id"] and args.fact_id in s["uses_facts"]]
    if users:
        raise ToolError(f"Fact {args.fact_id} is used by {', '.join(users)}: unlink it first")
    eng["facts"] = [f for f in eng["facts"] if f["id"] != args.fact_id]
    finish_eng(data, eng, f"Removed {eng['id']}.{args.fact_id}")


def cmd_decision_add(args: argparse.Namespace) -> None:
    """Record a decision, its alternatives and who owned it."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    decision: sm.Decision = {"id": sm.next_id(eng, "decisions", "d"), "what": args.what, "why": args.why,
                             "alternatives": split_list(args.alternatives or ""), "tradeoffs": args.tradeoffs,
                             "ownership": args.ownership}
    eng["decisions"].append(decision)
    finish_eng(data, eng, f"Added {eng['id']}.{decision['id']} [{decision['ownership']}]")


def cmd_decision_rm(args: argparse.Namespace) -> None:
    """Remove a decision."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    find(eng["decisions"], args.decision_id, "decision")
    eng["decisions"] = [d for d in eng["decisions"] if d["id"] != args.decision_id]
    finish_eng(data, eng, f"Removed {eng['id']}.{args.decision_id}")


def cmd_person_add(args: argparse.Namespace) -> None:
    """Record a person involved in an engagement."""
    data = load_eng_data()
    eng = find(data["engagements"], args.eng, "engagement")
    eng["people"].append({"role": args.role, **({"note": args.note} if args.note else {})})
    finish_eng(data, eng, f"{eng['id']}: {len(eng['people'])} people recorded")


# ---- search, validate, export, evidence -------------------------------------------------------------------

def stories_if_any() -> list[Story]:
    """All stories, or none before `init`."""
    return stories() if tables.has_stories() else []


def cmd_search(args: argparse.Namespace) -> None:
    """Search stories and engagements for a text."""
    hits = sm.search(stories_if_any(), engagements(), args.text)
    for kind, ident, field, snippet in hits:
        print(f"  {kind} {ident} | {field}: {snippet}")
    print(f"{len(hits)} match(es)")


def cmd_validate(args: argparse.Namespace) -> int:
    """Check stories and engagements against the rules; status 1 when there are errors."""
    ss, es = stories_if_any(), engagements()
    emap = {e["id"]: e for e in es}
    style = styles.in_force(args.style)
    problems: list[sm.Issue] = []
    for eng in es:
        if not args.id or args.id == eng["id"]:
            problems += sm.validate_engagement(eng)
    for story in ss:
        if not args.id or args.id == story["id"] or args.id == story["engagement"]:
            problems += sm.validate_story(story, emap.get(story["engagement"] or ""), style)
    if args.id and not any(x["id"] == args.id for x in [*ss, *es]):
        raise ToolError(f"No story or engagement {args.id}")
    errors = [m for level, m in problems if level == "error"]
    for level, message in problems:
        print(f"  {level.upper():<5} {message}")
    print(f"{len(errors)} error(s), {len(problems) - len(errors)} warning(s)")
    return 1 if errors else 0


def dump_json(stories_: Sequence[Story], engs: Sequence[Engagement]) -> str:
    """The export document as JSON text."""
    return json.dumps({"schema_version": sm.SCHEMA_VERSION, "stories": stories_, "engagements": engs},
                      indent=2, ensure_ascii=False) + "\n"


def export_text(args: argparse.Namespace) -> str:
    """The text to export for the chosen story/engagement/format."""
    ss, es = stories_if_any(), engagements()
    if args.story:
        story = find(ss, args.story, "story")
        eng = eng_of(story, es)
        if args.format == "md":
            return sm.render_story_md(story, eng, styles.in_force(args.style))
        return dump_json([story], [eng] if eng else [])
    if args.format == "md":
        raise ToolError("--format md needs --story")
    if args.engagement:
        es = [find(es, args.engagement, "engagement")]
        ss = [s for s in ss if s["engagement"] == args.engagement]
    return dump_json(ss, es)


def cmd_export(args: argparse.Namespace) -> None:
    """Print or write a story (markdown or JSON) or the whole store (JSON)."""
    text = export_text(args)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


def cmd_evidence(args: argparse.Namespace) -> None:
    """The dates a story was practised in sessions."""
    find(stories(), args.story, "story")
    from jk.interview import readiness  # pylint: disable=import-outside-toplevel,cyclic-import  # imported here: readiness imports this module
    evidence = readiness.attempts().get(args.story)
    if not evidence or not evidence["answered"]:
        print(f"{args.story}: no practice answer logged yet (lessons alone do not count).")
        return
    print(f"{args.story}: answered on {', '.join(sorted(evidence['answered']))}; "
          f"graded solid on {', '.join(sorted(evidence['graded2'])) or 'no day'}")


# ---- for-jd --------------------------------------------------------------------------------------------------------

def cmd_for_jd(args: argparse.Namespace) -> None:
    """Rank stories for a job description and list the ones to finish."""
    analysis = qr.analyze(common.read_text_arg(args.jd))
    ranked = ranked_scores(analysis)
    themes = tables.load_themes()
    rows = [(score, s) for s in stories() if (score := story_relevance(s, ranked, analysis.themes))]
    top = sorted(rows, key=lambda row: -row[0])[:args.top]
    for score, story in top:
        print(f"{story['id']}  ({story['company_name']}, {story['status']}, score {score:.0f})\n  {story['headline']}")
        for question in (story["likely_questions"] or themes.get(story["theme"], {}).get("questions", []))[:2]:
            print(f"  Q: {question}")
    unfilled = [s["id"] for _, s in top if s["status"] != "done"]
    print("\nStories to finish before this interview: " + (", ".join(unfilled) or "none"))


# ---- CLI -----------------------------------------------------------------------------------------------------------

def _actions(sub: Any, name: str) -> Any:
    """Subparser group for `name`, whose actions are separate subcommands."""
    return sub.add_parser(name).add_subparsers(dest="action", required=True)


def _style_option(parser: argparse.ArgumentParser) -> None:
    """The `--style` option: star, soar or carl (default: the profile's answer_style, then star)."""
    parser.add_argument("--style", help="answer style: " + ", ".join(styles.names()) + " (default: the profile's, then star)")


def _add_story_parsers(sub: Any) -> None:
    sub.add_parser("init", aliases=["skeleton"]).set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    listing = sub.add_parser("list")
    listing.add_argument("--company")
    listing.set_defaults(fn=cmd_list)
    nxt = sub.add_parser("next")
    nxt.add_argument("--company")
    nxt.set_defaults(fn=cmd_next)
    shower = sub.add_parser("show")
    shower.add_argument("id")
    _style_option(shower)
    shower.set_defaults(fn=cmd_show)
    setter = sub.add_parser("set")
    for name in ("id", "field", "value"):
        setter.add_argument(name)
    _style_option(setter)
    setter.add_argument("--merge", action="store_true",
                        help="save a challenge over a task: the new text becomes the situation and the task is emptied")
    setter.set_defaults(fn=cmd_set)
    sub.add_parser("styles").set_defaults(fn=cmd_styles)
    for_jd = sub.add_parser("for-jd")
    for_jd.add_argument("jd", help="job description file, or - for stdin")
    for_jd.add_argument("--top", type=int, default=8)
    for_jd.set_defaults(fn=cmd_for_jd)
    new = sub.add_parser("new")
    new.add_argument("id")
    new.add_argument("--company", required=True)
    new.add_argument("--theme", required=True)
    new.add_argument("--headline")
    new.add_argument("--engagement")
    new.set_defaults(fn=cmd_new)
    link = sub.add_parser("link")
    link.add_argument("story")
    link.add_argument("engagement")
    link.add_argument("--facts")
    link.set_defaults(fn=cmd_link)
    unlink = sub.add_parser("unlink")
    unlink.add_argument("story")
    unlink.add_argument("--facts")
    unlink.set_defaults(fn=cmd_unlink)


def _add_engagement_parsers(sub: Any) -> None:
    eng = _actions(sub, "engagement")
    add = eng.add_parser("add")
    add.add_argument("id")
    add.add_argument("--company", required=True)
    add.add_argument("--title", required=True)
    for flag in ("--role", "--period", "--summary"):
        add.add_argument(flag)
    add.set_defaults(fn=cmd_engagement_add)
    eng.add_parser("list").set_defaults(fn=cmd_engagement_list)
    show_p = eng.add_parser("show")
    show_p.add_argument("id")
    show_p.set_defaults(fn=cmd_engagement_show)
    set_p = eng.add_parser("set")
    for name in ("id", "field", "value"):
        set_p.add_argument(name)
    set_p.set_defaults(fn=cmd_engagement_set)


def _add_fact_parsers(sub: Any) -> None:
    fact = _actions(sub, "fact")
    add_f = fact.add_parser("add")
    add_f.add_argument("eng")
    add_f.add_argument("text")
    add_f.add_argument("--basis", required=True, choices=sm.FACT_BASES)
    add_f.set_defaults(fn=cmd_fact_add)
    set_f = fact.add_parser("set")
    set_f.add_argument("eng")
    set_f.add_argument("fact_id")
    set_f.add_argument("--text")
    set_f.add_argument("--basis", choices=sm.FACT_BASES)
    set_f.set_defaults(fn=cmd_fact_set)
    for parser in (add_f, set_f):
        parser.add_argument("--source")
        parser.add_argument("--note")
    rm_f = fact.add_parser("rm")
    rm_f.add_argument("eng")
    rm_f.add_argument("fact_id")
    rm_f.set_defaults(fn=cmd_fact_rm)


def _add_decision_parsers(sub: Any) -> None:
    decision = _actions(sub, "decision")
    add_d = decision.add_parser("add")
    add_d.add_argument("eng")
    add_d.add_argument("--what", required=True)
    for flag in ("--why", "--alternatives", "--tradeoffs"):
        add_d.add_argument(flag)
    add_d.add_argument("--ownership", choices=sm.OWNERSHIP, default="unsure")
    add_d.set_defaults(fn=cmd_decision_add)
    rm_d = decision.add_parser("rm")
    rm_d.add_argument("eng")
    rm_d.add_argument("decision_id")
    rm_d.set_defaults(fn=cmd_decision_rm)

    person = _actions(sub, "person").add_parser("add")
    person.add_argument("eng")
    person.add_argument("--role", required=True)
    person.add_argument("--note")
    person.set_defaults(fn=cmd_person_add)


def _add_note_parsers(sub: Any) -> None:
    metric = _actions(sub, "metric")
    add_m = metric.add_parser("add")
    add_m.add_argument("story")
    for flag in ("--name", "--value", "--note"):
        add_m.add_argument(flag)
    add_m.add_argument("--basis", choices=sm.METRIC_BASES)
    add_m.set_defaults(fn=cmd_metric_add)
    rm_m = metric.add_parser("rm")
    rm_m.add_argument("story")
    rm_m.add_argument("name")
    rm_m.set_defaults(fn=cmd_metric_rm)

    followup = _actions(sub, "followup")
    add_u = followup.add_parser("add")
    add_u.add_argument("story")
    add_u.add_argument("text")
    add_u.set_defaults(fn=cmd_followup_add)
    resolve = followup.add_parser("resolve")
    resolve.add_argument("story")
    resolve.add_argument("text")
    resolve.add_argument("--answer")
    resolve.set_defaults(fn=cmd_followup_resolve)


def _add_read_parsers(sub: Any) -> None:
    search = sub.add_parser("search")
    search.add_argument("text")
    search.set_defaults(fn=cmd_search)
    validate = sub.add_parser("validate")
    validate.add_argument("id", nargs="?")
    _style_option(validate)
    validate.set_defaults(fn=cmd_validate)
    export = sub.add_parser("export")
    export.add_argument("--story")
    export.add_argument("--engagement")
    export.add_argument("--format", choices=["json", "md"], default="json")
    _style_option(export)
    export.add_argument("-o", "--output")
    export.set_defaults(fn=cmd_export)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("story")
    evidence.set_defaults(fn=cmd_evidence)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for add in (_add_story_parsers, _add_engagement_parsers, _add_fact_parsers, _add_decision_parsers,
                _add_note_parsers, _add_read_parsers):
        add(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
