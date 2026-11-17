#!/usr/bin/env python3
"""Build the resume experience data (stored in the database) from every resume (pdf, docx, md, txt) under the resume folders.

  process-resumes --survey   # read-only: show what each resume parses into, write nothing
  process-resumes            # parse new/changed resumes and merge into the resume data
  process-resumes --force    # ignore the ledger and re-process everything
  process-resumes curate list|add|rm KIND ...   # your curation (certifications, skill rules, bullet themes ...)

Read-only on the resume folders; writes only to the database (and the output/ folder under the home folder for raw text). The resume folders and the employer list come from the profile (see user/profile.py).
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Final, Literal, cast

from jk import common, store
from jk.resumes import curate, extract, tables, visual, visual_compare
from jk.resumes import parse_resume as pr
from jk.resumes import resume_data as rd
from jk.resumes.resume_data import ResumeData
from jk.user import profile as up

TEXT_DIR: Path = rd.TEXT_DIR
NEW_VARIANT_RATIO: Final[float] = pr.SIMILAR_THRESHOLD
Outcome = Literal["unchanged", "other", "parsed"]


@dataclass(frozen=True)
class Config:
    """Where the resumes are: the root folder (names in the ledger are relative to it) and the folders to scan."""

    root: Path
    dirs: list[Path]


def load_config() -> Config:
    """Read the profile (fails with the setup instruction when missing) and install the employer registry."""
    config = Config(up.resume_root(), up.resume_dirs())
    pr.set_companies(up.company_registry())
    return config


def transcript_name(key: str) -> str:
    """File name of the visual transcript of a ledger key: a readable start plus a checksum of the whole key, so two
    different paths never share a transcript (`a/b.pdf` and `a__b.pdf` both read as `a__b` otherwise)."""
    return f"{text_name(key).removesuffix('.txt')}-{sha256(key.encode('utf-8')).hexdigest()[:10]}.txt"


def transcript_for(path: Path, root: Path) -> Path:
    """Where the visual transcript of a resume file is kept (see visual.py)."""
    return visual.VISUAL_DIR / transcript_name(rel(path, root))


def scan_companies(files: Iterable[Path], root: Path, save: bool) -> None:
    """First-run scan: find the employers in every resume so nothing has to be typed in. With `save`, new
    employers are stored in the database (existing entries are never changed)."""
    found: dict[str, str] = {}
    for path in files:
        try:
            doc = visual.read_document(path, transcript_for(path, root))
        except common.ToolError:
            continue                        # reported later, per file, by survey or build
        discovered = pr.discover_companies(doc.layout_text or doc.text) or pr.discover_companies(doc.text)
        found.update({k: v for k, v in discovered.items() if k not in found})
    new = [k for k in found if k not in pr.COMPANIES]
    if not new:
        return
    print("Employers found in your resumes: " + ", ".join(found[k] for k in new))
    if save:
        up.add_companies({k: found[k] for k in new})
        print("  Saved the employers. If one employer appears twice, use `profile companies merge FROM INTO` or `rename ID NAME`.")
    else:
        print("  (survey: not saved)")
    pr.set_companies({**pr.COMPANIES, **{k: (found[k], re.escape(found[k]) + rf"(?:{pr.SEP}(?P<t>.+))?")
                                         for k in new}})


def list_resumes(dirs: Iterable[Path]) -> list[Path]:
    """All resume files (any supported format, no Word lock files) under the given dirs, newest first."""
    files = [p for d in dirs for p in d.rglob("*") if p.is_file() and extract.is_resume_file(p)]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def rel(path: Path, root: Path) -> str:
    """The file's path relative to the resume root, with forward slashes on every platform (its key in the ledger)."""
    return path.relative_to(root).as_posix()


def file_sha(path: Path) -> str:
    """SHA-256 of the file contents."""
    return sha256(path.read_bytes()).hexdigest()


def text_name(key: str) -> str:
    """File name for the raw extracted text of a ledger key (`a/b c.pdf` -> `a__b_c.txt`; other formats keep their
    suffix, `a/b.docx` -> `a__b.docx.txt`, so two formats of one resume never collide). The name never holds a
    path separator or a colon, which Windows does not allow in a file name."""
    return re.sub(r"[/\\:]", "__", key).replace(" ", "_").removesuffix(".pdf") + ".txt"


