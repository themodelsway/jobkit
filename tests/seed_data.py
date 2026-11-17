"""Synthetic data for every kind, written into a test database by `seed()`, and the sample records it uses."""
from collections.abc import Callable
from typing import Any

from jk import store
from jk.interview import tables
from jk.resumes import tables as resume_tables
from jk.user import tables as user_tables

# One record of each interview kind, also used by the table tests.
CARD = {"id": "vpc", "track": "aws", "kind": "topic", "area": "Network", "name": "VPC", "tier": 1, "aliases": [],
        "members": [], "lifecycle": {"status": "active"}, "recent_changes": [], "verified_on": None}
PROGRESS = {"confidence": 1, "notes": "", "last_drilled": "2026-11-01", "links": {"acme": ["b1"]}}
ENGAGEMENT = {"id": "acme-platform", "company": "acme", "title": "Platform", "my_role": "Lead", "period": "2022",
              "summary": "s", "notes": None, "updated": "2026-11-01T10:00:00", "counters": {"f": 2, "d": 1},
              "facts": [{"id": "f1", "text": "12 engineers", "basis": "stated", "source": None, "note": None, "added": "d"},
                        {"id": "f2", "text": "x", "basis": "unsure", "source": None, "note": None, "added": "d"}],
              "decisions": [{"id": "d1", "what": "ECS", "why": "w", "alternatives": ["EKS"], "tradeoffs": "t",
                             "ownership": "mine"}],
              "people": [{"role": "Owner", "note": "n"}]}
STORY = {"id": "acme-platform-story", "company": "acme", "company_name": "Acme", "theme": "platform", "headline": "h",
         "status": "draft", "engagement": "acme-platform", "uses_facts": ["f1"], "updated": "2026-11-01T10:00:00",
         "metrics": [], "resolved": [{"q": "q", "answer": "a", "at": "t"}], "spoken": {"60s": None, "2min": None}}
ENTRY = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "question": "q", "answer": "a full answer",
         "grade": "solid", "confidence_after": 2, "tutor": False, "quiz": False}
SEED = {"name": "people-ops", "label": "People operations", "source_hosts": ["handbook.example.org"], "topics": [],
        "pairs": [], "scenarios": [], "dimensions": ["scale"]}
QUESTION = {"id": "team-scope", "category": "Scope and facts", "question": "How big was the team?", "themes": []}
LEAD_PROGRESS = {"confidence": 1, "principle": "p", "notes": "", "last_drilled": "2026-11-01",
                 "examples": {"acme": {"situation": "s", "task": "t", "action": "a", "result": "r", "metric": "m"}}}


def session(log=(), sid="s1"):
    """A practice session holding the given answer log."""
    return {"id": sid, "title": "t", "mode": "knowledge", "status": "open", "created": "2026-11-01T09:00:00",
            "updated": "2026-11-01T09:00:00", "jd": None, "queue": [{"id": "vpc", "kind": "card"}], "log": list(log)}


