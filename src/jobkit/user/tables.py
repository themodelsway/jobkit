"""The user's settings, the employers found in the resumes, and open items, in the database."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from jobkit import store
from jobkit.interview.tables import dump

Record = dict[str, Any]


def load_settings() -> Record:
    """{setting: value} (resume_root, resume_dirs, name, tier1_services, ...); empty before `profile init`."""
    with store.transaction(write=False) as conn:
        return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM setting ORDER BY rowid")}


def has_settings() -> bool:
    """True once `profile init` has stored the settings."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM setting LIMIT 1").fetchone() is not None


def save_settings(settings: Mapping[str, Any]) -> None:
    """Replace the settings."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM setting")
        conn.executemany("INSERT INTO setting(key, value) VALUES(?,?)", [(k, dump(v)) for k, v in settings.items()])


def has_employers() -> bool:
    """True once a scan has stored employers."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM employer LIMIT 1").fetchone() is not None


def load_employers() -> dict[str, Record]:
    """{employer id: {name, regex, ...}} in stored order."""
    with store.transaction(write=False) as conn:
        return {r["id"]: json.loads(r["body"]) for r in conn.execute("SELECT id, body FROM employer ORDER BY position")}


def save_employers(employers: Mapping[str, Mapping[str, Any]]) -> None:
    """Replace the employers."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM employer")
        conn.executemany("INSERT INTO employer(id, position, name, body) VALUES(?,?,?,?)",
                         [(i, p, e["name"], dump(e)) for p, (i, e) in enumerate(employers.items())])


def load_open_items() -> list[Record]:
    """Open items and data notes, in id order."""
    with store.transaction(write=False) as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT body FROM open_item ORDER BY id")]


def save_open_items(items: Sequence[Mapping[str, Any]]) -> None:
    """Replace the open items."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM open_item")
        conn.executemany("INSERT INTO open_item(id, status, body) VALUES(?,?,?)",
                         [(i["id"], i.get("status", "open"), dump(i)) for i in items])
