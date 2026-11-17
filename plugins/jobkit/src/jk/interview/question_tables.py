"""Store role questions, dated research outcomes and shared practice progress."""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Final, NotRequired, TypedDict

from jk import store
from jk.base import ToolError
from jk.interview.practice_tables import check_confidence

FIELDS: Final = ("id", "source", "link", "label", "pulled")
ID_PREFIX: Final = "rq:"
CITED_SOURCES: Final = ("research", "company")
NOT_RESEARCHED: Final = "not researched"
FOUND: Final = "found"
NONE_FOUND: Final = "none found"


class Question(TypedDict):
    """One question with its source and, when applicable, its evidence."""

    id: str
    source: str
    link: str | None
    label: str
    pulled: str | None
    question: str
    quote: NotRequired[str]
    vetted: NotRequired[bool]
    bullet: NotRequired[str]
    requirement: NotRequired[str]


class RoleResearch(TypedDict):
    """One role and its questions, with the latest research outcome."""

    role_key: str
    role: str
    outcome: str
    researched: str | None
    questions: list[Question]


class Progress(TypedDict):
    """Current question confidence and the date it was last practiced."""

    confidence: int
    last_drilled: str | None


def key_of(role: str) -> str:
    """Compare role names case-insensitively and normalize whitespace."""
    return " ".join(role.split()).casefold()


def load_roles(role: str | None = None) -> list[RoleResearch]:
    """Read roles and ordered questions, optionally for one role."""
    clause, params = (" WHERE role_key=?", (key_of(role),)) if role is not None else ("", ())
    with store.transaction(write=False) as conn:
        rows = conn.execute("SELECT role_key, role, outcome, researched FROM role_research" + clause
                            + " ORDER BY role_key", params)
        return [RoleResearch(role_key=row["role_key"], role=row["role"], outcome=row["outcome"],
                             researched=row["researched"], questions=store.records(
                                 conn, "SELECT id, source, link, label, pulled, body FROM role_question "
                                 "WHERE role_key=? ORDER BY position", (row["role_key"],), FIELDS))
                for row in rows]


def find(item: str) -> Question | None:
    """Read one question by its full ID."""
    with store.transaction(write=False) as conn:
        rows = store.records(conn, "SELECT id, source, link, label, pulled, body FROM role_question WHERE id=?",
                             (item,), FIELDS)
    return rows[0] if rows else None


def load_progress() -> dict[str, Progress]:
    """Read practice progress by question ID."""
    with store.transaction(write=False) as conn:
        return {row["question_id"]: json.loads(row["body"])
                for row in conn.execute("SELECT question_id, body FROM question_progress")}


def set_progress(item: str, entry: Progress) -> None:
    """Store one question's confidence and date."""
    check_confidence(entry)
    with store.transaction() as conn:
        if find(item) is None:
            raise ToolError(f"Unknown role question {item}. Use questions list.")
        conn.execute("INSERT INTO question_progress(question_id, body) VALUES(?,?) "
                     "ON CONFLICT(question_id) DO UPDATE SET body=excluded.body", (item, store.dump(entry)))


def save_questions(role: str, questions: Sequence[Question]) -> None:
    """Append new questions or update existing IDs in place, keeping practice history."""
    key = key_of(role)
    with store.transaction() as conn:
        conn.execute("INSERT INTO role_research VALUES(?,?,?,NULL) ON CONFLICT(role_key) DO NOTHING",
                     (key, " ".join(role.split()), NOT_RESEARCHED))
        position = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM role_question WHERE role_key=?",
                                (key,)).fetchone()[0]
        for offset, question in enumerate(questions, position):
            (item, source, link, label, pulled), body = store.split(question, FIELDS)
            collision = conn.execute("SELECT id FROM story WHERE id=? UNION ALL SELECT id FROM card WHERE id=? "
                                     "UNION ALL SELECT id FROM lead_question WHERE id=? "
                                     "UNION ALL SELECT item FROM session_log WHERE item=? AND kind!='question' LIMIT 1",
                                     (item, item, item, item)).fetchone()
            if collision:
                raise ToolError(f"Question id {item} is already used by another practice item; choose another local id.")
            conn.execute("INSERT INTO role_question VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE "
                         "SET source=excluded.source, link=excluded.link, label=excluded.label, pulled=excluded.pulled, "
                         "body=excluded.body", (item, key, offset, source, link, label, pulled, body))
        refresh_outcome(role)


def refresh_outcome(role: str) -> None:
    """Reflect the remaining cited questions in the role's research status."""
    key = key_of(role)
    with store.transaction() as conn:
        latest = conn.execute("SELECT MAX(pulled) FROM role_question WHERE role_key=?", (key,)).fetchone()[0]
        if latest:
            conn.execute("UPDATE role_research SET outcome=?, researched=? WHERE role_key=?",
                         (FOUND, latest, key))
        else:
            conn.execute("UPDATE role_research SET outcome=?, researched=NULL WHERE role_key=? AND outcome=?",
                         (NOT_RESEARCHED, key, FOUND))


def record_none_found(role: str, today: date) -> None:
    """Date an unsuccessful search while keeping locally written questions."""
    with store.transaction() as conn:
        key = key_of(role)
        if conn.execute("SELECT 1 FROM role_question WHERE role_key=? AND pulled IS NOT NULL", (key,)).fetchone():
            raise ToolError("This role still has cited questions. Review those questions before recording none found.")
        conn.execute("INSERT INTO role_research VALUES(?,?,?,?) ON CONFLICT(role_key) DO UPDATE "
                     "SET outcome=excluded.outcome, researched=excluded.researched",
                     (key, " ".join(role.split()), NONE_FOUND, today.isoformat()))


def remove_question(item: str) -> None:
    """Remove a question and its active progress while keeping any session log entries."""
    with store.transaction() as conn:
        row = conn.execute("SELECT role_key, pulled FROM role_question WHERE id=?", (item,)).fetchone()
        if row is None:
            raise ToolError(f"Unknown role question {item}. Use questions list.")
        conn.execute("DELETE FROM role_question WHERE id=?", (item,))
        if row["pulled"] is not None:
            refresh_outcome(row["role_key"])
        conn.execute("DELETE FROM role_research WHERE role_key=? AND outcome=? "
                     "AND NOT EXISTS (SELECT 1 FROM role_question WHERE role_key=?)",
                     (row["role_key"], NOT_RESEARCHED, row["role_key"]))
