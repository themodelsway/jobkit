"""The user's curation of the resume data, edited with commands (`process-resumes curate ...`).

Curation survives rebuilds: certifications and education to keep, skill merge/drop/group rules, tag-only
skills, extra skills, figures known to be wrong, shorter wordings the user approved, bullet themes, ignored fragments
and summary angles.
"""
from __future__ import annotations

import argparse
import shlex
from typing import Any, Final, NamedTuple

from jk import common
from jk.base import ToolError
from jk.resumes import lines as line_rules
from jk.resumes import resume_data as rd
from jk.resumes import tables


class Spec(NamedTuple):
    """Where one curation kind lives and how its entries are shaped."""

    file: str
    key: str
    shape: str          # list | certification | map | map-list | extra-skill
    usage: str


SPECS: Final[dict[str, Spec]] = {
    "certification": Spec("curated", "certifications", "certification", "NAME [--issued YYYY-MM] [--expires YYYY-MM]"),
    "education": Spec("curated", "education", "list", "TEXT"),
    "wrong-metric": Spec("curated", "review_if_metric_matches", "list", "FIGURE   (bullets with it need review)"),
    "skill-merge": Spec("curated", "skill_merge", "map", "FROM TO   (spell FROM as TO)"),
    "skill-drop": Spec("curated", "skill_drop", "list", "NAME   (not a skill)"),
    "tag-only": Spec("curated", "tag_only", "list", "NAME   (a tag, not a skill)"),
    "skill-group": Spec("curated", "skill_group", "map", "SKILL GROUP"),
    "extra-skill": Spec("curated", "extra_skills", "extra-skill", "GROUP NAME [ALIAS ...]"),
    "short-wording": Spec("curated", "short_wording", "map", f"BULLET_ID TEXT   (the user's approved wording, at most {rd.LINE_LIMIT} characters)"),
    "theme": Spec("themes", "themes", "map-list", "BULLET_ID THEME [THEME ...]"),
    "ignore": Spec("themes", "ignore", "list", "BULLET_ID   (a fragment, not a bullet)"),
    "summary-angle": Spec("themes", "summary_angles", "map-list", "SUMMARY_ID ANGLE [ANGLE ...]"),
}
KINDS: Final[tuple[str, ...]] = tuple(SPECS)


def load(spec: Spec) -> dict[str, Any]:
    """The whole curation file this kind lives in."""
    return rd.load_curated() if spec.file == "curated" else rd.load_themes_file()


def container(data: dict[str, Any], spec: Spec) -> Any:
    """The list or dict of this kind inside the file (created empty when missing)."""
    return data.setdefault(spec.key, {} if spec.shape in ("map", "map-list", "extra-skill") else [])


def describe(spec: Spec, entry: Any) -> str:
    """One entry as a line of text."""
    if spec.shape == "certification":
        return f"{entry['name']}  (issued {entry.get('issued') or '-'}, expires {entry.get('expires') or '-'})"
    return str(entry)


def lines(kind: str) -> list[str]:
    """Every entry of a kind as text lines."""
    spec = SPECS[kind]
    items = container(load(spec), spec)
    if spec.shape in ("map", "map-list"):
        return [f"{key} -> {', '.join(value) if isinstance(value, list) else value}" for key, value in items.items()]
    if spec.shape == "extra-skill":
        return [f"{group}: " + ", ".join(s["name"] for s in skills) for group, skills in items.items()]
    return [describe(spec, entry) for entry in items]


def add_entry(spec: Spec, items: Any, values: list[str], options: argparse.Namespace) -> None:
    """Add (or replace) one entry in the container."""
    need = {"map": 2, "list": 1, "certification": 1}.get(spec.shape, 2)
    if len(values) < need or (spec.shape in ("map", "list", "certification") and len(values) != need):
        raise ToolError(f"usage: curate add {spec.key} {spec.usage}")
    if spec.shape == "list":
        if values[0] not in items:
            items.append(values[0])
    elif spec.shape == "certification":
        items[:] = [c for c in items if c["name"] != values[0]]
        items.append({"name": values[0], "issued": options.issued, "expires": options.expires})
    elif spec.shape == "map":
        if spec.key == "short_wording":
            line_rules.require_acceptable(values[0], values[1])
        items[values[0]] = values[1]
    elif spec.shape == "map-list":
        if spec.key == "summary_angles":
            bad = [v for v in values[1:] if v not in rd.SUMMARY_ANGLES]
            if bad:
                raise ToolError(f"Unknown summary angle {', '.join(bad)}. Use only: {', '.join(rd.SUMMARY_ANGLES)}.")
        items[values[0]] = values[1:]
    else:
        group = items.setdefault(values[0], [])
        group[:] = [s for s in group if s["name"].lower() != values[1].lower()]
        group.append({"name": values[1], "aliases": values[2:]})


