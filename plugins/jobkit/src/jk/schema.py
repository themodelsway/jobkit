"""The database schema as numbered upgrade steps (see `store.migrate`).

Record tables keep the record as JSON in `body`. A field is a real column only when SQL needs it (a key, a
link, a sort or filter, a listing); every other field lives in `body` only, and a field that is a column is
not repeated in `body`, so each field has one stored value. The append-only `session_log` is the exception.
Never edit a step after release: add a new one.
"""
from __future__ import annotations

import sqlite3
import sys
from typing import Final

from jk.base import ToolError

APPEND_ONLY: Final[str] = """
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, '{table} entries are append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, '{table} entries are append-only'); END;
"""


def run_script(conn: sqlite3.Connection, script: str) -> None:
    """Run several statements one by one (`executescript` would commit the upgrade transaction)."""
    for statement in _split(script):
        conn.execute(statement)


def _split(script: str) -> list[str]:
    """Statements of a script (SQLite itself decides where a statement, including a trigger body, ends)."""
    out, current = [], ""
    for line in script.strip().splitlines():
        current += line + "\n"
        if sqlite3.complete_statement(current):
            out.append(current.strip().rstrip(";"))
            current = ""
    return out


def step_meta_and_docs(conn: sqlite3.Connection) -> None:
    """Version 1: the meta table and the transitional document table."""
    run_script(conn, """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE doc (key TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL);
""")


def step_sessions(conn: sqlite3.Connection) -> None:
    """Version 2: practice sessions, their queue and the append-only answer log."""
    run_script(conn, """
CREATE TABLE session (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
  created TEXT NOT NULL, updated TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE session_item (
  session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE, position INTEGER NOT NULL,
  item TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY (session_id, position));
CREATE TABLE session_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES session(id) ON DELETE RESTRICT,
  at TEXT NOT NULL, item TEXT NOT NULL, kind TEXT NOT NULL, answered INTEGER NOT NULL,
  confidence_after INTEGER, tutor INTEGER NOT NULL, quiz INTEGER NOT NULL, body TEXT NOT NULL);
CREATE INDEX session_log_item ON session_log(item);
CREATE INDEX session_log_session ON session_log(session_id);
""" + APPEND_ONLY.format(table="session_log"))


def step_architecture(conn: sqlite3.Connection) -> None:
    """Version 3: architecture cards, the user's progress on them, and custom tracks."""
    run_script(conn, """
CREATE TABLE card (
  id TEXT PRIMARY KEY, position INTEGER NOT NULL, track TEXT NOT NULL, kind TEXT NOT NULL, area TEXT,
  name TEXT NOT NULL, tier INTEGER, body TEXT NOT NULL);
CREATE TABLE card_progress (
  card_id TEXT PRIMARY KEY REFERENCES card(id) ON DELETE CASCADE, confidence INTEGER NOT NULL,
  last_drilled TEXT, body TEXT NOT NULL);
CREATE TABLE track (name TEXT PRIMARY KEY, body TEXT NOT NULL);
""")


def step_stories(conn: sqlite3.Connection) -> None:
    """Version 4: engagements with their facts, decisions and people; stories; themes."""
    run_script(conn, """
CREATE TABLE engagement (
  id TEXT PRIMARY KEY, position INTEGER NOT NULL, company TEXT, title TEXT, updated TEXT, body TEXT NOT NULL);
CREATE TABLE fact (
  engagement_id TEXT NOT NULL REFERENCES engagement(id) ON DELETE CASCADE, id TEXT NOT NULL, position INTEGER NOT NULL,
  basis TEXT, body TEXT NOT NULL, PRIMARY KEY (engagement_id, id));
CREATE TABLE decision (
  engagement_id TEXT NOT NULL REFERENCES engagement(id) ON DELETE CASCADE, id TEXT NOT NULL, position INTEGER NOT NULL,
  ownership TEXT, body TEXT NOT NULL, PRIMARY KEY (engagement_id, id));
CREATE TABLE person (
  engagement_id TEXT NOT NULL REFERENCES engagement(id) ON DELETE CASCADE, position INTEGER NOT NULL,
  body TEXT NOT NULL, PRIMARY KEY (engagement_id, position));
CREATE TABLE story (
  id TEXT PRIMARY KEY, position INTEGER NOT NULL, company TEXT, theme TEXT, status TEXT NOT NULL,
  engagement_id TEXT REFERENCES engagement(id) DEFERRABLE INITIALLY DEFERRED, updated TEXT, body TEXT NOT NULL);
CREATE INDEX story_engagement ON story(engagement_id);
CREATE TABLE theme (name TEXT PRIMARY KEY, body TEXT NOT NULL);
""")


