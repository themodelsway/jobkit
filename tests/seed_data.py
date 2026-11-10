"""Synthetic data for every kind, written into a test database by `seed()`."""
from collections.abc import Callable
from typing import Any

from jobkit import store
from jobkit.interview import tables
from jobkit.resumes import tables as resume_tables
from jobkit.user import tables as user_tables
from tests.interview.test_tables import CARD, ENGAGEMENT, PROGRESS, STORY, session

ENTRY = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "question": "q", "answer": "a full answer",
         "grade": "solid", "confidence_after": 2, "tutor": False, "quiz": False}
SEED = {"name": "acmedata", "label": "Acme Data", "source_hosts": ["docs.example.com"], "services": [],
        "pairs": [], "scenarios": [], "dimensions": ["scale"]}
QUESTION = {"id": "team-scope", "category": "Scope and facts", "question": "How big was the team?", "themes": []}
LEAD_PROGRESS = {"confidence": 1, "principle": "p", "notes": "", "last_drilled": "2026-11-01",
                 "examples": {"acme": {"situation": "s", "task": "t", "action": "a", "result": "r", "metric": "m"}}}

DATA: dict[str, Any] = {
    "settings": {"resume_root": "/example", "resume_dirs": [], "tier1_services": ["VPC"]},
    "employers": {"acme": {"name": "Acme Corp", "regex": "Acme"}},
    "open-items": [{"id": 1, "text": "check a figure", "status": "open"}],
    "stories": {"schema_version": 2, "stories": [STORY]},
    "engagements": {"schema_version": 2, "engagements": [ENGAGEMENT]},
    "themes": {"themes": {"platform": {"stories": [STORY["id"]], "questions": []}}},
    "arch-catalog": {"dimensions": ["scale"], "scenarios_note": "n", "tracks": ["aws"], "cards": [CARD]},
    "arch-progress": {"cards": {"vpc": PROGRESS}},
    "arch-tracks": {"acmedata": SEED},
    "lead-questions": {"questions": [QUESTION]},
    "lead-progress": {"questions": {"team-scope": LEAD_PROGRESS}},
    "lead-scope": {"companies": {"acme": {"title": "Lead", "direct_reports": "6"},
                                                    "globex": {"title": None, "direct_reports": None}}},
    "sessions": {"s1": session([ENTRY])},
    "curated": {"certifications": [{"name": "X", "issued": "2024-01", "expires": None}], "education": ["BSc"],
                                 "review_if_metric_matches": ["30%"], "skill_merge": {"llms": "LLM"}, "skill_drop": ["teamwork"],
                                 "tag_only": ["Security"], "skill_group": {"VPC": "Cloud"},
                                 "extra_skills": {"Cloud": [{"name": "Terraform", "aliases": ["TF"]}]}},
    "curation-themes": {"themes": {"acme-1": ["cost"]}, "ignore": ["acme-2"], "summary_angles": {"sum-1": ["focus-a"]}},
    "resume-skills": {"groups": {"Cloud": [{"name": "VPC", "aliases": [], "sources": ["a.pdf"]}], "Data": []},
                                     "tag_only": ["Security"]},
    "resume-companies": {"acme": {
        "id": "acme", "name": "Acme Corp", "aliases": ["Acme"],
        "roles": [{"start": "2021-01", "end": None, "titles": ["Lead"], "subtitles": [], "clients": [], "sources": ["a.pdf"]}],
        "bullets": [{"id": "acme-1", "text": "Cut page load time by 30%.", "role_start": "2021-01", "skills": ["AWS"],
                     "themes": ["cost"], "metrics": ["30%"], "sources": ["a.pdf", "b.pdf"], "variants": ["Cut spend 30%."],
                     "needs_review": True},
                    {"id": "acme-2", "text": "Ran weekly reviews.", "role_start": "2021-01", "skills": [], "themes": [],
                     "metrics": [], "sources": ["a.pdf"]}]}},
    "resume-profile": {"summaries": [{"id": "sum-1", "text": "Engineer.", "angles": [], "sources": ["a.pdf"]}],
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
    "themes": lambda d: tables.replace_themes(d["themes"]), "arch-catalog": tables.replace_catalog,
    "arch-progress": lambda d: tables.replace_progress(d["cards"]), "arch-tracks": _save_tracks,
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
    """Write DATA into the (initialised) test database, every kind in one transaction."""
    with store.transaction():
        for name, data in DATA.items():
            WRITERS[name](data)
