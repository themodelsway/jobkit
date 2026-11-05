#!/usr/bin/env python3
"""Per-user settings, kept in the database under the home folder (nothing personal lives in committed files).

  settings    resume_root, resume_dirs, name (optional), tier1_services (optional)
  employers   found by the first resume scan: {id: {"name", "regex"}}
  profile/header.md (in the home folder)  name and contact line printed at the top of generated resumes

Commands:
  profile status
  profile init --resume-root PATH [--resume-dir SUB ...] [--name NAME]
  profile set KEY VALUE         # name, resume_root
  profile companies [rename ID NAME | merge FROM INTO]   # employers from the scan; rename or merge them
  profile tier1 [SERVICE ...]   # pin your own tier-1 services (any track); no args shows the current list
  profile open [add TEXT | done ID]   # open items and data notes 

Standard library only. Run it as the `profile` command.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NotRequired, TypedDict, cast

from jobkit import common
from jobkit.common import ToolError
from jobkit.user import tables

DIR: Final[Path] = common.home() / "profile"
HEADER_FILE: Final[Path] = DIR / "header.md"
SEP: Final[str] = r"\s*[–—-]\s*"
SETTABLE_KEYS: Final[tuple[str, ...]] = ("name", "resume_root")
NEEDS_PROFILE: Final[str] = (
    "No profile yet. Ask the user where their resume files are, then run:\n"
    "  profile init --resume-root <folder> "
    "[--resume-dir <subfolder> ...] [--name <name>]")


class Profile(TypedDict):
    """Contents of profile/profile.json."""

    resume_root: str
    resume_dirs: NotRequired[list[str]]
    name: NotRequired[str]
    tier1_services: NotRequired[list[str]]


class OpenItem(TypedDict):
    """One entry of profile/open_items.json."""

    id: int
    text: str
    status: str


def load() -> Profile:
    """The saved profile, or an empty one."""
    return cast(Profile, tables.load_settings())


def save(profile: Profile) -> None:
    """Store the profile."""
    tables.save_settings(profile)


def exists() -> bool:
    """Whether the profile has been created."""
    return tables.has_settings()


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
        tables.save_employers(stored)
    return new


def header_path() -> Path:
    """Where the resume header (name and contact line) lives."""
    return HEADER_FILE


def personal_terms() -> set[str]:
    """Your name, resume folder and employer names, for the privacy checks. Empty without a profile."""
    terms: set[str] = set()
    stored = load()
    terms |= {str(value).strip() for value in (stored.get("name"), stored.get("resume_root")) if value}
    if HEADER_FILE.exists():
        terms |= {re.sub(r"^#\s*", "", line).strip() for line in HEADER_FILE.read_text(encoding="utf-8").splitlines()[:1]}
    terms |= {entry["name"] for entry in tables.load_employers().values()}
    return {t for t in terms if len(t) >= 3 and t.lower() != "your name"}


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
    print(f"header: {'present' if HEADER_FILE.exists() else 'missing (build-resume creates a template)'}")


def cmd_init(args: argparse.Namespace) -> None:
    """Create or update the profile."""
    root = Path(args.resume_root).expanduser()
    if not root.is_dir():
        raise ToolError(f"{root} is not a folder")
    profile = load()
    profile["resume_root"] = str(args.resume_root)
    profile["resume_dirs"] = args.resume_dir or profile.get("resume_dirs") or []
    if args.name:
        profile["name"] = args.name
    save(profile)
    print("Saved the profile. Next: process-resumes")


def cmd_set(args: argparse.Namespace) -> None:
    """Change one setting."""
    if args.key not in SETTABLE_KEYS:
        raise ToolError("keys: " + ", ".join(SETTABLE_KEYS))
    profile = need()
    if args.key == "name":
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
    tables.save_employers(employers)
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
    tables.save_employers(employers)
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
    tables.save_open_items(items)


def _finish_open_item(items: list[OpenItem], item_id: str | None) -> None:
    match = [item for item in items if str(item["id"]) == item_id]
    if not match:
        raise ToolError(f"No open item {item_id}")
    match[0]["status"] = "done"
    tables.save_open_items(items)


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
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