def step_leadership(conn: sqlite3.Connection) -> None:
    """Version 5: leadership questions, the user's answers, and factual scope per employer."""
    run_script(conn, """
CREATE TABLE lead_question (
  id TEXT PRIMARY KEY, position INTEGER NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE lead_progress (
  question_id TEXT PRIMARY KEY REFERENCES lead_question(id) ON DELETE CASCADE, confidence INTEGER NOT NULL,
  last_drilled TEXT, body TEXT NOT NULL);
CREATE TABLE lead_company_fact (company_id TEXT PRIMARY KEY, body TEXT NOT NULL);
""")


def step_profile(conn: sqlite3.Connection) -> None:
    """Version 6: the user's settings, the employers found in the resumes, and open items."""
    run_script(conn, """
CREATE TABLE setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE employer (id TEXT PRIMARY KEY, position INTEGER NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE open_item (id INTEGER PRIMARY KEY, status TEXT NOT NULL, body TEXT NOT NULL);
""")


def step_resume_data(conn: sqlite3.Connection) -> None:
    """Version 7: what the resumes contain (companies, roles, bullets, skills, sections) and the scan ledger."""
    run_script(conn, """
CREATE TABLE company (id TEXT PRIMARY KEY, position INTEGER NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE role (
  company_id TEXT NOT NULL REFERENCES company(id) ON DELETE CASCADE, position INTEGER NOT NULL,
  start TEXT, body TEXT NOT NULL, PRIMARY KEY (company_id, position));
CREATE TABLE bullet (
  company_id TEXT NOT NULL REFERENCES company(id) ON DELETE CASCADE, id TEXT NOT NULL, position INTEGER NOT NULL,
  needs_review INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY (company_id, id));
CREATE TABLE bullet_source (
  company_id TEXT NOT NULL, bullet_id TEXT NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY (company_id, bullet_id, source),
  FOREIGN KEY (company_id, bullet_id) REFERENCES bullet(company_id, id) ON DELETE CASCADE);
CREATE INDEX bullet_source_file ON bullet_source(source);
CREATE TABLE skill (
  group_name TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL,
  PRIMARY KEY (group_name, position));
CREATE TABLE resume_item (
  section TEXT NOT NULL, position INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY (section, position));
CREATE TABLE ledger (file TEXT PRIMARY KEY, kind TEXT NOT NULL, mtime REAL, body TEXT NOT NULL);
CREATE TABLE unparsed (file TEXT PRIMARY KEY, body TEXT NOT NULL);
""")


def step_curation(conn: sqlite3.Connection) -> None:
    """Version 8: the user's curation (certifications, skill rules, bullet themes, ...), one row per entry."""
    run_script(conn, """
CREATE TABLE curation (
  file TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, position INTEGER NOT NULL, body TEXT NOT NULL,
  PRIMARY KEY (file, kind, key));
""")


def step_drop_documents(conn: sqlite3.Connection) -> None:
    """Version 9: the transitional document table is gone; refuse to drop it if anything is still in it."""
    if conn.execute("SELECT 1 FROM doc LIMIT 1").fetchone() is not None:
        raise RuntimeError("The transitional doc table still holds data; export it before upgrading.")
    conn.execute("DROP TABLE doc")


