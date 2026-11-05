"""A synthetic old-format data tree (profile/, prep/, resume-data/) for migration tests."""
import json
from pathlib import Path

from tests.interview.test_tables import CARD, ENGAGEMENT, PROGRESS, STORY, session

ENTRY = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "question": "q", "answer": "a full answer",
         "grade": "solid", "confidence_after": 2, "tutor": False, "quiz": False}
SEED = {"name": "acmedata", "label": "Acme Data", "source_hosts": ["docs.example.com"], "services": [],
        "pairs": [], "scenarios": [], "dimensions": ["scale"]}
QUESTION = {"id": "team-scope", "category": "Scope and facts", "question": "How big was the team?", "themes": []}
LEAD_PROGRESS = {"confidence": 1, "principle": "p", "notes": "", "last_drilled": "2026-11-01",
                 "examples": {"acme": {"situation": "s", "task": "t", "action": "a", "result": "r", "metric": "m"}}}

FILES: dict[str, object] = {
    "profile/profile.json": {"resume_root": "/example", "resume_dirs": [], "tier1_services": ["VPC"]},
    "profile/companies.json": {"acme": {"name": "Acme Corp", "regex": "Acme"}},
    "profile/open_items.json": [{"id": 1, "text": "check a figure", "status": "open"}],
    "prep/stories.json": {"schema_version": 2, "stories": [STORY]},
    "prep/engagements.json": {"schema_version": 2, "engagements": [ENGAGEMENT]},
    "prep/themes.json": {"themes": {"platform": {"stories": [STORY["id"]], "questions": []}}},
    "prep/arch/catalog.json": {"dimensions": ["scale"], "scenarios_note": "n", "tracks": ["aws"], "cards": [CARD]},
    "prep/arch/progress.json": {"cards": {"vpc": PROGRESS}},
    "prep/arch/tracks/acmedata.json": SEED,
    "prep/leadership/questions.json": {"questions": [QUESTION]},
    "prep/leadership/progress.json": {"questions": {"team-scope": LEAD_PROGRESS}},
    "prep/leadership/profile.json": {"companies": {"acme": {"title": "Lead", "direct_reports": "6"},
                                                    "globex": {"title": None, "direct_reports": None}}},
    "prep/sessions/s1.json": session([ENTRY]),
    "prep/sessions/index.json": {"sessions": [{"id": "s1"}]},
    "resume-data/curated.json": {"certifications": [{"name": "X", "issued": "2024-01", "expires": None}], "education": ["BSc"],
                                 "review_if_metric_matches": ["30%"], "skill_merge": {"llms": "LLM"}, "skill_drop": ["teamwork"],
                                 "tag_only": ["Security"], "skill_group": {"VPC": "Cloud"},
                                 "extra_skills": {"Cloud": [{"name": "Terraform", "aliases": ["TF"]}]}},
    "resume-data/themes.json": {"themes": {"acme-1": ["cost"]}, "ignore": ["acme-2"], "summary_angles": {"sum-1": ["focus-a"]}},
    "resume-data/json/skills.json": {"groups": {"Cloud": [{"name": "VPC", "aliases": [], "sources": ["a.pdf"]}], "Data": []},
                                     "tag_only": ["Security"]},
    "resume-data/json/companies/acme.json": {
        "id": "acme", "name": "Acme Corp", "aliases": ["Acme"],
        "roles": [{"start": "2021-01", "end": None, "titles": ["Lead"], "subtitles": [], "clients": [], "sources": ["a.pdf"]}],
        "bullets": [{"id": "acme-1", "text": "Cut page load time by 30%.", "role_start": "2021-01", "skills": ["AWS"],
                     "themes": ["cost"], "metrics": ["30%"], "sources": ["a.pdf", "b.pdf"], "variants": ["Cut spend 30%."],
                     "needs_review": True},
                    {"id": "acme-2", "text": "Ran weekly reviews.", "role_start": "2021-01", "skills": [], "themes": [],
                     "metrics": [], "sources": ["a.pdf"]}]},
    "resume-data/json/profile.json": {"summaries": [{"id": "sum-1", "text": "Engineer.", "angles": [], "sources": ["a.pdf"]}],
                                      "profile_points": ["p"], "education": ["BSc"], "certifications": [{"name": "X"}],
                                      "projects": [], "headlines": ["h"]},
    "resume-data/json/index.json": {"generated": "t", "companies": [{"id": "acme", "name": "Acme Corp", "bullets": 2, "roles": []}],
                                    "skill_groups": {"Cloud": 1}, "themes": ["cost"], "resumes": 1},
    "resume-data/json/ledger.json": {"a.pdf": {"mtime": 100.0, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}},
    "resume-data/json/_unparsed.json": {"b.pdf": ["no work history found"]},
}


def build_old_tree(root: Path) -> Path:
    """Write every file of FILES (plus header.md and the old .bak/.lock leftovers) under `root`."""
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    (root / "profile" / "header.md").write_text("# Jane Example\nCity | jane@example.com\n", encoding="utf-8")
    (root / "prep" / "stories.json.bak").write_text("{}", encoding="utf-8")
    (root / "prep" / ".lock").write_text("", encoding="utf-8")
    return root