DATA: dict[str, Any] = {
    "settings": {"resume_root": "/example", "resume_dirs": [], "key_topics": ["VPC"]},
    "employers": {"acme": {"name": "Acme Corp", "regex": "Acme"}},
    "open-items": [{"id": 1, "text": "check a figure", "status": "open"}],
    "stories": {"schema_version": 2, "stories": [STORY]},
    "engagements": {"schema_version": 2, "engagements": [ENGAGEMENT]},
    "themes": {"themes": {"platform": {"stories": [STORY["id"]], "questions": []}}},
    "cards-catalog": {"dimensions": ["scale"], "scenarios_note": "n", "tracks": ["aws"], "cards": [CARD]},
    "cards-progress": {"cards": {"vpc": PROGRESS}},
    "cards-tracks": {"people-ops": SEED},
    "lead-questions": {"questions": [QUESTION]},
    "lead-progress": {"questions": {"team-scope": LEAD_PROGRESS}},
    "lead-scope": {"companies": {"acme": {"title": "Lead", "direct_reports": "6"},
                                                    "acme-2": {"title": None, "direct_reports": None}}},
    "sessions": {"s1": session([ENTRY])},
    "curated": {"certifications": [{"name": "X", "issued": "2024-01", "expires": None}], "education": ["BSc"],
                                 "review_if_metric_matches": ["30%"], "skill_merge": {"llms": "LLM"}, "skill_drop": ["teamwork"],
                                 "tag_only": ["Security"], "skill_group": {"VPC": "Cloud"},
                                 "extra_skills": {"Cloud": [{"name": "Terraform", "aliases": ["TF"]}]}},
    "curation-themes": {"themes": {"acme-line-1": ["cost"]}, "ignore": ["acme-line-2"], "summary_angles": {"sum-1": ["focus-a"]}},
    "resume-skills": {"groups": {"Cloud": [{"name": "VPC", "aliases": [], "sources": ["a.pdf"]}], "Data": []},
                                     "tag_only": ["Security"]},
    "resume-companies": {"acme": {
        "id": "acme", "name": "Acme Corp", "aliases": ["Acme"],
        "roles": [{"start": "2021-01", "end": None, "titles": ["Lead"], "subtitles": [], "clients": [], "sources": ["a.pdf"]}],
        "bullets": [{"id": "acme-line-1", "text": "Cut checkout drop-off by 30%.", "role_start": "2021-01", "skills": ["AWS"],
                     "themes": ["cost"], "metrics": ["30%"], "sources": ["a.pdf", "b.pdf"], "variants": ["Cut spend 30%."],
                     "needs_review": True},
                    {"id": "acme-line-2", "text": "Ran weekly reviews.", "role_start": "2021-01", "skills": [], "themes": [],
                     "metrics": [], "sources": ["a.pdf"]}]}},
    "resume-profile": {"summaries": [{"id": "sum-1", "text": "Designer.", "angles": [], "sources": ["a.pdf"]}],
                                      "profile_points": ["p"], "education": ["BSc"], "certifications": [{"name": "X"}],
                                      "projects": [], "headlines": ["h"]},
    "resume-index": {"generated": "t", "companies": [{"id": "acme", "name": "Acme Corp", "bullets": 2, "roles": []}],
                                    "skill_groups": {"Cloud": 1}, "themes": ["cost"], "resumes": 1},
    "resume-ledger": {"a.pdf": {"mtime": 100.0, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}},
    "resume-unparsed": {"b.pdf": ["no work history found"]},
}


def _save_tracks(data: dict[str, Any]) -> None:
    for name, seed_ in data.items():
        tables.save_track(name, seed_)


def _save_sessions(data: dict[str, Any]) -> None:
    for session_ in data.values():
        tables.save_session(session_)


WRITERS: dict[str, Callable[[Any], None]] = {
    "stories": tables.replace_stories, "engagements": tables.replace_engagements,
    "themes": lambda d: tables.replace_themes(d["themes"]), "cards-catalog": tables.replace_catalog,
    "cards-progress": lambda d: tables.replace_progress(d["cards"]), "cards-tracks": _save_tracks,
    "lead-questions": lambda d: tables.replace_questions(d["questions"]),
    "lead-progress": lambda d: tables.replace_lead_progress(d["questions"]),
    "lead-scope": lambda d: tables.replace_company_facts(d["companies"]), "sessions": _save_sessions,
    "settings": user_tables.replace_settings, "employers": user_tables.replace_employers,
    "open-items": user_tables.replace_open_items, "resume-companies": resume_tables.replace_companies,
    "resume-skills": resume_tables.replace_skills, "resume-profile": resume_tables.replace_profile,
    "resume-index": resume_tables.save_index, "resume-ledger": resume_tables.replace_ledger,
    "resume-unparsed": resume_tables.replace_unparsed,
    "curated": lambda d: resume_tables.save_curation("curated", d),
    "curation-themes": lambda d: resume_tables.save_curation("themes", d),
}


def seed() -> None:
    """Write DATA into the (initialized) test database, every kind in one transaction."""
    with store.transaction():
        for name, data in DATA.items():
            WRITERS[name](data)
