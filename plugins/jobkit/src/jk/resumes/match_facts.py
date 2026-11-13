"""What the match score may cite: the stored resume facts, evidence references, and the fingerprints used as cache keys.

`ResumeFacts` is a plain snapshot, so everything here except `load_facts` works without a database.
Standard library only. Import it as `from jk.resumes import match_facts`.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jk import common
from jk.resumes import resume_data as rd
from jk.resumes import tables

REF_KINDS = ("bullet", "skill", "education", "certification", "role")


@dataclass(frozen=True)
class ResumeFacts:
    """A snapshot of what the resumes show: companies (with roles and bullets), skills, education, certifications."""

    companies: Mapping[str, Any]
    skills: Mapping[str, Any]
    education: list[str]
    certifications: list[str]


class EvidenceError(ValueError):
    """A reference that cannot be resolved (the message says why)."""


def load_facts() -> ResumeFacts:
    """The stored facts.

    Raises:
        ToolError: there is no resume data yet.
    """
    if not tables.has_resume_data():
        raise common.ToolError(rd.MISSING_DATA)
    profile = rd.load_profile()
    certs = [c["name"] if isinstance(c, dict) else str(c) for c in profile.get("certifications", [])]
    return ResumeFacts(rd.load_companies(), rd.load_skills(), [str(e) for e in profile.get("education", [])], certs)


def bullet_owners(facts: ResumeFacts, bullet_id: str) -> list[str]:
    """Ids of the companies that have a line with this id."""
    return [cid for cid, company in facts.companies.items() if any(b["id"] == bullet_id for b in company["bullets"])]


def bullet_ref(facts: ResumeFacts, company_id: str, bullet_id: str) -> str:
    """The shortest reference that finds this line: the company form only when two companies share the id."""
    return f"bullet:{bullet_id}" if len(bullet_owners(facts, bullet_id)) == 1 else f"bullet:{company_id}:{bullet_id}"


def resolve(ref: Any, facts: ResumeFacts) -> str:
    """The text a reference points at.

    Raises:
        EvidenceError: the reference is malformed or points at nothing (or at several lines).
    """
    if not isinstance(ref, str) or ":" not in ref:
        raise EvidenceError(f"{ref!r} is not a reference like 'bullet:ID' (kinds: {', '.join(REF_KINDS)})")
    kind, _, rest = ref.partition(":")
    handler = {"bullet": _bullet, "skill": _skill, "education": _education, "certification": _certification,
               "role": _role}.get(kind)
    if handler is None:
        raise EvidenceError(f"unknown reference kind {kind!r} (kinds: {', '.join(REF_KINDS)})")
    return handler(rest, facts)


def _bullet(rest: str, facts: ResumeFacts) -> str:
    """Text of a line given as `ID` or `COMPANY_ID:ID`."""
    company_id, _, bullet_id = rest.rpartition(":")
    owners = bullet_owners(facts, bullet_id)
    if company_id:
        owners = [c for c in owners if c == company_id]
    if not owners:
        raise EvidenceError(f"no stored line has the id {bullet_id!r}")
    if len(owners) > 1:
        raise EvidenceError(f"the id {bullet_id!r} is in several companies; use bullet:COMPANY_ID:{bullet_id}")
    return next(b["text"] for b in facts.companies[owners[0]]["bullets"] if b["id"] == bullet_id)


def _tagged_lines(name: str, facts: ResumeFacts) -> bool:
    """True when a stored line carries `name` as a tag."""
    return any(name in (*b.get("skills", []), *b.get("skills_manual", []))
               for c in facts.companies.values() for b in c["bullets"])


def _skill(rest: str, facts: ResumeFacts) -> str:
    """The stored skill name for a name or alias (case does not matter). A tag-only word (a quality such as
    Leadership) counts only when a stored line carries that tag."""
    wanted = rest.strip().lower()
    for items in facts.skills.get("groups", {}).values():
        for skill in items:
            if wanted == skill["name"].lower() or wanted in (a.lower() for a in skill.get("aliases", [])):
                return str(skill["name"])
    for name in facts.skills.get("tag_only", []):
        if wanted == name.lower():
            if _tagged_lines(name, facts):
                return str(name)
            raise EvidenceError(f"{name!r} is a tag-only word and no stored line carries it")
    raise EvidenceError(f"no stored skill named {rest!r}")


def _education(rest: str, facts: ResumeFacts) -> str:
    """The education line with this 1-based number."""
    if not rest.isdigit() or not 1 <= int(rest) <= len(facts.education):
        raise EvidenceError(f"no education entry {rest!r} (there are {len(facts.education)}; numbers start at 1)")
    return facts.education[int(rest) - 1]


def _certification(rest: str, facts: ResumeFacts) -> str:
    """The stored certification whose name equals this one (case does not matter)."""
    for name in facts.certifications:
        if name.lower() == rest.strip().lower():
            return name
    raise EvidenceError(f"no stored certification named {rest!r}")


def _role(rest: str, facts: ResumeFacts) -> str:
    """A description of the roles at one company."""
    company = facts.companies.get(rest)
    if company is None or not company["roles"]:
        raise EvidenceError(f"no stored company with roles has the id {rest!r}")
    spans = ", ".join(f"{r.get('start') or '?'} to {r.get('end') or 'now'}" for r in company["roles"])
    return f"{company['name']} ({spans})"


# ---------------------------------------------------------------- fingerprints

def normalise_posting(text: str) -> str:
    """The posting text as the cache sees it: Unicode normalised, LF line endings, whitespace runs collapsed."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


def _digest(value: Any) -> str:
    """SHA-256 of canonical JSON."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def posting_fingerprint(text: str) -> str:
    """SHA-256 of the normalised posting."""
    return hashlib.sha256(normalise_posting(text).encode("utf-8")).hexdigest()


def resume_fingerprint(facts: ResumeFacts) -> str:
    """SHA-256 of what scoring can cite, by text and not by id (a rebuild that changes no text keeps it): each
    line's text, whether it is ignored or flagged, and its tags, plus skills, roles, education and certifications."""
    skills = sorted((s["name"], sorted(s.get("aliases", []))) for g in facts.skills.get("groups", {}).values()
                    for s in g)
    bullets = sorted((c["name"], b["text"], bool(b.get("ignored")), bool(b.get("needs_review")),
                      sorted(b.get("skills", [])), sorted(b.get("skills_manual", [])))
                     for c in facts.companies.values() for b in c["bullets"])
    roles = sorted((c["name"], r.get("start") or "", r.get("end") or "", list(r.get("titles", [])))
                   for c in facts.companies.values() for r in c["roles"])
    return _digest({"bullets": bullets, "skills": skills, "education": list(facts.education),
                    "certifications": sorted(facts.certifications), "roles": roles})


def result_key(posting: str, resume: str, rubric: str, weights: str, day: str) -> str:
    """The cache key for the inputs that exist before a request does; `day` (YYYY-MM-DD) is the assessment date,
    because years in an ongoing role grow with it."""
    return _digest([posting, resume, rubric, weights, day])[:24]


def variant_key(*parts: Any) -> str:
    """A short digest of the judgments that make one result differ from another for the same key (the band and
    the requests)."""
    return _digest(list(parts))[:8]
