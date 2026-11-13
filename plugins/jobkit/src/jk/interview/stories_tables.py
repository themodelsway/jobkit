"""Stories, engagements (with facts, decisions and people) and story themes in the database.

An engagement, fact, decision or story keeps only its id (and position and link) as columns; the rest of the
record is in `body`. A story's link to its engagement is the `engagement_id` column only. Every change runs
inside the caller's transaction (`store.transaction`).
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from jk import store

Record = dict[str, Any]
CHILDREN = (("facts", "fact"), ("decisions", "decision"), ("people", "person"))


def has_stories() -> bool:
    """True once `prep init` has stored stories."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='prep.stories'").fetchone() is not None


def load_stories() -> Record | None:
    """The stories document (`schema_version` plus `stories`), or None."""
    with store.transaction(write=False) as conn:
        head = store.meta_get(conn, "prep.stories", None)
        if head is None:
            return None
        rows = conn.execute("SELECT id, engagement_id, body FROM story ORDER BY position").fetchall()
        head["stories"] = [store.merge({"id": r["id"], "engagement": r["engagement_id"]}, r["body"]) for r in rows]
    return head


def replace_stories(doc: Mapping[str, Any]) -> None:
    """Store the stories; a story may only link to an engagement that exists when the change commits."""
    head = {k: v for k, v in doc.items() if k != "stories"}
    with store.transaction() as conn:
        store.meta_put(conn, "prep.stories", head)
        for position, story in enumerate(doc["stories"]):
            (sid, engagement), body = store.split(story, ("id", "engagement"))
            conn.execute("INSERT INTO story(id, position, engagement_id, body) VALUES(?,?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, "
                         "engagement_id=excluded.engagement_id, body=excluded.body", (sid, position, engagement, body))
        store.keep_only(conn, "story", "id", [s["id"] for s in doc["stories"]])


def has_engagements() -> bool:
    """True once any engagement document has been stored."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='prep.engagements'").fetchone() is not None


def load_engagements() -> Record:
    """The engagements document (`schema_version` plus `engagements`, each with facts, decisions, people)."""
    with store.transaction(write=False) as conn:
        head = store.meta_get(conn, "prep.engagements", {})
        engagements = []
        for eng in store.records(conn, "SELECT id, body FROM engagement ORDER BY position", (), ("id",)):
            for field, table in CHILDREN:
                owned = () if table == "person" else ("id",)
                columns = "body" if table == "person" else "id, body"
                eng[field] = store.records(
                    conn, f"SELECT {columns} FROM {table} WHERE engagement_id=? ORDER BY position", (eng["id"],), owned)
            engagements.append(eng)
        head["engagements"] = engagements
    return head


def replace_engagements(doc: Mapping[str, Any]) -> None:
    """Store the engagements and, for each, its facts, decisions and people."""
    head = {k: v for k, v in doc.items() if k != "engagements"}
    with store.transaction() as conn:
        store.meta_put(conn, "prep.engagements", head)
        for position, eng in enumerate(doc["engagements"]):
            (eid,), body = store.split({k: v for k, v in eng.items() if k not in dict(CHILDREN)}, ("id",))
            conn.execute("INSERT INTO engagement(id, position, body) VALUES(?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, body=excluded.body",
                         (eid, position, body))
            _save_children(conn, eng)
        store.keep_only(conn, "engagement", "id", [e["id"] for e in doc["engagements"]])


def _save_children(conn: sqlite3.Connection, eng: Mapping[str, Any]) -> None:
    """Replace the facts, decisions and people of one engagement."""
    eid = eng["id"]
    for _, table in CHILDREN:
        conn.execute(f"DELETE FROM {table} WHERE engagement_id=?", (eid,))
    for field, table in CHILDREN[:2]:
        rows = []
        for position, item in enumerate(eng.get(field, [])):
            (item_id,), body = store.split(item, ("id",))
            rows.append((eid, item_id, position, body))
        conn.executemany(f"INSERT INTO {table}(engagement_id, id, position, body) VALUES(?,?,?,?)", rows)
    conn.executemany("INSERT INTO person(engagement_id, position, body) VALUES(?,?,?)",
                     [(eid, i, store.dump(p)) for i, p in enumerate(eng.get("people", []))])


def load_themes() -> Record:
    """{theme: {stories, questions}} for the story themes."""
    with store.transaction(write=False) as conn:
        return {row["name"]: json.loads(row["body"]) for row in conn.execute("SELECT name, body FROM theme ORDER BY name")}


def replace_themes(themes: Mapping[str, Mapping[str, Any]]) -> None:
    """Store the themes."""
    with store.transaction() as conn:
        for name, entry in themes.items():
            conn.execute("INSERT INTO theme(name, body) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                         (name, store.dump(entry)))
        store.keep_only(conn, "theme", "name", list(themes))
