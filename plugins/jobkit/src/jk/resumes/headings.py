"""Recognise resume section headings by meaning, not by one exact spelling.

  heading_key("PROFESSIONAL EXPERIENCE")  ->  "work"
  heading_key("Volunteer Experience:")    ->  "other"   (a known section whose content is not stored)
  heading_key("Product strategy")         ->  None

Library module with no file access. A heading ends the section before it, even when the section it starts is
not stored (key "other"), so awards or volunteering never end up inside the work history.
"""
from __future__ import annotations

import re
from typing import Final

MAX_HEADING_CHARS: Final[int] = 40
MAX_HEADING_WORDS: Final[int] = 5
OTHER: Final[str] = "other"
COMBINED: Final[str] = "education_certs"      # "Education & Certifications": one block holding both

SYNONYMS: Final[dict[str, tuple[str, ...]]] = {
    "work": ("work experience", "experience", "professional experience", "employment", "employment history",
             "work history", "career history", "relevant experience", "professional history", "career",
             "experience summary", "professional background"),
    "summary": ("summary", "professional summary", "executive summary", "career summary", "about", "about me",
                "objective", "career objective", "profile summary", "summary of qualifications"),
    "profile": ("profile", "professional profile", "highlights", "career highlights", "key highlights",
                "key achievements", "achievements", "selected achievements", "accomplishments",
                "key accomplishments", "areas of impact"),
    "skills": ("skills", "key skills", "core skills", "core competencies", "competencies", "areas of expertise",
               "expertise", "skills and tools", "tools", "technologies", "technical proficiencies", "skill set"),
    "skills_technical": ("technical skills", "technical", "technical expertise", "tech stack"),
    "skills_leadership": ("leadership", "leadership skills", "soft skills"),
    "certifications": ("certifications", "certificates", "licenses and certifications", "certifications and training",
                       "professional certifications", "training"),
    "education": ("education", "academic background", "education and training", "qualifications"),
    COMBINED: ("education and certifications", "certifications and education", "education and certificates"),
    "projects": ("projects", "key projects", "selected projects"),
    OTHER: ("awards", "honors", "awards and honors", "honors and awards", "volunteer", "volunteer experience",
            "volunteering", "community involvement", "publications", "patents", "languages", "interests",
            "hobbies", "references", "affiliations", "memberships", "speaking", "conferences",
            "additional information", "additional", "personal"),
}
LOOKUP: Final[dict[str, str]] = {name: key for key, names in SYNONYMS.items() for name in names}
SPACED_RE: Final = re.compile(r"(?:\S ){3,}\S")
WORK_EXITS: Final[frozenset[str]] = frozenset({"skills", "skills_technical", "skills_leadership", "education",
                                               "certifications", "summary"})
JOB_LABELS: Final[frozenset[str]] = frozenset({"tools", "technologies", "skills and tools", "technical proficiencies",
                                               "expertise", "accomplishments", "tech stack", "technical",
                                               "technical expertise", "leadership"})
INLINE_KEYS: Final[frozenset[str]] = frozenset(set(SYNONYMS) - {OTHER, COMBINED, "work"})


def _despace(text: str) -> str:
    """'W O R K   H I S T O R Y' -> 'WORK HISTORY' (letter-spaced headings); other text unchanged."""
    groups = re.split(r"\s{2,}", text)
    if all(SPACED_RE.fullmatch(group) or " " not in group for group in groups) and any(" " in g for g in groups):
        return " ".join(group.replace(" ", "") for group in groups)
    return text


def normalise(text: str) -> str:
    """A heading in comparable form: letter-spacing joined, no trailing colon, '&' as 'and', lower case."""
    text = _despace(text.strip()).rstrip(":").strip()
    return re.sub(r"\s+", " ", text.replace("&", " and ")).strip().lower()


def heading_key(line: str) -> str | None:
    """The section key of a heading line, or None when the line is not a known heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS or stripped.endswith("."):
        return None
    name = normalise(stripped)
    if not stripped[0].isalnum() or len(name.split()) > MAX_HEADING_WORDS:
        return None
    return LOOKUP.get(name)


def inline_heading(line: str, in_work: bool = False) -> tuple[str, str] | None:
    """('skills', 'Python, Java') for 'Skills: Python, Java': a heading with its first content on the same line.
    Only sections whose content is a list or text qualify; 'Languages: Python' stays a label inside skills. Inside
    the work history only the clear exits (skills, education, certifications, summary) count, and not the labels
    jobs often carry ('Technologies: ...', 'Projects: ...', 'Achievements: ...')."""
    head, colon, rest = line.partition(":")
    if not colon or not rest.strip():
        return None
    key = heading_key(head)
    if key not in INLINE_KEYS or key is None:
        return None
    if in_work and (key not in WORK_EXITS or normalise(head) in JOB_LABELS):
        return None
    return key, rest.strip()


def is_unknown_heading(line: str) -> bool:
    """True for a short ALL-CAPS line that is no known heading: words of letters only, at most four words."""
    stripped = line.strip()
    words = stripped.split()
    return (bool(words) and len(words) <= 4 and stripped.isupper() and len(stripped) > 3
            and all(re.fullmatch(r"[A-Z&/'-]+", word) for word in words) and heading_key(stripped) is None)
