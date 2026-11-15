#!/usr/bin/env python3
"""Per-user settings, kept in the database under the home folder (nothing personal lives in committed files).

  settings    resume_root, resume_dirs, name (optional), tier1_services (optional)
  employers   found by the first resume scan: {id: {"name", "regex"}}
  settings    header (name and contact line printed at the top of generated resumes; an older profile/header.md
              file in the home folder is still read when no header is saved)

Commands:
  profile status
  profile init --resume-root PATH [--resume-dir SUB ...] [--name NAME]
  profile set KEY VALUE         # name, resume_root, reassess_days, years_experience (shown as "N+ years" in built summaries),
                                # answer_style (star, soar or carl: the default way a story is shown and judged complete),
                                # research_days (when a researched company's facts count as stale; default 30),
                                # target_company (a researched company `target show` and `prep for-target` use by
                                # default; "" clears it)
  profile header [set NAME CONTACT_LINE]   # the name and contact line at the top of built resumes; no args shows it
  profile companies [rename ID NAME | merge FROM INTO]   # employers from the scan; rename or merge them
  profile tier1 [SERVICE ...]   # pin your own tier-1 services (any track); no args shows the current list
  profile open [add TEXT | done ID]   # open items and data notes 
  profile terms [list | add TEXT [--kind K] [--match word|phrase|regex] | ignore TEXT | rm TEXT | import FILE
                 | check [--staged | --all | PATH ...]]   # personal words that must never be committed (contributors)

Standard library only. Run it as the `profile` command.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NotRequired, TypedDict, cast

from jk import common, store
from jk.common import ToolError
from jk.interview import target_tables
from jk.resumes import tables as resume_tables
from jk.user import tables, terms

DIR: Final[Path] = common.home() / "profile"
HEADER_FILE: Final[Path] = DIR / "header.md"
SEP: Final[str] = r"\s*[–—-]\s*"
SETTABLE_KEYS: Final[tuple[str, ...]] = ("name", "resume_root", "reassess_days", "years_experience", "answer_style",
                                         "research_days", "target_company")
ANSWER_STYLES: Final[tuple[str, ...]] = ("star", "soar", "carl")
YEARS_RANGE: Final[tuple[int, int]] = (1, 60)
DEFAULT_REASSESS_DAYS: Final[int] = 30   # a good answer older than this is offered for a retest
REASSESS_RANGE: Final[tuple[int, int]] = (1, 365)
DEFAULT_RESEARCH_DAYS: Final[int] = 30   # researched company facts older than this are read again
NEEDS_PROFILE: Final[str] = (
    "No profile yet. Ask the user where their resume files are, then run:\n"
    "  profile init --resume-root <folder> "
    "[--resume-dir <subfolder> ...] [--name <name>]")


class Profile(TypedDict):
    """The stored profile settings."""

    resume_root: str
    resume_dirs: NotRequired[list[str]]
    name: NotRequired[str]
    tier1_services: NotRequired[list[str]]
    reassess_days: NotRequired[int]
    header: NotRequired[str]
    years_experience: NotRequired[int]
    answer_style: NotRequired[str]
    research_days: NotRequired[int]
    target_company: NotRequired[str]


class OpenItem(TypedDict):
    """One open item."""

    id: int
    text: str
    status: str


def load() -> Profile:
    """The saved profile, or an empty one."""
    return cast(Profile, tables.load_settings())


def save(profile: Profile) -> None:
    """Store the profile."""
    tables.replace_settings(profile)


def exists() -> bool:
    """Whether the profile has been created."""
    return tables.has_settings()


def reassess_days() -> int:
    """The retest window in days: the stored value, or 30 when none is stored."""
    value = tables.load_settings().get("reassess_days")
    low, high = REASSESS_RANGE
    return value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high \
        else DEFAULT_REASSESS_DAYS


def parse_window(text: str) -> int:
    """A retest window from text: a whole number of days from 1 to 365, else a `ToolError`."""
    low, high = REASSESS_RANGE
    try:
        days = int(text)
    except ValueError:
        days = low - 1
    if not low <= days <= high:
        raise ToolError(f"reassess_days must be a whole number of days from {low} to {high}, not {text!r}.")
    return days


def parse_years(text: str) -> int:
    """Years of experience from text ("26" or "26+"): a whole number from 1 to 60, else a `ToolError`."""
    low, high = YEARS_RANGE
    try:
        years = int(text.strip().rstrip("+"))
    except ValueError:
        years = low - 1
    if not low <= years <= high:
        raise ToolError(f"years_experience must be a whole number from {low} to {high}, not {text!r}.")
    return years


def parse_answer_style(text: str) -> str:
    """An answer style from text (star, soar or carl), else a `ToolError` naming the three."""
    style = text.strip().lower()
    if style not in ANSWER_STYLES:
        raise ToolError(f"answer_style must be one of {', '.join(ANSWER_STYLES)}, not {text!r}.")
    return style


def answer_style() -> str | None:
    """The default answer style the user saved, or None when none is saved (star applies then)."""
    value = tables.load_settings().get("answer_style")
    return value if value in ANSWER_STYLES else None


def parse_research_days(text: str) -> int:
    """A research window from text: a whole number of days of 1 or more, else a `ToolError`."""
    try:
        days = int(text)
    except ValueError:
        days = 0
    if days < 1:
        raise ToolError(f"research_days must be a whole number of days of 1 or more, not {text!r}.")
    return days


def research_days() -> int:
    """The research window in days: the stored value, or 30 when none is stored."""
    value = tables.load_settings().get("research_days")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else DEFAULT_RESEARCH_DAYS


def parse_target_company(text: str) -> str | None:
    """The stored name of a researched company given in any letter case; None for "" (clears the default).

    Raises:
        ToolError: no researched company has that name (the message lists the ones that exist).
    """
    if not text.strip():
        return None
    found = target_tables.load_company(text)
    if found is None:
        names = ", ".join(target_tables.company_names()) or "none yet"
        raise ToolError(f"No researched company {text!r}. Researched companies: {names}.")
    return str(found["name"])


def target_company() -> str | None:
    """The default target company the user saved, or None."""
    value = tables.load_settings().get("target_company")
    return value if isinstance(value, str) and value else None


def years_experience() -> int | None:
    """The years of experience the user gave (built summaries show it as "N+ years"), or None."""
    return load().get("years_experience")


def need() -> Profile:
    """The profile, or fail with the instruction the skills turn into a question for the user."""
    if not exists():
        raise ToolError(NEEDS_PROFILE)
    return load()


def resume_root() -> Path:
    """Folder that holds the resume files."""
    return Path(need()["resume_root"]).expanduser()


def resume_dirs() -> list[Path]:
    """Folders to scan: the chosen subfolders of the resume root, or the root itself."""
    profile = need()
    root = Path(profile["resume_root"]).expanduser()
    return [root / sub for sub in profile.get("resume_dirs") or [""]]


def tier1_services() -> list[str]:
    """Services the user pinned as tier 1 (empty: derive them from the resume scan)."""
    return load().get("tier1_services") or []


def company_registry() -> dict[str, tuple[str, str]]:
    """{id: (display name, header regex)} ready for parse_resume.set_companies. Empty before the first scan."""
    stored = tables.load_employers()
    return {cid: (entry["name"], entry["regex"]) for cid, entry in stored.items()}


def add_companies(found: dict[str, str]) -> list[str]:
    """Merge employers found by a scan ({id: name}); never overwrites or removes an entry you have edited.

    Returns the ids that were new.
    """
    stored = tables.load_employers()
    new = [cid for cid in found if cid not in stored]
    for cid in new:
        stored[cid] = {"name": found[cid], "regex": re.escape(found[cid]) + rf"(?:{SEP}(?P<t>.+))?"}
    if new:
        tables.replace_employers(stored)
    return new


def header_path() -> Path:
    """Where the resume header (name and contact line) lives."""
    return HEADER_FILE


def header_text() -> str | None:
    """The saved name and contact line (Markdown: `# Name` then the contact line), or the older header.md file's
    text, or None when neither exists."""
    saved = load().get("header")
    if saved:
        return saved
    return HEADER_FILE.read_text(encoding="utf-8") if HEADER_FILE.exists() else None


def cmd_header(args: argparse.Namespace) -> None:
    """Show the saved header, or `header set NAME CONTACT_LINE` to save it."""
    if args.action == "set":
        if not args.name or not args.contact or not args.name.strip() or not args.contact.strip():
            raise ToolError("header set needs a name and a contact line: profile header set NAME CONTACT_LINE")
        profile = need()
        profile["header"] = f"# {args.name.strip()}\n{args.contact.strip()}\n"
        save(profile)
    print((header_text() or "No header saved yet. Save one with: profile header set NAME CONTACT_LINE").rstrip())


def derived_terms() -> list[terms.Term]:
    """Terms read from what is stored: name, header contact details, resume folder and employer names."""
    stored = load()
    return terms.derive(stored.get("name"), stored.get("resume_root"), header_text(),
                        [entry["name"] for entry in tables.load_employers().values()],
                        terms.folder_names(resume_tables.load_ledger(), stored.get("resume_dirs") or ()))


def cmd_terms(args: argparse.Namespace) -> int:
    """List, change, import or check the personal terms."""
    return terms.run(args, derived_terms())


def cmd_status(args: argparse.Namespace) -> None:
    """Show what the profile holds and what is still missing."""
    if not exists():
        print("No profile. Run `profile init --resume-root PATH` "
              "(the skills ask for the folder first).")
        return
    profile = load()
    pinned = profile.get("tier1_services")
    print(f"resume_root: {profile['resume_root']}")
    print(f"resume_dirs: {', '.join(profile.get('resume_dirs') or ['(whole folder)'])}")
    print(f"name: {profile.get('name') or '(not set)'}")
    print(f"employers: {len(tables.load_employers())} (run process-resumes to scan)"
          if tables.has_employers() else "employers: not scanned yet (run process-resumes)")
    print(f"tier-1 services: {f'pinned list of {len(pinned)}' if pinned else 'from your resume scan'}")
    stored = profile.get("reassess_days")
    print(f"years of experience: {profile.get('years_experience') or '(not set: summaries show what your resume says)'}")
    print(f"retest window: {reassess_days()} days" + ("" if stored is not None else " (default, not set)"))
    print(f"answer style: {answer_style() or 'star (default, not set)'}")
    print(f"research window: {research_days()} days" + ("" if profile.get("research_days") is not None else " (default, not set)"))
    print(f"default target company: {target_company() or '(not set)'}")
    print(f"header: {'present' if header_text() else 'missing (profile header set NAME CONTACT_LINE)'}")


def cmd_init(args: argparse.Namespace) -> None:
    """Create the profile, or fill in what is still unset; an existing answer is never overwritten (use `set`)."""
    root = Path(args.resume_root).expanduser()
    if not root.is_dir():
        raise ToolError(f"{root} is not a folder")
    profile = load()
    kept = [key for key, given in (("resume_root", args.resume_root), ("name", args.name), ("resume_dirs", args.resume_dir))
            if given and profile.get(key) and profile[key] != given]
    profile.setdefault("resume_root", str(args.resume_root))
    profile["resume_dirs"] = profile.get("resume_dirs") or args.resume_dir or []
    if args.name and not profile.get("name"):
        profile["name"] = args.name
    save(profile)
    if kept:
        print(f"Kept the existing {', '.join(kept)} (init never overwrites an answer; `profile set` changes name or resume_root).")
    print("Saved the profile. Next: process-resumes")


def _set_target_company(settings: Profile, value: str) -> None:
    """Set the default target company (a researched one), or clear it with ""."""
    name = parse_target_company(value)
    if name is None:
        settings.pop("target_company", None)
    else:
        settings["target_company"] = name


def cmd_set(args: argparse.Namespace) -> None:
    """Change one setting."""
    if args.key not in SETTABLE_KEYS:
        raise ToolError("keys: " + ", ".join(SETTABLE_KEYS))
    profile = need()
    if args.key == "reassess_days":
        profile["reassess_days"] = parse_window(args.value)
    elif args.key == "years_experience":
        profile["years_experience"] = parse_years(args.value)
    elif args.key == "answer_style":
        profile["answer_style"] = parse_answer_style(args.value)
    elif args.key == "research_days":
        profile["research_days"] = parse_research_days(args.value)
    elif args.key == "target_company":
        _set_target_company(profile, args.value)
    elif args.key == "name":
        profile["name"] = args.value
    else:
        profile["resume_root"] = args.value
    save(profile)


TITLE_SUFFIX: Final[str] = rf"(?:{SEP}(?P<t>.+))?"


def rename_company(args: list[str]) -> None:
    """`companies rename ID NAME`: change the name shown for an employer (its match pattern is unchanged)."""
    if len(args) != 2:
        raise ToolError("usage: companies rename ID NAME")
    employers = tables.load_employers()
    if args[0] not in employers:
        raise ToolError(f"No employer {args[0]}. Run `companies` to list them.")
    employers[args[0]]["name"] = args[1]
    tables.replace_employers(employers)
    print(f"Renamed {args[0]} to {args[1]}. Run `process-resumes --force` to rebuild with the new name.")


def merge_companies(args: list[str]) -> None:
    """`companies merge FROM INTO`: treat two names as one employer; FROM is folded into INTO."""
    if len(args) != 2 or args[0] == args[1]:
        raise ToolError("usage: companies merge FROM INTO (two different employer ids)")
    employers = tables.load_employers()
    for cid in args:
        if cid not in employers:
            raise ToolError(f"No employer {cid}. Run `companies` to list them.")
    source, target = employers.pop(args[0]), employers[args[1]]
    heads = [e["regex"][:-len(TITLE_SUFFIX)] for e in (target, source) if e["regex"].endswith(TITLE_SUFFIX)]
    if len(heads) != 2:
        raise ToolError("These employers have a custom match pattern, so they cannot be merged automatically.")
    target["regex"] = f"(?:{heads[0]}|{heads[1]}){TITLE_SUFFIX}"
    target["aliases"] = sorted({*target.get("aliases", []), source["name"], *source.get("aliases", [])})
    tables.replace_employers(employers)
    print(f"Merged {args[0]} into {args[1]}. Run `process-resumes --force` to rebuild.")


def cmd_companies(args: argparse.Namespace) -> None:
    """List the employers found by the resume scan, or rename / merge them."""
    if args.action == "rename":
        rename_company(args.args)
    elif args.action == "merge":
        merge_companies(args.args)
    else:
        for cid, entry in tables.load_employers().items():
            print(f"{cid:<24} {entry['name']}")
        if not tables.has_employers():
            print("No scan yet: run process-resumes")


def cmd_tier1(args: argparse.Namespace) -> None:
    """Pin the tier-1 services, or show the pinned list."""
    profile = need()
    if args.services:
        profile["tier1_services"] = args.services
        save(profile)
    print("\n".join(profile.get("tier1_services") or ["(none pinned: tier 1 comes from your resume scan)"]))


def _add_open_item(items: list[OpenItem], text: str | None) -> None:
    if not text:
        raise ToolError("open add needs the text of the item")
    items.append({"id": max([item["id"] for item in items] + [0]) + 1, "text": text, "status": "open"})
    tables.replace_open_items(items)


def _finish_open_item(items: list[OpenItem], item_id: str | None) -> None:
    match = [item for item in items if str(item["id"]) == item_id]
    if not match:
        raise ToolError(f"No open item {item_id}")
    match[0]["status"] = "done"
    tables.replace_open_items(items)


def cmd_open(args: argparse.Namespace) -> None:
    """List open items, or add one / mark one done."""
    items = cast(list[OpenItem], tables.load_open_items())
    if args.action == "add":
        _add_open_item(items, args.arg)
    elif args.action == "done":
        _finish_open_item(items, args.arg)
    still_open = [item for item in items if item["status"] == "open"]
    for item in still_open:
        print(f"{item['id']}. {item['text']}")
    if not still_open:
        print("No open items.")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    init = sub.add_parser("init")
    init.add_argument("--resume-root", required=True)
    init.add_argument("--resume-dir", action="append")
    init.add_argument("--name")
    init.set_defaults(fn=cmd_init)
    setter = sub.add_parser("set")
    setter.add_argument("key")
    setter.add_argument("value")
    setter.set_defaults(fn=cmd_set)
    companies = sub.add_parser("companies")
    companies.add_argument("action", nargs="?", choices=["rename", "merge"])
    companies.add_argument("args", nargs="*")
    companies.set_defaults(fn=cmd_companies)
    header = sub.add_parser("header")
    header.add_argument("action", nargs="?", choices=["set"])
    header.add_argument("name", nargs="?")
    header.add_argument("contact", nargs="?")
    header.set_defaults(fn=cmd_header)
    term_cmd = sub.add_parser("terms")
    terms.add_arguments(term_cmd)
    term_cmd.set_defaults(fn=cmd_terms)
    tier1 = sub.add_parser("tier1")
    tier1.add_argument("services", nargs="*")
    tier1.set_defaults(fn=cmd_tier1)
    open_items = sub.add_parser("open")
    open_items.add_argument("action", nargs="?", choices=["add", "done"])
    open_items.add_argument("arg", nargs="?")
    open_items.set_defaults(fn=cmd_open)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    args = build_parser().parse_args(argv)
    if args.cmd == "terms" and args.action == "check" and not store.db_path().exists():
        print("personal terms: no database here, nothing to check (skipped)")
        return 0
    return common.run(args, lock=args.cmd != "terms" or args.action not in (None, "list", "check"))


if __name__ == "__main__":
    raise SystemExit(main())
