"""A small made-up resume (no personal data) for the match-score tests."""
import copy
from typing import Any

from jobkit.resumes import match_facts as mf


def bullet(bid, text, skills=()):
    return {"id": bid, "text": text, "skills": list(skills), "themes": [], "metrics": [], "sources": []}


def facts() -> mf.ResumeFacts:
    companies = {
        "acme": {"id": "acme", "name": "Acme", "aliases": [],
                 "roles": [{"start": "2015-01", "end": "2020-12", "titles": ["Engineer"], "subtitles": [],
                            "clients": [], "sources": []}],
                 "bullets": [bullet("b1", "Built an AWS data platform for ten teams", ["AWS"]),
                             bullet("b2", "Led a team of 6 engineers", []), bullet("dup", "Wrote runbooks")]},
        "globex": {"id": "globex", "name": "Globex", "aliases": [],
                   "roles": [{"start": "2021-01", "end": None, "titles": ["Architect"], "subtitles": [],
                              "clients": [], "sources": []}],
                   "bullets": [bullet("dup", "Wrote guides"), bullet("b3", "Migrated clusters to Kubernetes on AWS",
                                                                      ["Kubernetes", "AWS"])]}}
    skills = {"groups": {"Cloud": [{"name": "AWS", "aliases": ["Amazon Web Services"], "sources": []},
                                   {"name": "Kubernetes", "aliases": ["k8s"], "sources": []}],
                         "Languages": [{"name": "Python", "aliases": [], "sources": []}]}}
    return mf.ResumeFacts(copy.deepcopy(companies), skills,
                          ["M.S. in Computer Science, Some University", "B.A. in Economics, Other College"],
                          ["Example Certified Developer - Associate"])


def request(**changes) -> dict:
    """A valid request with three requirements."""
    data = {"schema_version": 1, "band": "mid-manager", "band_reason": "leads a team of engineers", "label": "test",
            "requirements": [
                {"id": "r1", "label": "AWS", "quote": "Strong AWS experience.", "section": "Skills",
                 "category": "core_skills", "priority": "required", "level": "full", "reason": "shown twice",
                 "evidence": ["bullet:b1", "skill:AWS"], "confidence": 0.9},
                {"id": "r2", "label": "Lead a team", "quote": "Lead a team of 10.", "section": "Responsibilities",
                 "category": "people_leadership", "priority": "critical", "level": "partial",
                 "reason": "led six", "evidence": ["bullet:b2"]},
                {"id": "r3", "label": "Results", "quote": "Show results.", "section": "", "category": "impact",
                 "priority": "preferred", "level": "profile_miss", "reason": "no result stated", "evidence": [],
                 "related": "ran a platform"}]}
    data.update(changes)
    return data


def role(start: str, end: str | None, title: str) -> dict[str, Any]:
    """A stored role."""
    return {"start": start, "end": end, "titles": [title], "subtitles": [], "clients": [], "sources": ["a"]}


def line(text: str, role_start: str | None = None, **extra: Any) -> dict[str, Any]:
    """A stored bullet."""
    return {"id": text[:8], "text": text, "role_start": role_start, "skills": [], "themes": [], "metrics": [],
            "sources": ["a"], **extra}


def jd_from_bullets(data: dict) -> str:
    """A job description made of the bullets' own words, so every bullet scores as relevant."""
    return " ".join(b["text"] for c in data["companies"].values() for b in c["bullets"])
