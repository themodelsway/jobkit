"""Researched companies and their facts in the database (the `target_company` and `target_fact` tables).

A company row keeps its key (the name in lower case), name, outcome (`found` or `none found`), date researched and
suggested style as columns, and the ids of the facts the suggestion rests on in `body`. A fact keeps its id,
position, kind, link, label, date of pull and vetting as columns, and its wording, quote and value mapping in
`body`. Every change runs inside the caller's transaction (`store.transaction`); the checks are in `targets.py`.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any, Final

from jk import store

FOUND: Final[str] = "found"
NONE_FOUND: Final[str] = "none found"

Record = dict[str, Any]
COMPANY_FIELDS = ("key", "name", "outcome", "researched", "style", "style_basis")
FACT_FIELDS = ("id", "kind", "link", "label", "pulled", "vetted")


def key_of(name: str) -> str:
    """The stored key of a company name: the name in lower case, so names compare without regard to case."""
    return name.strip().lower()


def _facts(conn: sqlite3.Connection, key: str) -> list[Record]:
    """The facts of one company, in their stored order, with `vetted` as a boolean."""
    facts = store.records(conn, "SELECT id, kind, link, label, pulled, vetted, body FROM target_fact "
                                "WHERE company_key=? ORDER BY position", (key,), FACT_FIELDS)
    for fact in facts:
        fact["vetted"] = bool(fact["vetted"])
    return facts


def load_company(name: str) -> Record | None:
    """One researched company with its facts, found by name in any letter case; None when there is none."""
    with store.transaction(write=False) as conn:
        found = store.records(conn, "SELECT key, name, outcome, researched, style, style_basis, body "
                                    "FROM target_company WHERE key=?", (key_of(name),), COMPANY_FIELDS)
        if not found:
            return None
        found[0]["facts"] = _facts(conn, found[0]["key"])
    return found[0]


def load_companies() -> list[Record]:
    """Every researched company with its facts, by name."""
    with store.transaction(write=False) as conn:
        companies = store.records(conn, "SELECT key, name, outcome, researched, style, style_basis, body "
                                        "FROM target_company ORDER BY key", (), COMPANY_FIELDS)
        for company in companies:
            company["facts"] = _facts(conn, company["key"])
    return companies


def company_names() -> list[str]:
    """The names of the researched companies, by name."""
    with store.transaction(write=False) as conn:
        return [row[0] for row in conn.execute("SELECT name FROM target_company ORDER BY key")]


def save_company(company: Mapping[str, Any]) -> None:
    """Store one company and exactly the facts it holds, in their order (one transaction: all or nothing)."""
    fields, body = store.split({k: v for k, v in company.items() if k != "facts"}, COMPANY_FIELDS)
    with store.transaction() as conn:
        conn.execute("INSERT INTO target_company(key, name, outcome, researched, style, style_basis, body) "
                     "VALUES(?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET name=excluded.name, "
                     "outcome=excluded.outcome, researched=excluded.researched, style=excluded.style, "
                     "style_basis=excluded.style_basis, body=excluded.body", (*fields, body))
        conn.execute("DELETE FROM target_fact WHERE company_key=?", (company["key"],))
        for position, fact in enumerate(company["facts"]):
            (fid, kind, link, label, pulled, vetted), fact_body = store.split(fact, FACT_FIELDS)
            conn.execute("INSERT INTO target_fact(company_key, id, position, kind, link, label, pulled, vetted, body) "
                         "VALUES(?,?,?,?,?,?,?,?,?)",
                         (company["key"], fid, position, kind, link, label, pulled, int(bool(vetted)), fact_body))


def remove_company(name: str) -> bool:
    """Remove a company and its facts; True when there was one."""
    with store.transaction() as conn:
        return conn.execute("DELETE FROM target_company WHERE key=?", (key_of(name),)).rowcount > 0