def remove_entry(spec: Spec, items: Any, keys: list[str]) -> bool:
    """Remove one entry; False when there was nothing to remove."""
    key = keys[0]
    if spec.shape == "list":
        found = key in items
        items[:] = [e for e in items if e != key]
    elif spec.shape == "certification":
        found = any(c["name"] == key for c in items)
        items[:] = [c for c in items if c["name"] != key]
    elif spec.shape == "extra-skill" and len(keys) > 1:
        group = items.get(key, [])
        found = any(s["name"].lower() == keys[1].lower() for s in group)
        group[:] = [s for s in group if s["name"].lower() != keys[1].lower()]
        if not group:
            items.pop(key, None)
    else:
        found = items.pop(key, None) is not None
    return found


def unknown_theme_note(spec: Spec, rows: list[list[str]]) -> str:
    """A warning for themes no tool acts on (they are kept, but drive no questions and no matching)."""
    if spec.key != "themes":
        return ""
    other = sorted({v for row in rows for v in row[1:] if v not in rd.KNOWN_THEMES})
    if not other:
        return ""
    which = f"{other[0]} is not a theme" if len(other) == 1 else f"{', '.join(other)} are not themes"
    return (f" Note: {which} the tools use, so they add no lead questions, typical questions "
            "or matching. Run `curate themes` for the ones that do.")


def print_themes() -> None:
    """The themes and summary angles the tools act on."""
    print("Themes: " + ", ".join(rd.KNOWN_THEMES))
    print("Summary angles: " + ", ".join(rd.SUMMARY_ANGLES))


def batch_entries(values: list[str]) -> list[list[str]]:
    """The entries to add: the one given, or one per line of standard input when the only value is `-`
    (quotes group words, `#` starts a comment)."""
    if values != ["-"]:
        return [values]
    rows: list[list[str]] = []
    for number, line in enumerate(common.read_text_arg("-").splitlines(), 1):
        try:
            row = shlex.split(line, comments=True)
        except ValueError as error:
            raise ToolError(f"Line {number} of the entries: {error} (quote a name that holds `#` or spaces, "
                            "and close every quote).") from error
        if row:
            rows.append(row)
    if not rows:
        raise ToolError("Standard input had no entries.")
    return rows


def cmd_curate(args: argparse.Namespace) -> None:
    """List, add or remove curation entries."""
    if args.action == "themes":
        print_themes()
        return
    if args.action == "list":
        for kind in [args.kind] if args.kind else KINDS:
            rows = lines(kind)
            print(f"{kind}: {len(rows)}")
            for row in rows:
                print(f"  {row}")
        return
    spec = SPECS[args.kind]
    data = load(spec)
    items = container(data, spec)
    if args.action == "add":
        rows = batch_entries(args.values)
        for row in rows:
            add_entry(spec, items, row, args)
        done = f"Added {len(rows)} {args.kind} entries." if len(rows) > 1 else f"Added {args.kind}: {' '.join(rows[0])}."
        done += unknown_theme_note(spec, rows)
        if spec.key in ("certifications", "education"):
            done += f" Once there is any entry, your {spec.key} list replaces the list parsed from your resumes."
    else:
        if not remove_entry(spec, items, args.values):
            raise ToolError(f"No {args.kind} entry {' '.join(args.values)}. Run `curate list {args.kind}`.")
        done = f"Removed {args.kind}: {' '.join(args.values)}."
    tables.save_curation(spec.file, data)
    print(f"{done} Run `process-resumes` to apply it.")


def add_parser(sub: Any) -> None:
    """Register `curate list|add|rm` on a subparsers action."""
    curate = sub.add_parser("curate", help="list, add or remove curation entries")
    actions = curate.add_subparsers(dest="action", required=True)
    actions.add_parser("themes", help="list the themes and summary angles the tools act on")
    listing = actions.add_parser("list")
    listing.add_argument("kind", nargs="?", choices=KINDS)
    for name in ("add", "rm"):
        action = actions.add_parser(name)
        action.add_argument("kind", choices=KINDS)
        action.add_argument("values", nargs="+", metavar="VALUE")
    actions.choices["add"].add_argument("--issued", help="certification: issue date YYYY-MM")
    actions.choices["add"].add_argument("--expires", help="certification: expiry date YYYY-MM")
    curate.set_defaults(fn=cmd_curate)