def step_match_results(conn: sqlite3.Connection) -> None:
    """Version 10: finished match scores (`match-score run`), kept so the same posting and resume give the same result."""
    run_script(conn, """
CREATE TABLE match_result (
  key TEXT PRIMARY KEY, created TEXT NOT NULL, last_used TEXT NOT NULL, label TEXT NOT NULL, band TEXT NOT NULL,
  lower REAL NOT NULL, upper REAL NOT NULL, body TEXT NOT NULL);
""")


# Step 11. (table, ((JSON key, column) pairs kept as the column only))
STRIPPED: Final[tuple[tuple[str, tuple[tuple[str, str], ...]], ...]] = (
    ("session", (("id", "id"), ("title", "title"), ("mode", "mode"), ("status", "status"),
                 ("created", "created"), ("updated", "updated"))),
    ("card", (("id", "id"),)), ("engagement", (("id", "id"),)), ("fact", (("id", "id"),)),
    ("decision", (("id", "id"),)), ("story", (("id", "id"), ("engagement", "engagement_id"))),
    ("lead_question", (("id", "id"),)), ("open_item", (("id", "id"),)), ("company", (("id", "id"),)),
    ("bullet", (("id", "id"),)),
)
DROPPED: Final[dict[str, tuple[str, ...]]] = {
    "session_item": ("body",), "card": ("track", "kind", "area", "name", "tier"),
    "card_progress": ("confidence", "last_drilled"), "engagement": ("company", "title", "updated"),
    "fact": ("basis",), "decision": ("ownership",), "story": ("company", "theme", "status", "updated"),
    "lead_question": ("category",), "lead_progress": ("confidence", "last_drilled"), "employer": ("name",),
    "open_item": ("status",), "company": ("name",), "role": ("start",), "bullet": ("needs_review",),
    "skill": ("name",), "ledger": ("kind", "mtime"), "match_result": ("label", "band", "lower", "upper"),
}


def _refuse(table: str, field: str) -> None:
    """Stop the upgrade: the two stored copies of a field disagree (the message names no record)."""
    raise ToolError(f"Upgrade stopped, nothing was changed: the two stored copies of {table}.{field} disagree. "
                    "Run `jobkit export` to look at the data, then fix it or ask for help.")


def _check_copies(conn: sqlite3.Connection) -> None:
    """Fail unless every field that is about to keep one copy has the same value in both copies.

    A missing JSON key and an empty column count as equal. The one exception is the creation time of a session:
    the column (what `sessions list` showed) is kept and the session is reported on stderr.
    """
    for table, pairs in STRIPPED:
        for key, column in pairs:
            rows = conn.execute(f"SELECT * FROM {table} WHERE json_extract(body, '$.{key}') IS NOT {column}").fetchall()
            if not rows:
                continue
            if (table, key) != ("session", "created"):
                _refuse(table, column)
            for row in rows:
                print(f"Upgrade: session {row['id']} had two different creation times; kept {row['created']}, "
                      "the one `sessions list` showed.", file=sys.stderr)
    odd = conn.execute("SELECT 1 FROM session_item WHERE json_extract(body, '$.id') IS NOT item "
                       "OR json_extract(body, '$.kind') IS NOT kind "
                       "OR (SELECT COUNT(*) FROM json_each(session_item.body)) != 2 LIMIT 1").fetchone()
    if odd:
        _refuse("session_item", "body")


def step_one_home_per_field(conn: sqlite3.Connection) -> None:
    """Version 11: every field has one stored value; no record or field is lost (export is the same before and after).

    Checks first, then removes the JSON keys that are columns, then drops the columns that only repeated the JSON.
    """
    conn.row_factory = sqlite3.Row
    _check_copies(conn)
    for table, pairs in STRIPPED:
        paths = ", ".join(f"'$.{key}'" for key, _ in pairs)
        conn.execute(f"UPDATE {table} SET body = json_remove(body, {paths})")
    for table, columns in DROPPED.items():
        for column in columns:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    conn.execute("DROP TABLE bullet_source")