def now() -> str:
    """Timestamp for the ledger."""
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- survey

def survey(files: Iterable[Path], root: Path) -> None:
    """Print what each resume parses into, writing nothing."""
    for path in sorted(files, key=lambda p: rel(p, root)):
        try:
            doc = visual.read_document(path, transcript_for(path, root))
        except common.ToolError as error:
            print(f"{rel(path, root)}\n  {'NEEDS VISUAL READING' if isinstance(error, extract.NeedsVisualRead) else 'UNREADABLE'}: {common.hide_home(str(error))}")
            continue
        parsed = pr.parse_resume(doc.text, doc.layout_text)
        if parsed["is_resume"] is False:
            print(f"{rel(path, root)}\n  NOT A RESUME: {parsed['problems']}")
            continue
        bullets = sum(len(e["bullets"]) for e in parsed["work"])
        print(f"{rel(path, root)}\n  employers={len(parsed['work'])} bullets={bullets} "
              f"skill_groups={sorted(parsed['skills'])} certs={len(parsed['certifications'])} "
              f"edu={len(parsed['education'])} profile_points={len(parsed['profile_points'])}")
        for e in parsed["work"]:
            print(f"    {e['company_id']:<14} {e['start']}..{e['end']}  {e['title']!r} "
                  f"role={e['subtitle']!r} client={e['client']!r} bullets={len(e['bullets'])}")
        if doc.column_pages:
            print(f"  columns: read page{'s' if len(doc.column_pages) > 1 else ''} "
                  f"{', '.join(map(str, doc.column_pages))} as columns")
        for problem in parsed["problems"]:
            print(f"  PROBLEM: {problem}")


# ---------------------------------------------------------------- merge

def add_unique(items: list[str], value: str) -> None:
    """Append value when it is not empty and not already there."""
    if value and value not in items:
        items.append(value)


ROLE_FIELDS: Final = (("titles", "title"), ("subtitles", "subtitle"), ("clients", "client"))


def find_role(roles: list[dict[str, Any]], start: str | None, end: str | None) -> dict[str, Any] | None:
    """The stored role an entry belongs to: the same start and end, else the same start where one side is still
    open (a resume that says Present and one that gives the end date describe one job)."""
    same = [r for r in roles if r["start"] == start]
    exact = next((r for r in same if r["end"] == end), None)
    if exact or start is None:
        return exact
    if end is None:
        return max(same, key=lambda r: r["end"] or "", default=None)
    return next((r for r in same if r["end"] is None), None)


def latest_end(ends: Mapping[str, str | None]) -> str | None:
    """The role's end: the latest real end date any resume gives; None (current) only when none gives one."""
    return max((e for e in ends.values() if e), default=None)


def merge_role(company: dict[str, Any], entry: pr.WorkEntry, source: str) -> None:
    """One role per job (see find_role); titles/subtitles/clients seen in tailored resumes are kept as variants,
    each with the files that state it, and so is the end date each file gives."""
    role = find_role(company["roles"], entry["start"], entry["end"])
    if role is None:
        role = {"start": entry["start"], "end": entry["end"], "titles": [], "subtitles": [], "clients": [],
                "sources": [], "ends": {}, "field_sources": {}}
        company["roles"].append(role)
    role["ends"][source] = entry["end"]
    role["end"] = latest_end(role["ends"])
    for field, key in ROLE_FIELDS:
        add_unique(role[field], entry[key])
        if entry[key]:
            by_value = role["field_sources"].setdefault(field, {})
            add_unique(by_value.setdefault(entry[key], []), source)
    add_unique(role["sources"], source)


def strip_role(role: dict[str, Any], key: str) -> bool:
    """Take resume file `key` out of a role: its end date and the titles only it stated. False when no file is left."""
    if key not in role["sources"]:
        return True
    role["sources"].remove(key)
    if "ends" in role:
        role["ends"].pop(key, None)
        role["end"] = latest_end(role["ends"])
    for field, by_value in role.get("field_sources", {}).items():
        for value, files in list(by_value.items()):
            if key in files:
                files.remove(key)
            if not files:
                del by_value[value]
                role[field].remove(value)
    return bool(role["sources"])


