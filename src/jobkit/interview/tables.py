"""Interview data in the database: sessions, architecture cards, tracks, stories, engagements, leadership.

Each function takes or returns the same dicts the tools used to keep in JSON files, so the tool code is
unchanged; this module is the only place that knows the tables. Record tables keep the record as JSON in
`body` and copy the key, link and queried fields into columns, always written from the body here.
Every change runs inside the caller's transaction (`store.transaction`).
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from jobkit import store
from jobkit.base import ToolError

Record = dict[str, Any]


def dump(value: Any) -> str:
    """Compact, readable JSON for a body column."""
    return json.dumps(value, ensure_ascii=False)


def _bodies(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    """The decoded `body` of every row the query returns."""
    return [json.loads(row[0]) for row in conn.execute(sql, params)]


def meta_get(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    """A value from the meta table, or `default`."""
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return default if row is None else json.loads(row[0])


def meta_put(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Store a value in the meta table."""
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, dump(value)))


def _sync(conn: sqlite3.Connection, table: str, key: str, keep: Iterable[str]) -> None:
    """Delete the rows of `table` whose `key` is not in `keep` (rows that were written are upserts)."""
    keep = list(keep)
    marks = ",".join("?" for _ in keep)
    conn.execute(f"DELETE FROM {table} WHERE {key} NOT IN ({marks})" if keep else f"DELETE FROM {table}", keep)


# ---------------------------------------------------------------- sessions

def session_exists(sid: str) -> bool:
    """True when a session with this id exists."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM session WHERE id=?", (sid,)).fetchone() is not None


def load_session(sid: str) -> Record | None:
    """One session with its queue and full answer log, or None."""
    with store.transaction(write=False) as conn:
        row = conn.execute("SELECT body FROM session WHERE id=?", (sid,)).fetchone()
        if row is None:
            return None
        session = json.loads(row[0])
        session["queue"] = _bodies(conn, "SELECT body FROM session_item WHERE session_id=? ORDER BY position", (sid,))
        session["log"] = _bodies(conn, "SELECT body FROM session_log WHERE session_id=? ORDER BY seq", (sid,))
    return session


def session_ids() -> list[str]:
    """Ids of every stored session, oldest id first."""
    with store.transaction(write=False) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM session ORDER BY id")]


def all_sessions() -> list[Record]:
    """Every session, in id order."""
    return [s for s in (load_session(sid) for sid in session_ids()) if s is not None]


def save_session(session: Mapping[str, Any]) -> None:
    """Store a session. Log entries can only be added: a changed or removed earlier entry is refused.

    Raises:
        ToolError: the log no longer starts with the entries already stored.
    """
    body = {k: v for k, v in session.items() if k not in ("queue", "log")}
    sid = session["id"]
    with store.transaction() as conn:
        conn.execute("INSERT INTO session(id, title, mode, status, created, updated, body) VALUES(?,?,?,?,?,?,?) "
                     "ON CONFLICT(id) DO UPDATE SET title=excluded.title, mode=excluded.mode, status=excluded.status, "
                     "updated=excluded.updated, body=excluded.body",
                     (sid, session["title"], session["mode"], session["status"], session["created"],
                      session["updated"], dump(body)))
        conn.execute("DELETE FROM session_item WHERE session_id=?", (sid,))
        conn.executemany("INSERT INTO session_item(session_id, position, item, kind, body) VALUES(?,?,?,?,?)",
                         [(sid, i, q["id"], q["kind"], dump(q)) for i, q in enumerate(session["queue"])])
        stored = _bodies(conn, "SELECT body FROM session_log WHERE session_id=? ORDER BY seq", (sid,))
        log = list(session["log"])
        if log[:len(stored)] != stored:
            raise ToolError(f"Session {sid}: logged answers can only be added, never changed or removed.")
        conn.executemany(
            "INSERT INTO session_log(session_id, at, item, kind, answered, confidence_after, tutor, quiz, body) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [(sid, e["at"], e["item"], e["kind"], int(bool((e.get("answer") or "").strip())),
              e.get("confidence_after"), int(bool(e.get("tutor"))), int(bool(e.get("quiz"))), dump(e))
             for e in log[len(stored):]])


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


# ---------------------------------------------------------------- architecture

def has_catalog() -> bool:
    """True once `arch init` has stored a catalog."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='arch.catalog'").fetchone() is not None


def load_catalog() -> Record | None:
    """The card catalog (top-level fields plus `cards`), or None before `arch init`."""
    with store.transaction(write=False) as conn:
        head = meta_get(conn, "arch.catalog", None)
        if head is None:
            return None
        head["cards"] = _bodies(conn, "SELECT body FROM card ORDER BY position")
    return head


