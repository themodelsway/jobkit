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

from jobkit import common
from jobkit.resumes import curate, extract, tables
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import resume_data as rd
from jobkit.resumes.resume_data import ResumeData
from jobkit.user import profile as up

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


def scan_companies(files: Iterable[Path], save: bool) -> None:
    """First-run scan: find the employers in every resume so nothing has to be typed in. With `save`, new
    employers are stored in the database (existing entries are never changed)."""
    found: dict[str, str] = {}
    for path in files:
        try:
            doc = extract.extract(path)
        except common.ToolError:
            continue                        # reported later, per file, by survey or build
        discovered = pr.discover_companies(doc.layout_text or doc.text)
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
    """The file's path relative to the resume root (its key in the ledger)."""
    return str(path.relative_to(root))


def file_sha(path: Path) -> str:
    """SHA-256 of the file contents."""
    return sha256(path.read_bytes()).hexdigest()


def text_name(key: str) -> str:
    """File name for the raw extracted text of a ledger key (`a/b c.pdf` -> `a__b_c.txt`; other formats keep their
    suffix, `a/b.docx` -> `a__b.docx.txt`, so two formats of one resume never collide)."""
    return key.replace("/", "__").replace(" ", "_").removesuffix(".pdf") + ".txt"


def now() -> str:
    """Timestamp for the ledger."""
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- survey

def survey(files: Iterable[Path], root: Path) -> None:
    """Print what each resume parses into, writing nothing."""
    for path in sorted(files, key=lambda p: rel(p, root)):
        try:
            doc = extract.extract(path)
        except common.ToolError as error:
            print(f"{rel(path, root)}\n  UNREADABLE: {error}")
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
        for problem in parsed["problems"]:
            print(f"  PROBLEM: {problem}")


# ---------------------------------------------------------------- merge

def add_unique(items: list[str], value: str) -> None:
    """Append value when it is not empty and not already there."""
    if value and value not in items:
        items.append(value)


def merge_role(company: dict[str, Any], entry: pr.WorkEntry, source: str) -> None:
    """One role per (start, end); titles/subtitles/clients seen in tailored resumes are kept as variants."""
    role = next((r for r in company["roles"] if r["start"] == entry["start"] and r["end"] == entry["end"]), None)
    if role is None:
        role = {"start": entry["start"], "end": entry["end"], "titles": [], "subtitles": [], "clients": [],
                "sources": []}
        company["roles"].append(role)
    add_unique(role["titles"], entry["title"])
    add_unique(role["subtitles"], entry["subtitle"])
    add_unique(role["clients"], entry["client"])
    add_unique(role["sources"], source)


def merge_bullet(company: dict[str, Any], text: str, role_start: str | None, source: str) -> None:
    """Add a bullet, or record it as a source/variant of an identical or near-identical one."""
    bullet_id = pr.bullet_id(company["id"], text)
    hit = next((b for b in company["bullets"] if b["id"] == bullet_id), None)
    if hit is None:
        hit = next((b for b in company["bullets"] if pr.similar(b["text"], text) >= NEW_VARIANT_RATIO), None)
        if hit is not None and text != hit["text"] and text not in hit["variants"]:
            hit["variants"].append(text)
    if hit is None:
        hit = {"id": bullet_id, "text": text, "role_start": role_start, "skills": [], "themes": [],
               "metrics": pr.find_metrics(text), "sources": [], "variants": [], "needs_review": False,
               "ignored": False}
        company["bullets"].append(hit)
    add_unique(hit["sources"], source)


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
    """Merge summary, headline and the plain lists (profile points, education, certifications, projects)."""
    if parsed["summary"]:
        sid = "sum-" + pr.bullet_id("s", parsed["summary"]).split("-")[1]
        existing = next((x for x in profile["summaries"] if x["id"] == sid), None)
        if existing is None:
            existing = {"id": sid, "text": parsed["summary"], "angles": [], "sources": []}
            profile["summaries"].append(existing)
        add_unique(existing["sources"], source)
    if parsed.get("headline"):
        add_unique(profile.setdefault("headlines", []), parsed["headline"])
    bucket_keys = ("profile_points", "education", "certifications", "projects")
    for key in bucket_keys:
        for text in cast(list[str], parsed[key]):
            add_unique(profile[key], text)


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


