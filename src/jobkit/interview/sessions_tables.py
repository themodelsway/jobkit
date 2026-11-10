"""Practice sessions in the database: the queue, the append-only answer log and the evidence read from it.

A session's id, title, mode, status and dates are columns (the listing reads them); everything else of the
session is in `body`. Every change runs inside the caller's transaction (`store.transaction`).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

from jobkit import store
from jobkit.base import ToolError

Record = dict[str, Any]
SESSION_FIELDS = ("id", "title", "mode", "status", "created", "updated")
ITEM_TABLES = {"card": "card", "leader": "lead_question", "story": "story"}   # item kind -> the table holding it


def session_exists(sid: str) -> bool:
    """True when a session with this id exists."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM session WHERE id=?", (sid,)).fetchone() is not None


def load_session(sid: str) -> Record | None:
    """One session with its queue and full answer log, or None."""
    with store.transaction(write=False) as conn:
        found = store.records(conn, "SELECT id, title, mode, status, created, updated, body FROM session WHERE id=?",
                              (sid,), SESSION_FIELDS)
        if not found:
            return None
        session = found[0]
        session["queue"] = [{"id": r["item"], "kind": r["kind"]} for r in conn.execute(
            "SELECT item, kind FROM session_item WHERE session_id=? ORDER BY position", (sid,))]
        session["log"] = store.bodies(conn, "SELECT body FROM session_log WHERE session_id=? ORDER BY seq", (sid,))
    return session


def session_ids() -> list[str]:
    """Ids of every stored session, oldest id first."""
    with store.transaction(write=False) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM session ORDER BY id")]


def all_sessions() -> list[Record]:
    """Every session, in id order."""
    return [s for s in (load_session(sid) for sid in session_ids()) if s is not None]


def _check_items(conn: sqlite3.Connection, pairs: Iterable[tuple[str, str]]) -> None:
    """Fail unless every (kind, id) names an item that exists now.

    Raises:
        ToolError: a kind is not card, leader or story, or the item is not in the data.
    """
    for kind, item in sorted(set(pairs)):
        table = ITEM_TABLES.get(kind)
        if table is None:
            raise ToolError(f"Item {item}: unknown kind {kind!r}; use card, leader or story.")
        if conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (item,)).fetchone() is None:
            raise ToolError(f"Unknown {kind} {item}: it is not in the data, so it cannot be queued or answered.")


def _check_session(conn: sqlite3.Connection, session: Mapping[str, Any]) -> list[Record]:
    """Refuse a change an existing session may not have; return the log entries already stored.

    Only entries that are new are checked against the data, so a session whose item was removed stays savable.

    Raises:
        ToolError: the creation time differs, the log no longer starts with the stored entries, or a new entry
            names an item that does not exist.
    """
    sid = session["id"]
    row = conn.execute("SELECT created FROM session WHERE id=?", (sid,)).fetchone()
    if row is not None and row[0] != session["created"]:
        raise ToolError(f"Session {sid}: the creation time of a session cannot be changed.")
    stored = store.bodies(conn, "SELECT body FROM session_log WHERE session_id=? ORDER BY seq", (sid,))
    log = list(session["log"])
    if log[:len(stored)] != stored:
        raise ToolError(f"Session {sid}: logged answers can only be added, never changed or removed.")
    queued = {(r["kind"], r["item"]) for r in conn.execute("SELECT kind, item FROM session_item WHERE session_id=?", (sid,))}
    _check_items(conn, [(q["kind"], q["id"]) for q in session["queue"] if (q["kind"], q["id"]) not in queued]
                 + [(e["kind"], e["item"]) for e in log[len(stored):]])
    return stored


def save_session(session: Mapping[str, Any]) -> None:
    """Store a session. Log entries can only be added: a changed or removed earlier entry is refused.

    Everything is checked before anything is written.

    Raises:
        ToolError: the creation time changed, the log no longer starts with the entries already stored, or a new
            entry names an item that does not exist.
    """
    fields, body = store.split({k: v for k, v in session.items() if k not in ("queue", "log")}, SESSION_FIELDS)
    sid = session["id"]
    with store.transaction() as conn:
        stored = _check_session(conn, session)
        conn.execute("INSERT INTO session(id, title, mode, status, created, updated, body) VALUES(?,?,?,?,?,?,?) "
                     "ON CONFLICT(id) DO UPDATE SET title=excluded.title, mode=excluded.mode, status=excluded.status, "
                     "updated=excluded.updated, body=excluded.body", (*fields, body))
        conn.execute("DELETE FROM session_item WHERE session_id=?", (sid,))
        conn.executemany("INSERT INTO session_item(session_id, position, item, kind) VALUES(?,?,?,?)",
                         [(sid, i, q["id"], q["kind"]) for i, q in enumerate(session["queue"])])
        conn.executemany(
            "INSERT INTO session_log(session_id, at, item, kind, answered, confidence_after, tutor, quiz, body) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [(sid, e["at"], e["item"], e["kind"], int(bool((e.get("answer") or "").strip())),
              e.get("confidence_after"), int(bool(e.get("tutor"))), int(bool(e.get("quiz"))), store.dump(e))
             for e in list(session["log"])[len(stored):]])


def session_rows() -> list[Record]:
    """One summary row per session, newest update first (for `sessions list`)."""
    with store.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT s.id, s.title, s.mode, s.status, s.created, s.updated, "
            "(SELECT COUNT(DISTINCT item) FROM session_log WHERE session_id=s.id) AS logged, "
            "(SELECT COUNT(*) FROM session_item WHERE session_id=s.id) AS total "
            "FROM session s ORDER BY s.updated DESC, s.id")
        return [dict(row) for row in rows]


def evidence() -> dict[str, dict[str, set[str]]]:
    """item id -> dates (YYYY-MM-DD) it was answered and graded solid, counting only real practice.

    An entry counts when its answer is not empty, and a tutor lesson counts only when its quiz was passed.
    """
    out: dict[str, dict[str, set[str]]] = {}
    with store.transaction(write=False) as conn:
        for row in conn.execute("SELECT item, substr(at, 1, 10) AS day, confidence_after FROM session_log "
                                "WHERE answered=1 AND NOT (tutor=1 AND quiz=0)"):
            entry = out.setdefault(row["item"], {"graded2": set(), "answered": set()})
            entry["answered"].add(row["day"])
            if row["confidence_after"] == 2:
                entry["graded2"].add(row["day"])
    return out