NUMBER_RE: Final = re.compile(r"\d+(?:[.,]\d+)*")


def same_figures(a: str, b: str) -> bool:
    """Whether two lines state the same numbers; a near-duplicate with different figures is a different claim."""
    return sorted(NUMBER_RE.findall(a)) == sorted(NUMBER_RE.findall(b))


def merge_bullet(company: dict[str, Any], text: str, role_start: str | None, source: str) -> None:
    """Add a bullet, or record it as a source/variant of an identical or near-identical one."""
    bullet_id = pr.bullet_id(company["id"], text)
    hit = next((b for b in company["bullets"] if b["id"] == bullet_id), None)
    if hit is None:
        hit = next((b for b in company["bullets"] if pr.similar(b["text"], text) >= NEW_VARIANT_RATIO
                                                    and same_figures(b["text"], text)), None)
        if hit is not None and text != hit["text"] and text not in hit["variants"]:
            hit["variants"].append(text)
    if hit is None:
        hit = {"id": bullet_id, "text": text, "role_start": role_start, "skills": [], "themes": [],
               "metrics": pr.find_metrics(text), "sources": [], "variants": [], "needs_review": False,
               "ignored": False}
        company["bullets"].append(hit)
    add_unique(hit["sources"], source)
    add_unique(hit.setdefault("wordings", {}).setdefault(source, []), text)


def _wordings(bullet: Mapping[str, Any]) -> set[str]:
    """Every wording a bullet is known by: its text, its variants and the wording each file used."""
    texts = {bullet["text"], *bullet.get("variants", [])}
    for words in bullet.get("wordings", {}).values():
        texts.update(words)
    return texts


def _continues(new: Mapping[str, Any], old: Mapping[str, Any], pass_no: int) -> bool:
    """Whether `new` continues the stored bullet `old`: same id (1), a shared wording (2), or 0.92 similar
    text with the same numbers (3)."""
    if pass_no == 1:
        return new["id"] == old["id"]
    if pass_no == 2:
        return bool(_wordings(new) & _wordings(old))
    return any(pr.similar(n, o) >= NEW_VARIANT_RATIO and same_figures(n, o)
               for n in (new["text"], *new.get("variants", [])) for o in (old["text"], *old.get("variants", [])))


def _carry_company(new: Sequence[Any], old: Sequence[Any], curated: set[str]) -> None:
    """Give each bullet of `new` the id of the stored bullet it continues, using each old id once. Of several
    candidates a curated one wins, then the lowest id."""
    free = {b["id"]: b for b in old}
    taken: set[int] = set()
    for pass_no in (1, 2, 3):
        for bullet in sorted(new, key=lambda b: b["id"]):
            if id(bullet) in taken:
                continue
            found = sorted((o for o in free.values() if _continues(bullet, o, pass_no)),
                           key=lambda o: (o["id"] not in curated, o["id"]))
            if found:
                bullet["id"] = found[0]["id"]
                taken.add(id(bullet))
                del free[bullet["id"]]


def carry_ids(data: ResumeData, stored: Mapping[str, Any], curated: set[str]) -> None:
    """Keep each bullet's stored id through a rebuild while the bullet continues (see `_carry_company`)."""
    for cid, company in data["companies"].items():
        if cid in stored:
            _carry_company(company["bullets"], stored[cid]["bullets"], curated)


def merge_work(companies: dict[str, Any], source: str, work: Iterable[pr.WorkEntry]) -> None:
    """Merge the work history of one resume."""
    for entry in work:
        cid = entry["company_id"]
        company = companies.setdefault(cid, {"id": cid, "name": pr.COMPANIES[cid][0], "aliases": [], "roles": [],
                                             "bullets": []})
        merge_role(company, entry, source)
        for text in entry["bullets"]:
            merge_bullet(company, text, entry["start"], source)