def strip_source(data: ResumeData, key: str) -> int:
    """Remove what resume file `key` contributed (bullets, roles, summaries, skills with no other source).
    Skills with the source `curated` stay. Returns how many bullets were dropped."""
    companies = cast(dict[str, Any], data["companies"])
    dropped = 0
    for cid, company in list(companies.items()):
        before = len(company["bullets"])
        company["bullets"] = _strip(company["bullets"], key)
        company["roles"] = _strip(company["roles"], key)
        dropped += before - len(company["bullets"])
        if not company["bullets"] and not company["roles"]:
            del companies[cid]
    profile = cast(dict[str, Any], data["profile"])
    profile["summaries"] = _strip(profile["summaries"], key)
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
    """(Re)compute skill tags on every bullet from the skills vocabulary; keep manually added tags."""
    terms = pr.skill_terms(data["skills"]["groups"])
    terms.update({t: t for t in data["skills"].get("tag_only", [])})
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            auto = set(pr.tag_skills(bullet["text"], terms))
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
    """Themes, ignored fragments and summary angles from your curation."""
    themes = rd.load_themes_file()
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            bullet["themes"] = themes["themes"].get(bullet["id"], bullet["themes"])
            bullet["ignored"] = bullet["id"] in themes.get("ignore", [])
    for summary in data["profile"]["summaries"]:
        summary["angles"] = themes.get("summary_angles", {}).get(summary["id"], summary.get("angles", []))


def flag_review(data: ResumeData, patterns: list[str]) -> None:
    """Mark bullets whose metrics contain a known-wrong figure as needs_review."""
    for company in data["companies"].values():
        for bullet in company["bullets"]:
            if any(p in m for m in bullet["metrics"] for p in patterns):
                bullet["needs_review"] = True


def apply_curated(data: ResumeData) -> None:
    """The user's curation (certifications, themes, known-wrong figures ...) survives rebuilds (--force)."""
    cur = rd.load_curated()
    for key in ("certifications", "education"):
        if key in cur:
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
    tables.save_companies(data["companies"])      # a company whose every resume is gone is removed
    for entries in data["skills"]["groups"].values():
        entries.sort(key=lambda x: x["name"].lower())
    skills = {"groups": dict(sorted(data["skills"]["groups"].items())), "tag_only": data["skills"].get("tag_only", [])}
    tables.save_skills(skills)
    tables.save_profile(cast(Mapping[str, Sequence[Any]], data["profile"]))
    tables.save_index(build_index(data, ledger))
    tables.save_ledger(ledger)
    tables.save_unparsed(unparsed)


# ---------------------------------------------------------------- build

def load_state(force: bool) -> tuple[dict[str, Any], dict[str, Any], ResumeData]:
    """(ledger, unparsed, data) from the files on disk, or empty ones with --force."""
    if force:
        return {}, {}, {"companies": {}, "skills": {"groups": {}}, "profile": rd.empty_profile()}
    data: ResumeData = {"companies": rd.load_companies(), "skills": rd.load_skills(), "profile": rd.load_profile()}
    return rd.load_ledger(), tables.load_unparsed(), data


def process_file(path: Path, root: Path, ledger: dict[str, Any], unparsed: dict[str, Any], data: ResumeData) -> Outcome:
    """Parse one resume file unless the ledger says it is unchanged; merge it into `data`."""
    key, stat = rel(path, root), path.stat()
    old = ledger.get(key)
    if old and old["mtime"] == stat.st_mtime and old["size"] == stat.st_size:
        return "unchanged"
    entry = {"mtime": stat.st_mtime, "size": stat.st_size, "sha256": file_sha(path), "processed_at": now()}
    if old:
        strip_source(data, key)             # the file changed: forget its old contribution, then merge it again
    try:
        doc = extract.extract(path)
    except common.ToolError as error:
        ledger[key], unparsed[key] = {**entry, "kind": "other"}, [str(error)]
        print(f"skip (unreadable): {key}: {error}")
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


def build(files: Iterable[Path], root: Path, force: bool) -> None:
    """Process new or changed resumes, curate, and write the data files."""
    ledger, unparsed, data = load_state(force)
    TEXT_DIR.mkdir(exist_ok=True)
    present = sorted(files, key=lambda p: rel(p, root))
    pruned = prune_missing(data, ledger, unparsed, {rel(p, root) for p in present})
    outcomes = [process_file(path, root, ledger, unparsed, data) for path in present]
    curate_skills(data)
    retag(data)
    apply_curated(data)
    write_data(data, ledger, unparsed)
    orphans = rd.orphan_curation(data["companies"], data["profile"], rd.load_themes_file())
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
    files = list_resumes(config.dirs)
    if not files:
        raise common.ToolError(f"No resumes ({', '.join(extract.supported_suffixes())}) found under "
                               f"{', '.join(map(str, config.dirs))}. Check `profile status`.")
    scan_companies(files, save=not args.survey)
    if args.survey:
        survey(files, config.root)
    else:
        build(files, config.root, args.force)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--survey", action="store_true", help="show parse results only; write nothing")
    parser.add_argument("--force", action="store_true", help="ignore ledger and rebuild")
    parser.set_defaults(fn=cmd_process)
    sub = parser.add_subparsers(dest="cmd")
    curate.add_parser(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