def step_terms(conn: sqlite3.Connection) -> None:
    """Version 12: your own words that must never be committed (products, clients, patterns) and the ones to ignore."""
    run_script(conn, """
CREATE TABLE term (
  text TEXT PRIMARY KEY COLLATE NOCASE, kind TEXT NOT NULL, match TEXT NOT NULL, ignored INTEGER NOT NULL DEFAULT 0);
""")


def step_target_research(conn: sqlite3.Connection) -> None:
    """Version 13: researched companies and their facts, and the style and company each new log entry records.

    Nothing existing is rewritten. Log rows written before this step have no style and no company (NULL).
    """
    run_script(conn, """
CREATE TABLE target_company (
  key TEXT PRIMARY KEY, name TEXT NOT NULL, outcome TEXT NOT NULL, researched TEXT NOT NULL,
  style TEXT, style_basis TEXT, body TEXT NOT NULL);
CREATE TABLE target_fact (
  company_key TEXT NOT NULL REFERENCES target_company(key) ON DELETE CASCADE, id TEXT NOT NULL,
  position INTEGER NOT NULL, kind TEXT NOT NULL, link TEXT NOT NULL, label TEXT NOT NULL, pulled TEXT NOT NULL,
  vetted INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY (company_key, id));
ALTER TABLE session_log ADD COLUMN style TEXT;
ALTER TABLE session_log ADD COLUMN company TEXT;
""")


def step_cards(conn: sqlite3.Connection) -> None:
    """Version 14: the stored names of role-knowledge cards. Mode and tutor topic `architecture` become `knowledge`,
    card kind `service` becomes `topic`, a custom track's `services` become its `topics`, the setting
    `tier1_services` becomes `key_topics`, and the catalog's meta key `arch.catalog` becomes `cards.catalog`.
    The append-only log is not touched (it records items by id and kind card, story or leader)."""
    run_script(conn, """
UPDATE session SET mode = 'knowledge' WHERE mode = 'architecture';
UPDATE session SET body = json_set(body, '$.topic', 'knowledge') WHERE json_extract(body, '$.topic') = 'architecture';
UPDATE card SET body = json_set(body, '$.kind', 'topic') WHERE json_extract(body, '$.kind') = 'service';
UPDATE track SET body = json_set(json_remove(body, '$.services'), '$.topics', json(json_extract(body, '$.services')))
  WHERE json_type(body, '$.services') IS NOT NULL;
UPDATE setting SET key = 'key_topics' WHERE key = 'tier1_services';
UPDATE meta SET key = 'cards.catalog' WHERE key = 'arch.catalog';
""")


def step_role_questions(conn: sqlite3.Connection) -> None:
    """Version 15: role questions, search outcomes and practice progress."""
    run_script(conn, """
CREATE TABLE role_research (
  role_key TEXT PRIMARY KEY, role TEXT NOT NULL, outcome TEXT NOT NULL, researched TEXT);
CREATE TABLE role_question (
  id TEXT PRIMARY KEY, role_key TEXT NOT NULL REFERENCES role_research(role_key), position INTEGER NOT NULL,
  source TEXT NOT NULL, link TEXT, label TEXT NOT NULL, pulled TEXT, body TEXT NOT NULL);
CREATE INDEX role_question_order ON role_question(role_key, position);
CREATE TABLE question_progress (
  question_id TEXT PRIMARY KEY REFERENCES role_question(id) ON DELETE CASCADE, body TEXT NOT NULL);
""")


STEPS: list = [step_meta_and_docs, step_sessions, step_architecture, step_stories, step_leadership,
               step_profile, step_resume_data, step_curation, step_drop_documents, step_match_results,
               step_one_home_per_field, step_terms, step_target_research, step_cards, step_role_questions]
