"""Stored match scores in the database (see `jobkit.resumes.tables` for the approach).

One row per finished result: the whole result as JSON in `body`, a few real columns for listing and pruning.
A result is kept under a key made from the posting, the resume data and the rubric and weights versions, so
the same inputs find it again; entries not used for `RETENTION_DAYS` days are removed when a run finishes.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Final

from jobkit import common, store

RETENTION_DAYS: Final[int] = 90
Record = dict[str, Any]


def save_result(key: str, body: Record) -> None:
    """Store a result under its key (a result stored before keeps its created date)."""
    stamp = common.now()
    with store.transaction() as conn:
        conn.execute("INSERT INTO match_result(key, created, last_used, body) VALUES(?,?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET last_used=excluded.last_used, body=excluded.body",
                     (key, stamp, stamp, store.dump(body)))


def get_result(key: str, touch: bool = False) -> Record | None:
    """The stored result for a key (None when there is none); with `touch` its last-used date is renewed."""
    with store.transaction(write=touch) as conn:
        row = conn.execute("SELECT body FROM match_result WHERE key=?", (key,)).fetchone()
        if row is not None and touch:
            conn.execute("UPDATE match_result SET last_used=? WHERE key=?", (common.now(), key))
    return None if row is None else json.loads(row["body"])


def get_latest(base: str, touch: bool = False) -> Record | None:
    """The newest stored result whose key is `base` or `base-<variant>` (None when there is none)."""
    with store.transaction(write=touch) as conn:
        row = conn.execute("SELECT key, body FROM match_result WHERE key=? OR key LIKE ? ORDER BY created DESC, key "
                           "LIMIT 1", (base, base + "-%")).fetchone()
        if row is not None and touch:
            conn.execute("UPDATE match_result SET last_used=? WHERE key=?", (common.now(), row["key"]))
    return None if row is None else json.loads(row["body"])


def list_results() -> list[Record]:
    """Stored results, newest first: key, created, last used, label, band and the two scores."""
    with store.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT key, created, last_used, COALESCE(json_extract(body, '$.label'), '') AS label, "
            "json_extract(body, '$.band') AS band, json_extract(body, '$.score.lower') AS lower, "
            "json_extract(body, '$.score.upper') AS upper FROM match_result ORDER BY created DESC, key").fetchall()
    return [dict(row) for row in rows]


def prune(days: int = RETENTION_DAYS) -> int:
    """Remove entries not used for more than `days` days; returns how many were removed."""
    cutoff = (datetime.fromisoformat(common.now()) - timedelta(days=days)).isoformat(timespec="seconds")
    with store.transaction() as conn:
        return conn.execute("DELETE FROM match_result WHERE last_used < ?", (cutoff,)).rowcount


def load_results() -> dict[str, Record]:
    """Every stored result for export: {key: {created, last_used, body}}, with the versions inside the body."""
    with store.transaction(write=False) as conn:
        rows = conn.execute("SELECT key, created, last_used, body FROM match_result ORDER BY key").fetchall()
    return {r["key"]: {"created": r["created"], "last_used": r["last_used"], "body": json.loads(r["body"])}
            for r in rows}


def save_results(data: dict[str, Record]) -> None:
    """Replace the stored results with `data` (the shape `load_results` returns)."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM match_result")
        for key, entry in data.items():
            conn.execute("INSERT INTO match_result(key, created, last_used, body) VALUES(?,?,?,?)",
                         (key, entry["created"], entry["last_used"], store.dump(entry["body"])))