def save_catalog(catalog: Mapping[str, Any]) -> None:
    """Store the catalog; progress of cards that stay is kept, progress of removed cards goes with them."""
    head = {k: v for k, v in catalog.items() if k != "cards"}
    with store.transaction() as conn:
        meta_put(conn, "arch.catalog", head)
        for position, card in enumerate(catalog["cards"]):
            conn.execute(
                "INSERT INTO card(id, position, track, kind, area, name, tier, body) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET position=excluded.position, track=excluded.track, kind=excluded.kind, "
                "area=excluded.area, name=excluded.name, tier=excluded.tier, body=excluded.body",
                (card["id"], position, card.get("track", "aws"), card["kind"], card.get("area"), card["name"],
                 card.get("tier"), dump(card)))
        _sync(conn, "card", "id", [c["id"] for c in catalog["cards"]])


def load_progress() -> dict[str, Record]:
    """{card id: progress} for every card the user has touched."""
    with store.transaction(write=False) as conn:
        return {row["card_id"]: json.loads(row["body"]) for row in conn.execute("SELECT card_id, body FROM card_progress")}


def save_progress(progress: Mapping[str, Mapping[str, Any]]) -> None:
    """Store progress per card (every id must be a card in the catalog).

    Raises:
        ToolError: an id is not in the catalog.
    """
    with store.transaction() as conn:
        for card_id, entry in progress.items():
            try:
                conn.execute(
                    "INSERT INTO card_progress(card_id, confidence, last_drilled, body) VALUES(?,?,?,?) "
                    "ON CONFLICT(card_id) DO UPDATE SET confidence=excluded.confidence, "
                    "last_drilled=excluded.last_drilled, body=excluded.body",
                    (card_id, entry["confidence"], entry.get("last_drilled"), dump(entry)))
            except sqlite3.IntegrityError as exc:
                raise ToolError(f"Unknown card {card_id}: progress can only be kept for cards in the catalog.") from exc
        _sync(conn, "card_progress", "card_id", list(progress))


def track_names() -> list[str]:
    """Names of the stored custom tracks, sorted."""
    with store.transaction(write=False) as conn:
        return [row[0] for row in conn.execute("SELECT name FROM track ORDER BY name")]


def load_track(name: str) -> Record | None:
    """A custom track's seed, or None."""
    with store.transaction(write=False) as conn:
        row = conn.execute("SELECT body FROM track WHERE name=?", (name,)).fetchone()
    return None if row is None else json.loads(row[0])


def save_track(name: str, seed: Mapping[str, Any]) -> None:
    """Store (or replace) a custom track's seed."""
    with store.transaction() as conn:
        conn.execute("INSERT INTO track(name, body) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                     (name, dump(seed)))


# ---------------------------------------------------------------- stories and engagements

def has_stories() -> bool:
    """True once `prep init` has stored stories."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='prep.stories'").fetchone() is not None


def load_stories() -> Record | None:
    """The stories document (`schema_version` plus `stories`), or None."""
    with store.transaction(write=False) as conn:
        head = meta_get(conn, "prep.stories", None)
        if head is None:
            return None
        head["stories"] = _bodies(conn, "SELECT body FROM story ORDER BY position")
    return head


def save_stories(doc: Mapping[str, Any]) -> None:
    """Store the stories; a story may only link to an engagement that exists when the change commits."""
    head = {k: v for k, v in doc.items() if k != "stories"}
    with store.transaction() as conn:
        meta_put(conn, "prep.stories", head)
        for position, story in enumerate(doc["stories"]):
            conn.execute(
                "INSERT INTO story(id, position, company, theme, status, engagement_id, updated, body) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET position=excluded.position, "
                "company=excluded.company, theme=excluded.theme, status=excluded.status, "
                "engagement_id=excluded.engagement_id, updated=excluded.updated, body=excluded.body",
                (story["id"], position, story.get("company"), story.get("theme"), story["status"],
                 story.get("engagement"), story.get("updated"), dump(story)))
        _sync(conn, "story", "id", [s["id"] for s in doc["stories"]])


def has_engagements() -> bool:
    """True once any engagement document has been stored."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='prep.engagements'").fetchone() is not None


def load_engagements() -> Record:
    """The engagements document (`schema_version` plus `engagements`, each with facts, decisions, people)."""
    with store.transaction(write=False) as conn:
        head = meta_get(conn, "prep.engagements", {})
        engagements = []
        for row in conn.execute("SELECT id, body FROM engagement ORDER BY position").fetchall():
            eng = json.loads(row["body"])
            for field, table in (("facts", "fact"), ("decisions", "decision"), ("people", "person")):
                eng[field] = _bodies(conn, f"SELECT body FROM {table} WHERE engagement_id=? ORDER BY position", (row["id"],))
            engagements.append(eng)
        head["engagements"] = engagements
    return head


