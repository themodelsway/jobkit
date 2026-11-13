"""The level bands: the built-in five plus the user's own, read from `profile/match-bands.json` in the home folder.

The file is a JSON object {band name: {category: weight}} with a weight for every category. A name that is
also a built-in band replaces its weights. The file is validated on every read.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from jk import common
from jk.resumes import match_engine as me


def bands_file() -> Path:
    """Where the user's own bands live (the file need not exist)."""
    return common.home() / "profile" / "match-bands.json"


def load_bands() -> tuple[dict[str, dict[str, Decimal]], str]:
    """(every band by name, a fingerprint of the user's file or "" without one).

    Raises:
        ToolError: the file is not valid JSON or a band in it is invalid (the message names the file).
    """
    bands = {name: dict(weights) for name, weights in me.BANDS.items()}
    path = bands_file()
    if not path.is_file():
        return bands, ""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise common.ToolError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise common.ToolError(f"{path}: expected an object of band names")
    for name, weights in data.items():
        if not isinstance(weights, dict):
            raise common.ToolError(f"{path}: band {name!r} must be an object of category weights")
        try:
            bands[str(name)] = me.validate_band(str(name), weights)
        except ValueError as exc:
            raise common.ToolError(f"{path}: {exc}") from exc
    return bands, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
