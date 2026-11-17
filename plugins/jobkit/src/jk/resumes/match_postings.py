"""Postings saved for `match-score`, so the agent hands text over on standard input and writes no file itself.

`extract` saves the posting under `output/match/postings/` in the home folder, named by a short digest of the
normalized posting (the KEY); `check` and `run` read it back with `--key`. Copies unused for `RETENTION_DAYS` days
are removed when a run finishes.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Final

from jk import common
from jk.resumes import match_facts

RETENTION_DAYS: Final[int] = 30
KEY_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{16}")


def folder() -> Path:
    """The folder that holds the saved postings."""
    return common.output_dir() / "match" / "postings"


def save(text: str) -> str:
    """Save the posting text and return its key (saving the same posting again refreshes the copy)."""
    key = match_facts.posting_fingerprint(text)[:16]
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / f"{key}.txt").write_text(text, encoding="utf-8")
    return key


def load(key: str) -> str:
    """The posting saved under a key.

    Raises:
        ToolError: the key is malformed, or no posting was saved under it.
    """
    path = folder() / f"{key}.txt"
    if not KEY_RE.fullmatch(key) or not path.is_file():
        raise common.ToolError(f"No saved posting for key {key!r}. Run `match-score extract --jd -` with the posting "
                               "on standard input to save it and get its key.")
    path.touch()
    return path.read_text(encoding="utf-8")


def prune(days: int = RETENTION_DAYS) -> int:
    """Remove postings not used for more than `days` days; returns how many were removed."""
    cutoff = time.time() - days * 86400
    old = [p for p in folder().glob("*.txt") if p.stat().st_mtime < cutoff] if folder().is_dir() else []
    for path in old:
        path.unlink()
    return len(old)
