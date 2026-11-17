"""Interview data in the database: sessions, role-knowledge cards, leadership questions, stories, engagements.

Each function takes or returns the same dicts the tools used to keep in JSON files, so the tool code is
unchanged. The tables are known to three modules in this folder, re-exported here so callers import one name:
`sessions_tables`, `practice_tables` (cards, progress, tracks, leadership) and `stories_tables`.
"""
from __future__ import annotations

from jk.interview.practice_tables import (
    has_catalog, has_questions, load_catalog, load_company_facts, load_lead_progress, load_progress,
    load_questions, load_track, replace_catalog, replace_company_facts, replace_lead_progress, replace_progress,
    replace_questions, save_track, set_card_progress, set_lead_progress, track_names)
from jk.interview.sessions_tables import (
    ITEM_TABLES, all_sessions, evidence, load_session, save_session, session_exists, session_ids, session_rows)
from jk.interview.stories_tables import (
    has_engagements, has_stories, load_engagements, load_stories, load_themes, replace_engagements, replace_stories,
    replace_themes)

__all__ = [
    "ITEM_TABLES", "all_sessions", "evidence", "has_catalog", "has_engagements", "has_questions", "has_stories",
    "load_catalog", "load_company_facts", "load_engagements", "load_lead_progress", "load_progress",
    "load_questions", "load_session", "load_stories", "load_themes", "load_track", "replace_catalog",
    "replace_company_facts", "replace_engagements", "replace_lead_progress", "replace_progress", "replace_questions",
    "replace_stories", "replace_themes", "save_session", "save_track", "session_exists", "session_ids",
    "session_rows", "set_card_progress", "set_lead_progress", "track_names"]
