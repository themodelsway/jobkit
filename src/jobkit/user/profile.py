#!/usr/bin/env python3
"""Per-user settings, kept in the git-ignored `profile/` folder (nothing personal lives in committed files).

  profile/profile.json    resume_root, resume_dirs, name (optional), tier1_services (optional)
  profile/companies.json  employers found by the first resume scan: {id: {"name", "regex"}}
  profile/header.md       name and contact line printed at the top of generated resumes

Commands:
  python src/user/profile.py status
  python src/user/profile.py init --resume-root PATH [--resume-dir SUB ...] [--name NAME]
  python src/user/profile.py set KEY VALUE         # name, resume_root
  python src/user/profile.py companies             # employers from the scan (edit companies.json to merge or rename)
  python src/user/profile.py tier1 [SERVICE ...]   # pin your own tier-1 AWS services; no args shows the current list
  python src/user/profile.py open [add TEXT | done ID]   # open items and data notes (profile/open_items.json)

Standard library only. The module is `user.profile`; run it as a script, never as `import profile`.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NotRequired, TypedDict

from jobkit import common
from jobkit.common import ToolError

DIR: Final[Path] = common.REPO_ROOT / "profile"
PROFILE_FILE: Final[Path] = DIR / "profile.json"
COMPANIES_FILE: Final[Path] = DIR / "companies.json"
HEADER_FILE: Final[Path] = DIR / "header.md"
OPEN_ITEMS_FILE: Final[Path] = DIR / "open_items.json"
SEP: Final[str] = r"\s*[–—-]\s*"
SETTABLE_KEYS: Final[tuple[str, ...]] = ("name", "resume_root")
NEEDS_PROFILE: Final[str] = (
    "No profile yet. Ask the user where their resume files are, then run:\n"
    "  .venv/bin/python src/user/profile.py init --resume-root <folder> "
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
    return common.load_json(PROFILE_FILE, {})


def save(profile: Profile) -> None:
    """Write the profile atomically."""
    common.save_json(PROFILE_FILE, profile)


def exists() -> bool:
    """Whether profile/profile.json has been created."""
    return PROFILE_FILE.exists()


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
    """AWS services the user pinned as tier 1 (empty: derive them from the resume scan)."""
    return load().get("tier1_services") or []


def company_registry() -> dict[str, tuple[str, str]]:
    """{id: (display name, header regex)} ready for parse_resume.set_companies. Empty before the first scan."""
    stored = common.load_json(COMPANIES_FILE, {})
    return {cid: (entry["name"], entry["regex"]) for cid, entry in stored.items()}


def add_companies(found: dict[str, str]) -> list[str]:
    """Merge employers found by a scan ({id: name}); never overwrites or removes an entry you have edited.

    Returns the ids that were new.
    """
    stored = common.load_json(COMPANIES_FILE, {})
    new = [cid for cid in found if cid not in stored]
    for cid in new:
        stored[cid] = {"name": found[cid], "regex": re.escape(found[cid]) + rf"(?:{SEP}(?P<t>.+))?"}
    if new:
        common.save_json(COMPANIES_FILE, stored)
    return new


def header_path() -> Path:
    """Where the resume header (name and contact line) lives."""
    return HEADER_FILE


def cmd_status(args: argparse.Namespace) -> None:
    """Show what the profile holds and what is still missing."""
    if not exists():
        print("No profile. Run `src/user/profile.py init --resume-root PATH` "
              "(the skills ask for the folder first).")
        return
    profile = load()
    pinned = profile.get("tier1_services")
    print(f"resume_root: {profile['resume_root']}")
    print(f"resume_dirs: {', '.join(profile.get('resume_dirs') or ['(whole folder)'])}")
    print(f"name: {profile.get('name') or '(not set)'}")
    print(f"employers: {len(common.load_json(COMPANIES_FILE, {}))} (run process_resumes.py to scan)"
          if COMPANIES_FILE.exists() else "employers: not scanned yet (run process_resumes.py)")
    print(f"tier-1 AWS services: {f'pinned list of {len(pinned)}' if pinned else 'from your resume scan'}")
    print(f"header: {'present' if HEADER_FILE.exists() else 'missing (build_resume.py creates a template)'}")


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
    print(f"Saved {PROFILE_FILE.relative_to(DIR.parent)}. "
          "Next: .venv/bin/python src/resumes/process_resumes.py")


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


def cmd_companies(args: argparse.Namespace) -> None:
    """List the employers found by the resume scan."""
    for cid, entry in common.load_json(COMPANIES_FILE, {}).items():
        print(f"{cid:<24} {entry['name']}")
    if not COMPANIES_FILE.exists():
        print("No scan yet: run process_resumes.py")


def cmd_tier1(args: argparse.Namespace) -> None:
    """Pin the tier-1 AWS services, or show the pinned list."""
    profile = need()
    if args.services:
        profile["tier1_services"] = args.services
        save(profile)
    print("\n".join(profile.get("tier1_services") or ["(none pinned: tier 1 comes from your resume scan)"]))


def _add_open_item(items: list[OpenItem], text: str | None) -> None:
    if not text:
        raise ToolError("open add needs the text of the item")
    items.append({"id": max([item["id"] for item in items] + [0]) + 1, "text": text, "status": "open"})
    common.save_json(OPEN_ITEMS_FILE, items)


def _finish_open_item(items: list[OpenItem], item_id: str | None) -> None:
    match = [item for item in items if str(item["id"]) == item_id]
    if not match:
        raise ToolError(f"No open item {item_id}")
    match[0]["status"] = "done"
    common.save_json(OPEN_ITEMS_FILE, items)


def cmd_open(args: argparse.Namespace) -> None:
    """List open items, or add one / mark one done."""
    items: list[OpenItem] = common.load_json(OPEN_ITEMS_FILE, [])
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
    sub.add_parser("companies").set_defaults(fn=cmd_companies)
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
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
