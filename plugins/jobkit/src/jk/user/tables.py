"""The user's settings, the employers found in the resumes, and open items, in the database."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from jk import store

Record = dict[str, Any]


def load_settings() -> Record:
    """{setting: value} (resume_root, resume_dirs, name, tier1_services, ...); empty before `profile init`."""
    with store.transaction(write=False) as conn:
        return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM setting ORDER BY rowid")}


def has_settings() -> bool:
    """True once `profile init` has stored the settings."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM setting LIMIT 1").fetchone() is not None


def replace_settings(settings: Mapping[str, Any]) -> None:
    """Replace the settings."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM setting")
        conn.executemany("INSERT INTO setting(key, value) VALUES(?,?)", [(k, store.dump(v)) for k, v in settings.items()])


def has_employers() -> bool:
    """True once a scan has stored employers."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM employer LIMIT 1").fetchone() is not None


def load_employers() -> dict[str, Record]:
    """{employer id: {name, regex, ...}} in stored order."""
    with store.transaction(write=False) as conn:
        return {r["id"]: json.loads(r["body"]) for r in conn.execute("SELECT id, body FROM employer ORDER BY position")}


def replace_employers(employers: Mapping[str, Mapping[str, Any]]) -> None:
    """Replace the employers."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM employer")
        conn.executemany("INSERT INTO employer(id, position, body) VALUES(?,?,?)",
                         [(i, p, store.dump(e)) for p, (i, e) in enumerate(employers.items())])


def load_open_items() -> list[Record]:
    """Open items and data notes, in id order."""
    with store.transaction(write=False) as conn:
        return store.records(conn, "SELECT id, body FROM open_item ORDER BY id", (), ("id",))


def replace_open_items(items: Sequence[Mapping[str, Any]]) -> None:
    """Replace the open items."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM open_item")
        rows = []
        for item in items:
            (item_id,), body = store.split(item, ("id",))
            rows.append((item_id, body))
        conn.executemany("INSERT INTO open_item(id, body) VALUES(?,?)", rows)


def load_terms() -> list[Record]:
    """The stored terms (text, kind, match, ignored), by text."""
    with store.transaction(write=False) as conn:
        return [dict(r) for r in conn.execute("SELECT text, kind, match, ignored FROM term ORDER BY text COLLATE NOCASE")]


def save_term(text: str, kind: str, match: str, ignored: bool) -> None:
    """Add a term, or replace the one with the same text (any letter case)."""
    with store.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO term(text, kind, match, ignored) VALUES(?,?,?,?)",
                     (text, kind, match, int(ignored)))


def delete_term(text: str) -> bool:
    """Remove a stored term; False when there was none."""
    with store.transaction() as conn:
        return conn.execute("DELETE FROM term WHERE text = ?", (text,)).rowcount > 0
