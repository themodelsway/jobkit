"""The user's curation of the resume data, edited with commands (`process-resumes curate ...`).

Curation survives rebuilds: certifications and education to keep, skill merge/drop/group rules, tag-only
skills, extra skills, figures known to be wrong, bullet themes, ignored fragments and summary angles.
"""
from __future__ import annotations

import argparse
from typing import Any, Final, NamedTuple

from jobkit.base import ToolError
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables


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
        items[values[0]] = values[1]
    elif spec.shape == "map-list":
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


def cmd_curate(args: argparse.Namespace) -> None:
    """List, add or remove curation entries."""
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
        add_entry(spec, items, args.values, args)
        done = f"Added {args.kind}: {' '.join(args.values)}."
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
    listing = actions.add_parser("list")
    listing.add_argument("kind", nargs="?", choices=KINDS)
    for name in ("add", "rm"):
        action = actions.add_parser(name)
        action.add_argument("kind", choices=KINDS)
        action.add_argument("values", nargs="+", metavar="VALUE")
    actions.choices["add"].add_argument("--issued", help="certification: issue date YYYY-MM")
    actions.choices["add"].add_argument("--expires", help="certification: expiry date YYYY-MM")
    curate.set_defaults(fn=cmd_curate)