def merge_skills(skills: dict[str, Any], parsed: dict[str, list[pr.SkillItem]], source: str) -> None:
    """Merge the skill groups of one resume into the vocabulary."""
    for group, items in parsed.items():
        entries = skills["groups"].setdefault(group, [])
        for item in items:
            existing = next((x for x in entries if x["name"].lower() == item["name"].lower()), None)
            if existing is None:
                existing = {"name": item["name"], "aliases": [], "sources": []}
                entries.append(existing)
            for alias in item["aliases"]:
                add_unique(existing["aliases"], alias)
            add_unique(existing["sources"], source)


def merge_profile(profile: dict[str, Any], parsed: pr.Resume, source: str) -> None:
    """Merge summary and the plain lists (headlines, profile points, education, certifications, projects), noting
    which file stated each item so that it can go when the file does."""
    if parsed["summary"]:
        sid = "sum-" + pr.bullet_id("s", parsed["summary"]).split("-")[1]
        existing = next((x for x in profile["summaries"] if x["id"] == sid), None)
        if existing is None:
            existing = {"id": sid, "text": parsed["summary"], "angles": [], "sources": []}
            profile["summaries"].append(existing)
        add_unique(existing["sources"], source)
    items = {"headlines": [parsed["headline"]] if parsed.get("headline") else []}
    items.update({key: cast(list[str], parsed[key]) for key in ("profile_points", "education", "certifications",
                                                                 "projects")})
    noted = profile.setdefault("item_sources", [])
    for section, texts in items.items():
        for text in texts:
            add_unique(profile.setdefault(section, []), text)
            entry = next((x for x in noted if x["section"] == section and x["text"] == text), None)
            if entry is None:
                entry = {"section": section, "text": text, "sources": []}
                noted.append(entry)
            add_unique(entry["sources"], source)


def strip_items(profile: dict[str, Any], key: str) -> None:
    """Take resume file `key` out of the profile items; an item no other file states is removed."""
    kept = []
    for item in profile.get("item_sources", []):
        if key in item["sources"]:
            item["sources"].remove(key)
            if not item["sources"]:
                if item["text"] in profile.get(item["section"], []):
                    profile[item["section"]].remove(item["text"])
                continue
        kept.append(item)
    profile["item_sources"] = kept


