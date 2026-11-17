"""Shared helpers for the match-score tests: a small made-up resume (no personal data), a valid request, a posting,
and a home folder holding them."""
import copy
import json

from jk import store
from jk.resumes import match_facts as mf
from jk.resumes import match_score as ms
from jk.resumes import tables
from tests.support import HomeCase, call


def bullet(bid, text, skills=()):
    """A stored bullet of the made-up resume."""
    return {"id": bid, "text": text, "skills": list(skills), "themes": [], "metrics": [], "sources": []}


def facts() -> mf.ResumeFacts:
    """The made-up resume: two companies (one bullet id in both), three skills, two degrees and a certification."""
    companies = {
        "acme": {"id": "acme", "name": "Acme", "aliases": [],
                 "roles": [{"start": "2015-01", "end": "2020-12", "titles": ["Engineer"], "subtitles": [],
                            "clients": [], "sources": []}],
                 "bullets": [bullet("b1", "Built an AWS data platform for ten teams", ["AWS"]),
                             bullet("b2", "Led a team of 6 engineers", []), bullet("dup", "Wrote runbooks")]},
        "acme-2": {"id": "acme-2", "name": "Acme 2", "aliases": [],
                   "roles": [{"start": "2021-01", "end": None, "titles": ["Lead Designer"], "subtitles": [],
                              "clients": [], "sources": []}],
                   "bullets": [bullet("dup", "Wrote guides"), bullet("b3", "Migrated clusters to Kubernetes on AWS",
                                                                      ["Kubernetes", "AWS"])]}}
    skills = {"groups": {"Cloud": [{"name": "AWS", "aliases": ["Amazon Web Services"], "sources": []},
                                   {"name": "Kubernetes", "aliases": ["k8s"], "sources": []}],
                         "Languages": [{"name": "Python", "aliases": [], "sources": []}]}}
    return mf.ResumeFacts(copy.deepcopy(companies), skills,
                          ["M.S. in Computer Science, Some University", "B.A. in Economics, Other College"],
                          ["Example Certified Coach - Associate"])


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


# A posting with a degree, years, a team size and a skill.
POSTING = """Senior Strategist

Qualifications:
- Bachelor's degree in Computer Science.
- 5+ years of experience.

Responsibilities:
- Lead a team of 10 engineers.
- Strong AWS experience.
"""


def seed(company_edit=None):
    """Store the made-up resume in the current database."""
    data = facts()
    companies = copy.deepcopy(dict(data.companies))
    if company_edit:
        company_edit(companies)
    tables.replace_companies(companies)
    tables.replace_skills(dict(data.skills))
    tables.replace_profile({"summaries": [], "education": list(data.education),
                         "certifications": list(data.certifications), "profile_points": [], "projects": []})


class MatchCase(HomeCase):
    """A home folder holding the made-up resume, a posting file and a valid request file."""

    def setUp(self):
        super().setUp()
        seed()
        self.posting = self.home / "posting.txt"
        self.posting.write_text(POSTING, encoding="utf-8")
        self.requests = self.home / "requests.json"
        self.write_request(request())

    def write_request(self, data):
        """Replace the request file."""
        self.requests.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *argv, stdin=""):
        """Run `match-score`; (status, stdout, stderr). The database is closed afterwards."""
        result = call(ms.main, *argv, stdin=stdin)
        store.close()
        return result

    def run_json(self, *extra):
        """`match-score run --json` on the request and posting files; the parsed result."""
        code, out, err = self.cli("run", self.requests, "--jd", self.posting, "--json", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)


def tagged_facts(tag_a_line: bool) -> mf.ResumeFacts:
    """The made-up resume with `Leadership` as a tag-only word, tagged on one line or on none."""
    base = facts()
    companies = copy.deepcopy(dict(base.companies))
    if tag_a_line:
        next(b for b in companies["acme"]["bullets"] if b["id"] == "b2")["skills"] = ["Leadership"]
    skills = {**base.skills, "tag_only": ["Leadership"]}
    return mf.ResumeFacts(companies, skills, base.education, base.certifications)
