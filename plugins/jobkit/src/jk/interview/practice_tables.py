"""Architecture cards, the user's progress on them, custom tracks, and leadership questions in the database.

A card or question keeps only its id and position as columns; the rest of the record is in `body`. Progress
rows keep the whole entry in `body`. Every change runs inside the caller's transaction (`store.transaction`).
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from jk import store
from jk.base import ToolError

Record = dict[str, Any]


def has_catalog() -> bool:
    """True once `arch init` has stored a catalog."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key='arch.catalog'").fetchone() is not None


def load_catalog() -> Record | None:
    """The card catalog (top-level fields plus `cards`), or None before `arch init`."""
    with store.transaction(write=False) as conn:
        head = store.meta_get(conn, "arch.catalog", None)
        if head is None:
            return None
        head["cards"] = store.records(conn, "SELECT id, body FROM card ORDER BY position", (), ("id",))
    return head


def replace_catalog(catalog: Mapping[str, Any]) -> None:
    """Store the catalog; progress of cards that stay is kept, progress of removed cards goes with them."""
    head = {k: v for k, v in catalog.items() if k != "cards"}
    with store.transaction() as conn:
        store.meta_put(conn, "arch.catalog", head)
        for position, card in enumerate(catalog["cards"]):
            (cid,), body = store.split(card, ("id",))
            conn.execute("INSERT INTO card(id, position, body) VALUES(?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, body=excluded.body",
                         (cid, position, body))
        store.keep_only(conn, "card", "id", [c["id"] for c in catalog["cards"]])


def load_progress() -> dict[str, Record]:
    """{card id: progress} for every card the user has touched."""
    with store.transaction(write=False) as conn:
        return {row["card_id"]: json.loads(row["body"]) for row in conn.execute("SELECT card_id, body FROM card_progress")}


def check_confidence(entry: Mapping[str, Any]) -> None:
    """Fail unless the entry's confidence is 0, 1 or 2.

    Raises:
        ToolError: the confidence is missing, not a whole number, or outside 0 to 2.
    """
    value = entry.get("confidence")
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
        raise ToolError(f"Confidence must be 0, 1 or 2 (got {value!r}). Nothing was changed.")


def set_card_progress(card_id: str, entry: Mapping[str, Any]) -> None:
    """Store the progress of one card and leave every other card's progress alone.

    Raises:
        ToolError: the confidence is not 0, 1 or 2, or the id is not a card in the catalog.
    """
    check_confidence(entry)
    with store.transaction() as conn:
        try:
            conn.execute("INSERT INTO card_progress(card_id, body) VALUES(?,?) "
                         "ON CONFLICT(card_id) DO UPDATE SET body=excluded.body", (card_id, store.dump(entry)))
        except sqlite3.IntegrityError as exc:
            raise ToolError(f"Unknown card {card_id}: progress can only be kept for cards in the catalog.") from exc


def replace_progress(progress: Mapping[str, Mapping[str, Any]]) -> None:
    """Make the stored progress exactly `progress`: cards not in it lose theirs (use `set_card_progress` for one card).

    Raises:
        ToolError: a confidence is not 0, 1 or 2, or an id is not in the catalog.
    """
    for entry in progress.values():
        check_confidence(entry)
    with store.transaction() as conn:
        for card_id, entry in progress.items():
            set_card_progress(card_id, entry)
        store.keep_only(conn, "card_progress", "card_id", list(progress))


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
                     (name, store.dump(seed)))


def has_questions() -> bool:
    """True once `lead init` has stored the question set."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM lead_question LIMIT 1").fetchone() is not None


def load_questions() -> list[Record]:
    """The leadership questions in order."""
    with store.transaction(write=False) as conn:
        return store.records(conn, "SELECT id, body FROM lead_question ORDER BY position", (), ("id",))


def replace_questions(questions: Sequence[Mapping[str, Any]]) -> None:
    """Store the question set; the answers to questions that stay are kept."""
    with store.transaction() as conn:
        for position, q in enumerate(questions):
            (qid,), body = store.split(q, ("id",))
            conn.execute("INSERT INTO lead_question(id, position, body) VALUES(?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET position=excluded.position, body=excluded.body",
                         (qid, position, body))
        store.keep_only(conn, "lead_question", "id", [q["id"] for q in questions])


def load_lead_progress() -> dict[str, Record]:
    """{question id: the user's progress and STAR examples}."""
    with store.transaction(write=False) as conn:
        return {row["question_id"]: json.loads(row["body"])
                for row in conn.execute("SELECT question_id, body FROM lead_progress")}


def set_lead_progress(question_id: str, entry: Mapping[str, Any]) -> None:
    """Store the progress of one question and leave every other question's progress alone.

    Raises:
        ToolError: the confidence is not 0, 1 or 2, or the id is not a stored question.
    """
    check_confidence(entry)
    with store.transaction() as conn:
        try:
            conn.execute("INSERT INTO lead_progress(question_id, body) VALUES(?,?) "
                         "ON CONFLICT(question_id) DO UPDATE SET body=excluded.body", (question_id, store.dump(entry)))
        except sqlite3.IntegrityError as exc:
            raise ToolError(f"Unknown leadership question {question_id}.") from exc


def replace_lead_progress(progress: Mapping[str, Mapping[str, Any]]) -> None:
    """Make the stored progress exactly `progress`: questions not in it lose theirs (use `set_lead_progress` for one).

    Raises:
        ToolError: a confidence is not 0, 1 or 2, or an id is not a question.
    """
    for entry in progress.values():
        check_confidence(entry)
    with store.transaction() as conn:
        for question_id, entry in progress.items():
            set_lead_progress(question_id, entry)
        store.keep_only(conn, "lead_progress", "question_id", list(progress))


def load_company_facts() -> dict[str, Record]:
    """{company id: factual scope (team size, budget, ...)}."""
    with store.transaction(write=False) as conn:
        return {row["company_id"]: json.loads(row["body"])
                for row in conn.execute("SELECT company_id, body FROM lead_company_fact")}


def replace_company_facts(facts: Mapping[str, Mapping[str, Any]]) -> None:
    """Store the factual scope per company."""
    with store.transaction() as conn:
        for cid, entry in facts.items():
            conn.execute("INSERT INTO lead_company_fact(company_id, body) VALUES(?,?) "
                         "ON CONFLICT(company_id) DO UPDATE SET body=excluded.body", (cid, store.dump(entry)))
        store.keep_only(conn, "lead_company_fact", "company_id", list(facts))
