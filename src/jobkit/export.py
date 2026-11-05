"""Readable copies of the stored data: `jobkit export` (JSON or Markdown, to stdout or a folder)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jobkit import records
from jobkit.base import ToolError

FORMATS = ("json", "md")


def to_json(data: Any) -> str:
    """Indented JSON with non-ASCII text kept readable."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _lines(value: Any, depth: int) -> list[str]:
    """Markdown lines for a nested value: dicts and lists become bullets, text stays whole."""
    pad = "  " * depth
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                out += [f"{pad}- **{key}**:", *_lines(item, depth + 1)]
            else:
                out.append(f"{pad}- **{key}**: {_scalar(item)}")
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, (dict, list)):
                out += [f"{pad}-", *_lines(item, depth + 1)]
            else:
                out.append(f"{pad}- {_scalar(item)}")
        return out
    return [f"{pad}{_scalar(value)}"]


def _scalar(value: Any) -> str:
    """One value on one line (multi-line text is indented under its bullet)."""
    if value is None:
        return "(none)"
    return str(value).replace("\n", "\n    ")


def to_markdown(name: str, data: Any) -> str:
    """A Markdown view of one kind."""
    body = "\n".join(_lines(data, 0)) if not records.blank(data) else "(nothing stored)"
    return f"# {name}\n\n{body}\n"


def render(name: str, data: Any, fmt: str) -> str:
    """One kind as text in the chosen format."""
    return to_json(data) if fmt == "json" else to_markdown(name, data)


def export_text(fmt: str, only: str | None) -> str:
    """Everything (or one kind) as one text: JSON is one object keyed by kind; Markdown is one document."""
    kinds = [records.kind(only)] if only else list(records.KINDS)
    data = {k.name: k.export() for k in kinds}
    if fmt == "json":
        return to_json(data if not only else data[only])
    return "\n".join(to_markdown(name, value) for name, value in data.items())


def export_to_folder(folder: Path, fmt: str, only: str | None) -> list[Path]:
    """Write one file per kind into `folder`; returns the files written."""
    kinds = [records.kind(only)] if only else list(records.KINDS)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for entry in kinds:
        path = folder / f"{entry.name}.{fmt}"
        path.write_text(render(entry.name, entry.export(), fmt), encoding="utf-8")
        written.append(path)
    return written


def check_format(fmt: str) -> str:
    """The format, or a ToolError naming the choices."""
    if fmt not in FORMATS:
        raise ToolError(f"--format must be one of {', '.join(FORMATS)}")
    return fmt