def save_engagements(doc: Mapping[str, Any]) -> None:
    """Store the engagements and, for each, its facts, decisions and people."""
    head = {k: v for k, v in doc.items() if k != "engagements"}
    with store.transaction() as conn:
        meta_put(conn, "prep.engagements", head)
        for position, eng in enumerate(doc["engagements"]):
            body = {k: v for k, v in eng.items() if k not in ("facts", "decisions", "people")}
            conn.execute(
                "INSERT INTO engagement(id, position, company, title, updated, body) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET position=excluded.position, company=excluded.company, "
                "title=excluded.title, updated=excluded.updated, body=excluded.body",
                (eng["id"], position, eng.get("company"), eng.get("title"), eng.get("updated"), dump(body)))
            _save_children(conn, eng)
        _sync(conn, "engagement", "id", [e["id"] for e in doc["engagements"]])


def _save_children(conn: sqlite3.Connection, eng: Mapping[str, Any]) -> None:
    """Replace the facts, decisions and people of one engagement."""
    eid = eng["id"]
    for table in ("fact", "decision", "person"):
        conn.execute(f"DELETE FROM {table} WHERE engagement_id=?", (eid,))
    conn.executemany("INSERT INTO fact(engagement_id, id, position, basis, body) VALUES(?,?,?,?,?)",
                     [(eid, f["id"], i, f.get("basis"), dump(f)) for i, f in enumerate(eng.get("facts", []))])
    conn.executemany("INSERT INTO decision(engagement_id, id, position, ownership, body) VALUES(?,?,?,?,?)",
                     [(eid, d["id"], i, d.get("ownership"), dump(d)) for i, d in enumerate(eng.get("decisions", []))])
    conn.executemany("INSERT INTO person(engagement_id, position, body) VALUES(?,?,?)",
                     [(eid, i, dump(p)) for i, p in enumerate(eng.get("people", []))])


def load_themes() -> Record:
    """{theme: {stories, questions}} for the story themes."""
    with store.transaction(write=False) as conn:
        return {row["name"]: json.loads(row["body"]) for row in conn.execute("SELECT name, body FROM theme ORDER BY name")}


def save_themes(themes: Mapping[str, Mapping[str, Any]]) -> None:
    """Store the themes."""
    with store.transaction() as conn:
        for name, entry in themes.items():
            conn.execute("INSERT INTO theme(name, body) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                         (name, dump(entry)))
        _sync(conn, "theme", "name", list(themes))


# ---------------------------------------------------------------- leadership

def has_questions() -> bool:
    """True once `lead init` has stored the question set."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM lead_question LIMIT 1").fetchone() is not None


def load_questions() -> list[Record]:
    """The leadership questions in order."""
    with store.transaction(write=False) as conn:
        return _bodies(conn, "SELECT body FROM lead_question ORDER BY position")


def save_questions(questions: Sequence[Mapping[str, Any]]) -> None:
    """Store the question set; the answers to questions that stay are kept."""
    with store.transaction() as conn:
        for position, q in enumerate(questions):
            conn.execute("INSERT INTO lead_question(id, position, category, body) VALUES(?,?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, category=excluded.category, "
                         "body=excluded.body", (q["id"], position, q["category"], dump(q)))
        _sync(conn, "lead_question", "id", [q["id"] for q in questions])


def load_lead_progress() -> dict[str, Record]:
    """{question id: the user's progress and STAR examples}."""
    with store.transaction(write=False) as conn:
        return {row["question_id"]: json.loads(row["body"])
                for row in conn.execute("SELECT question_id, body FROM lead_progress")}


def save_lead_progress(progress: Mapping[str, Mapping[str, Any]]) -> None:
    """Store progress per question (every id must be a stored question).

    Raises:
        ToolError: an id is not a question.
    """
    with store.transaction() as conn:
        for qid, entry in progress.items():
            try:
                conn.execute("INSERT INTO lead_progress(question_id, confidence, last_drilled, body) VALUES(?,?,?,?) "
                             "ON CONFLICT(question_id) DO UPDATE SET confidence=excluded.confidence, "
                             "last_drilled=excluded.last_drilled, body=excluded.body",
                             (qid, entry["confidence"], entry.get("last_drilled"), dump(entry)))
            except sqlite3.IntegrityError as exc:
                raise ToolError(f"Unknown leadership question {qid}.") from exc
        _sync(conn, "lead_progress", "question_id", list(progress))


def load_company_facts() -> dict[str, Record]:
    """{company id: factual scope (team size, budget, ...)}."""
    with store.transaction(write=False) as conn:
        return {row["company_id"]: json.loads(row["body"])
                for row in conn.execute("SELECT company_id, body FROM lead_company_fact")}


def save_company_facts(facts: Mapping[str, Mapping[str, Any]]) -> None:
    """Store the factual scope per company."""
    with store.transaction() as conn:
        for cid, entry in facts.items():
            conn.execute("INSERT INTO lead_company_fact(company_id, body) VALUES(?,?) "
                         "ON CONFLICT(company_id) DO UPDATE SET body=excluded.body", (cid, dump(entry)))
        _sync(conn, "lead_company_fact", "company_id", list(facts))