def _strip(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Remove `key` from each item's sources; return the items that still have a source."""
    kept = []
    for item in items:
        if key in item["sources"]:
            item["sources"].remove(key)
            if not item["sources"]:
                continue
        kept.append(item)
    return kept


def recompute_bullet(bullet: dict[str, Any], key: str) -> bool:
    """Take resume file `key` out of a bullet and rebuild its wording from the files that remain.

    The text stays when a remaining file still says it; otherwise it becomes the first remaining file's
    wording (the figures follow), and the other wordings are its variants. A flag set from the old figures is
    cleared so curation can set it again. Returns False when no file is left (the bullet goes).
    """
    wordings = bullet.setdefault("wordings", {s: [bullet["text"]] for s in bullet["sources"]})
    wordings.pop(key, None)
    if key in bullet["sources"]:
        bullet["sources"].remove(key)
    if not bullet["sources"]:
        return False
    left = [w for src in bullet["sources"] for w in wordings.get(src, [])]
    if left and bullet["text"] not in left:
        bullet["text"], bullet["metrics"], bullet["needs_review"] = left[0], pr.find_metrics(left[0]), False
    bullet["variants"] = [w for w in dict.fromkeys(left) if w != bullet["text"]]
    return True


def _strip_bullets(bullets: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Remove file `key` from every bullet it contributed to; bullets with no other file are dropped."""
    return [b for b in bullets if key not in b["sources"] or recompute_bullet(b, key)]


def strip_source(data: ResumeData, key: str) -> int:
    """Remove what resume file `key` contributed (bullets, roles and their titles and end dates, summaries,
    headlines, education, certifications, projects, skills with no other source). Skills with the source `curated`
    stay. Returns how many bullets were dropped."""
    companies = cast(dict[str, Any], data["companies"])
    dropped = 0
    for cid, company in list(companies.items()):
        before = len(company["bullets"])
        company["bullets"] = _strip_bullets(company["bullets"], key)
        company["roles"] = [r for r in company["roles"] if strip_role(r, key)]
        dropped += before - len(company["bullets"])
        if not company["bullets"] and not company["roles"]:
            del companies[cid]
    profile = cast(dict[str, Any], data["profile"])
    profile["summaries"] = _strip(profile["summaries"], key)
    strip_items(profile, key)
    groups = cast(dict[str, Any], data["skills"])["groups"]
    for group, entries in groups.items():
        groups[group] = _strip(entries, key)
    return dropped


def prune_missing(data: ResumeData, ledger: dict[str, Any], unparsed: dict[str, Any], present: set[str]) -> list[str]:
    """Drop the contribution, ledger, unparsed and raw-text entries of files that no longer exist; print what went."""
    gone = sorted(set(ledger) - present)
    for key in gone:
        dropped = strip_source(data, key)
        ledger.pop(key)
        unparsed.pop(key, None)
        (TEXT_DIR / text_name(key)).unlink(missing_ok=True)
        print(f"pruned (file gone): {key}  ({dropped} bullet(s) dropped)")
    return gone


def merge_resume(data: ResumeData, source: str, parsed: pr.Resume) -> None:
    """Merge one parsed resume into the in-memory data."""
    merge_work(cast(dict[str, Any], data["companies"]), source, parsed["work"])
    merge_skills(cast(dict[str, Any], data["skills"]), parsed["skills"], source)
    merge_profile(cast(dict[str, Any], data["profile"]), parsed, source)


# ---------------------------------------------------------------- curation

def retag(data: ResumeData) -> None:
    """(Re)compute skill tags on every bullet from the skills vocabulary and every stored wording of the line; keep
    manually added tags."""
    terms = pr.skill_terms(data["skills"]["groups"])
    terms.update({t: t for t in data["skills"].get("tag_only", [])})
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            auto = {s for text in rd.wordings_of(bullet) for s in pr.tag_skills(text, terms)}
            bullet["skills"] = sorted(auto | set(bullet.get("skills_manual", [])))


def add_extra_skills(data: ResumeData, extra: dict[str, list[dict[str, Any]]]) -> None:
    """Skills in your curation that no resume mentions."""
    for group, items in extra.items():
        entries = data["skills"]["groups"].setdefault(group, [])
        for item in items:
            if not any(x["name"].lower() == item["name"].lower() for x in entries):
                entries.append({"name": item["name"], "aliases": item.get("aliases", []), "sources": ["curated"]})


def collect_skills(data: ResumeData, merge: dict[str, str]) -> dict[str, dict[str, Any]]:
    """{canonical lower-case name: {name, aliases, sources, groups: {group: n sources}}} with spellings merged."""
    found: dict[str, dict[str, Any]] = {}
    for group, items in data["skills"]["groups"].items():
        for item in items:
            canon = merge.get(item["name"].lower(), item["name"])
            entry = found.setdefault(canon.lower(), {"name": canon, "aliases": set(), "sources": set(), "groups": {}})
            if item["name"] != canon:
                entry["aliases"].add(item["name"])
            entry["aliases"].update(a for a in item.get("aliases", []) if a.lower() != canon.lower())
            entry["sources"].update(item["sources"])
            entry["groups"][group] = entry["groups"].get(group, 0) + len(item["sources"])
    return found


def assign_groups(found: dict[str, dict[str, Any]], drop: set[str], override: dict[str, str]) -> dict[str, list[Any]]:
    """Give every kept skill exactly one group: the override, else the group with most sources, else Unsorted."""
    groups: dict[str, list[Any]] = {}
    for key, entry in found.items():
        if key in drop:
            continue
        group = override.get(key) or max((g for g in entry["groups"] if g != "Unsorted"),
                                         key=entry["groups"].get, default="Unsorted")
        groups.setdefault(group, []).append({"name": entry["name"], "aliases": sorted(entry["aliases"]),
                                             "sources": sorted(entry["sources"])})
    return groups


def curate_skills(data: ResumeData) -> None:
    """Merge duplicate spellings, drop non-skills, give every skill exactly one group (your skill curation)."""
    cur = rd.load_curated()
    add_extra_skills(data, cur.get("extra_skills", {}))
    found = collect_skills(data, {k.lower(): v for k, v in cur.get("skill_merge", {}).items()})
    groups = assign_groups(found, {d.lower() for d in cur.get("skill_drop", [])},
                           {k.lower(): v for k, v in cur.get("skill_group", {}).items()})
    data["skills"] = {"groups": groups, "tag_only": cur.get("tag_only", [])}


def apply_themes(data: ResumeData) -> None:
    """Themes, ignored fragments and summary positioning from your curation."""
    themes = rd.load_themes_file()
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            bullet["themes"] = themes["themes"].get(bullet["id"], bullet["themes"])
            bullet["ignored"] = bullet["id"] in themes.get("ignore", [])
    for summary in data["profile"]["summaries"]:
        summary["angles"] = themes.get("summary_angles", {}).get(summary["id"], summary.get("angles", []))


def number_pattern(number: str) -> re.Pattern[str]:
    """A flagged number as it appears in a line: never part of a longer number, so `12` matches "team of 12" and
    "12%" but not "120" or "1.25", and `40%` does not match "140%"."""
    before = r"(?<![\d.,])" if number[:1].isdigit() else ""
    after = r"(?![\d]|[.,]\d)" if number[-1:].isdigit() else ""
    return re.compile(before + re.escape(number) + after, re.I)


def flag_review(data: ResumeData, numbers: list[str]) -> None:
    """Mark the bullets that state a flagged number as needs_review."""
    found = [number_pattern(n) for n in numbers if n]
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            if any(f.search(bullet["text"]) for f in found):
                bullet["needs_review"] = True


def apply_curated(data: ResumeData) -> None:
    """The user's curation (certifications, themes, known-wrong figures ...) survives rebuilds (--force)."""
    cur = rd.load_curated()
    for key in ("certifications", "education"):
        if cur.get(key):                # an empty curated list counts as none
            data["profile"][key] = cur[key]
    apply_themes(data)
    flag_review(data, cur.get("review_if_metric_matches", []))


# ---------------------------------------------------------------- write

def build_index(data: ResumeData, ledger: dict[str, Any]) -> dict[str, Any]:
    """The index: a summary of what the data holds."""
    companies = rd.newest_first(data["companies"].values())
    return {
        "generated": now(),
        "companies": [{"id": c["id"], "name": c["name"], "bullets": len(c["bullets"]),
                       "roles": [{"start": r["start"], "end": r["end"], "titles": r["titles"]} for r in c["roles"]]}
                      for c in companies],
        "skill_groups": {g: len(v) for g, v in data["skills"]["groups"].items()},
        "themes": sorted({t for c in data["companies"].values() for b in c["bullets"] for t in b["themes"]}),
        "resumes": len(ledger),
    }


def write_data(data: ResumeData, ledger: dict[str, Any], unparsed: dict[str, Any]) -> None:
    """Store the companies, skills, sections, index, ledger and unparsed report."""
    for company in data["companies"].values():
        company["roles"].sort(key=lambda r: r["start"] or "", reverse=True)
        company["bullets"].sort(key=lambda b: (b.get("role_start") or "", b["id"]), reverse=True)
    tables.replace_companies(data["companies"])      # a company whose every resume is gone is removed
    for entries in data["skills"]["groups"].values():
        entries.sort(key=lambda x: x["name"].lower())
    skills = {"groups": dict(sorted(data["skills"]["groups"].items())), "tag_only": data["skills"].get("tag_only", [])}
    tables.replace_skills(skills)
    tables.replace_profile(cast(Mapping[str, Sequence[Any]], data["profile"]))
    tables.save_index(build_index(data, ledger))
    tables.replace_ledger(ledger)
    tables.replace_unparsed(unparsed)


# ---------------------------------------------------------------- build

def untraceable_wording(data: ResumeData) -> bool:
    """True when an older merged bullet (several files, or variants) does not record which file said what, so
    its wording cannot be rebuilt after a file goes. A single-file bullet is traceable as it is."""
    return any("wordings" not in b and (len(b["sources"]) > 1 or b.get("variants"))
               for c in data["companies"].values() for b in c["bullets"])


def untraceable_sources(data: ResumeData) -> bool:
    """True when stored roles or profile items predate the record of which file stated what."""
    if not data["companies"]:
        return False
    return "item_sources" not in data["profile"] or any(
        "ends" not in r for c in data["companies"].values() for r in c["roles"])


def curation_changed(data: ResumeData) -> bool:
    """True when the curation is not the one the stored data was built with. Curation only ever adds to stored
    data, so after a change (a removal above all) the data is rebuilt from the files."""
    return bool(data["companies"]) and tables.load_built_curation() != tables.curation_digest()


def load_state(force: bool) -> tuple[dict[str, Any], dict[str, Any], ResumeData]:
    """(ledger, unparsed, data) from the files on disk, or empty ones with --force."""
    empty: ResumeData = {"companies": {}, "skills": {"groups": {}}, "profile": rd.empty_profile()}
    if force:
        return {}, {}, empty
    data: ResumeData = {"companies": rd.load_companies(), "skills": rd.load_skills(), "profile": rd.load_profile()}
    if untraceable_wording(data) or untraceable_sources(data):
        print("Upgrading the stored data: rebuilding once from your resume files (your curation is kept).")
        return {}, {}, empty
    if (data["companies"] or rd.load_ledger()) and tables.load_built_parser() != pr.PARSER_VERSION:
        saved = store.save_committed_copy(store.connect(), "jobkit-before-reparse", "rebuilding it")
        print(f"The resume parser changed since the stored data was built. A copy of the database was saved as {common.hide_home(str(saved))}; "
              f"rebuilding from your resume files (your curation is kept).")
        return {}, {}, empty
    if curation_changed(data):
        print("Your curation changed since the last build: rebuilding from your resume files (your curation is kept).")
        return {}, {}, empty
    return rd.load_ledger(), tables.load_unparsed(), data


def process_file(path: Path, root: Path, ledger: dict[str, Any], unparsed: dict[str, Any], data: ResumeData) -> Outcome:
    """Parse one resume file unless the ledger says it is unchanged; merge it into `data`."""
    key, stat = rel(path, root), path.stat()
    old = ledger.get(key)
    transcript = visual.fingerprint(path, transcript_for(path, root))
    if old and old["mtime"] == stat.st_mtime and old["size"] == stat.st_size and old.get("visual") == transcript:
        return "unchanged"
    entry = {"mtime": stat.st_mtime, "size": stat.st_size, "sha256": file_sha(path), "processed_at": now()}
    if transcript:
        entry["visual"] = transcript
    if old:
        strip_source(data, key)             # the file changed: forget its old contribution, then merge it again
    try:
        doc = visual.read_document(path, transcript_for(path, root))
    except common.ToolError as error:
        ledger[key], unparsed[key] = {**entry, "kind": "other"}, [str(error)]
        needs = isinstance(error, extract.NeedsVisualRead)
        print(f"skip ({'needs visual reading, ask the user first' if needs else 'unreadable'}): {key}: {common.hide_home(str(error))}")
        return "other"
    (TEXT_DIR / text_name(key)).write_text(doc.text, encoding="utf-8")
    parsed = pr.parse_resume(doc.text, doc.layout_text)
    ledger[key] = {**entry, "kind": "other" if parsed["is_resume"] is False else "resume"}
    if parsed["is_resume"] is False:
        unparsed[key] = parsed["problems"]
        print(f"skip (not a resume): {key}")
        return "other"
    merge_resume(data, key, parsed)
    if parsed["problems"]:
        unparsed[key] = parsed["problems"]
    else:
        unparsed.pop(key, None)
    print(f"parsed: {key}  ({sum(len(e['bullets']) for e in parsed['work'])} bullets)")
    return "parsed"


def check_folders(dirs: Iterable[Path], root: Path, present: Iterable[Path], force: bool) -> None:
    """Stop before pruning when a configured folder has emptied although the ledger lists files from it.
    `--force` accepts that as a deliberate removal."""
    ledger = rd.load_ledger()
    if force or not ledger:
        return
    present = list(present)
    for folder in dirs:
        prefix = "" if folder == root else rel(folder, root) + "/"
        if any(key.startswith(prefix) for key in ledger) and not any(folder in p.parents for p in present):
            raise common.ToolError(
                f"No resume files found in {folder}, but earlier runs read files from it. Is the folder "
                f"unmounted or moved? Check `profile status`. If you moved them out on purpose, run "
                f"`process-resumes --force`.")


def build(files: Iterable[Path], root: Path, force: bool, dirs: Iterable[Path] = ()) -> None:
    """Process new or changed resumes, curate, and write the data files."""
    files = list(files)
    check_folders(dirs, root, files, force)
    digest = tables.curation_digest()
    stored = rd.load_companies()
    ledger, unparsed, data = load_state(force)
    TEXT_DIR.mkdir(exist_ok=True)
    present = sorted(files, key=lambda p: rel(p, root))
    pruned = prune_missing(data, ledger, unparsed, {rel(p, root) for p in present})
    outcomes = [process_file(path, root, ledger, unparsed, data) for path in present]
    curate_skills(data)
    retag(data)
    themes = rd.load_themes_file()
    carry_ids(data, stored, set(themes.get("themes", {})) | set(themes.get("ignore", [])))
    apply_curated(data)
    write_data(data, ledger, unparsed)
    tables.save_built_curation(digest)
    tables.save_built_parser(pr.PARSER_VERSION)
    orphans = rd.orphan_curation(data["companies"], data["profile"], rd.load_themes_file(), rd.load_curated())
    if orphans:
        print(f"\nWARNING: {len(orphans)} entr(ies) in your curation match no bullet or summary "
              f"(run `query-resume review` to list them).")
    bullets = sum(len(c["bullets"]) for c in data["companies"].values())
    print(f"\n{outcomes.count('parsed')} new/changed, {outcomes.count('unchanged')} unchanged, {len(pruned)} pruned. "
          f"Resume data: {len(data['companies'])} companies, {bullets} bullets. "
          f"{len(unparsed)} file(s) in the unparsed report (`jobkit export --only resume-unparsed`).")


def cmd_process(args: argparse.Namespace) -> None:
    """Scan the resume folders, then survey or build."""
    config = load_config()
    for folder in config.dirs:
        if not folder.is_dir():
            raise common.ToolError(f"The resume folder {folder} does not exist. Is it unmounted or moved? "
                                   f"Check `profile status`; nothing was changed.")
    files = list_resumes(config.dirs)
    if not files:
        raise common.ToolError(f"No resumes ({', '.join(extract.supported_suffixes())}) found under "
                               f"{', '.join(map(str, config.dirs))}. Check `profile status`.")
    scan_companies(files, config.root, save=not args.survey)
    if args.survey:
        survey(files, config.root)
    else:
        build(files, config.root, args.force, config.dirs)


def cmd_visual(args: argparse.Namespace) -> None:
    """The `visual` verbs: list, render, confirm, schema, text and compare (see visual.py)."""
    if args.action == "schema":
        print(visual_compare.READING_SCHEMA)
        return
    config = load_config()
    files = list_resumes(config.dirs)
    names = {p: (rel(p, config.root), transcript_name(rel(p, config.root))) for p in files}
    if args.action == "confirm":
        visual.cmd_confirm(names, args.file, args.remove)
    elif args.action == "render":
        visual.cmd_render(names, args.file)
    elif args.action == "text":
        visual.cmd_text(names, args.file, args.layout)
    elif args.action == "compare":
        visual.cmd_compare(names, args.file, common.read_text_arg(args.reading))
    else:
        visual.cmd_list(visual.pending(files, names))


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--survey", action="store_true", help="show parse results only; write nothing")
    parser.add_argument("--force", action="store_true", help="ignore ledger and rebuild")
    parser.set_defaults(fn=cmd_process)
    sub = parser.add_subparsers(dest="cmd")
    curate.add_parser(sub)
    visual.add_parser(sub, cmd_visual)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
