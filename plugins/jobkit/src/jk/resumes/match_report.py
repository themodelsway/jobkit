"""The plain-language match-score report: gaps first, then the lower and upper scores, then the assumptions.

Everyday words only. The caveat that this is not an applicant tracking system score is on every report.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from jk.resumes import match_engine as me

CAVEAT: Final[str] = ("This is an estimate of how well your resume lines match this posting. It is not any employer's "
                      "applicant tracking system score, and it does not predict a hiring decision. This feature is an early preview: "
                      "the weights and the way the score is worked out may still change.")
LOW_COVERAGE: Final[int] = 70
LEVEL_WORDS: Final[dict[str, str]] = me.LEVEL_WORDS
GAP_TITLES: Final[tuple[tuple[str, str], ...]] = (
    ("critical", "Must-haves that are not fully shown"), ("required", "Required items not fully shown"),
    ("preferred", "Nice-to-haves not fully shown"), ("unassessed", "Items that could not be judged"))


def build_body(items: list[dict[str, Any]], result: me.Score, meta: dict[str, Any]) -> dict[str, Any]:
    """The stored and printed result: the engine's numbers joined with each requirement's text and evidence."""
    by_id = {r.id: r for r in result.requirements}
    rows = []
    for item in items:
        part = by_id[item["id"]]
        rows.append({**item, "category": part.category, "priority": part.priority, "level": part.level,
                     "credit": float(part.credit), "share": float(me.round1(part.share * 100)),
                     "counted": part.counted})
    return {**meta, "score": result.to_dict(), "requirements": rows, "caveat": CAVEAT}


def _line(row: dict[str, Any]) -> str:
    """One requirement as a bullet: its label, how well it is shown, and the reason in brackets."""
    text = f"- {row['label']}: {LEVEL_WORDS[row['level']]}"
    if row.get("reason"):
        text += f" ({row['reason'].strip().rstrip('.')})"
    text += "."
    if row.get("related") and row["level"] in ("profile_miss", "unknown"):
        text += f" Related experience, not counted: {row['related'].strip().rstrip('.')}."
    return text


def _gap_block(body: dict[str, Any]) -> list[str]:
    """The gap lists, in order."""
    rows = {r["id"]: r for r in body["requirements"]}
    out: list[str] = []
    for key, title in GAP_TITLES:
        ids = body["score"]["gaps"][key]
        if ids:
            out += [f"{title}:"] + [_line(rows[i]) for i in ids] + [""]
    return out


def _shown_block(body: dict[str, Any]) -> list[str]:
    """Requirements the profile shows well, with the stored line cited, so the user can check the match by eye."""
    rows = [r for r in body["requirements"] if r["counted"] and r["level"] in ("full", "substantial")]
    if not rows:
        return []
    out = ["Where your profile shows it:"]
    for row in rows:
        cited = (row.get("evidence_text") or [""])[0]
        out.append(f"- {row['label']}: {LEVEL_WORDS[row['level']]}" + (f' - "{cited}"' if cited else ""))
    return out + [""]


def _unmet_line(body: dict[str, Any]) -> list[str]:
    """A line right under the score naming the must-haves the profile does not show (none when all are shown)."""
    rows = {r["id"]: r for r in body["requirements"]}
    ids = body["score"].get("unmet_critical") or []
    if not ids:
        return []
    return ["Must-haves the profile does not show: " + "; ".join(rows[i]["label"] for i in ids) + ". "
            "They count in the score even where the role level would normally ignore them."]


def _score_block(body: dict[str, Any]) -> list[str]:
    """The lower and upper scores with the band, coverage and categories."""
    score = body["score"]
    low, high = me.whole(Decimal(str(score["lower"]))), me.whole(Decimal(str(score["upper"])))
    spread = f"about {low} to {high} out of 100" if low != high else f"about {low} out of 100"
    out = [f"How well your profile matches this posting: {spread}.", *_unmet_line(body),
           "The lower number counts only what your profile clearly shows. The higher number is the result if every "
           "close call went your way and every item that could not be judged turned out well.",
           f"Level of the role: {me.BAND_LABELS.get(body['band'], body['band'])} ({body['band_reason'].strip().rstrip('.')})"]
    coverage = me.whole(Decimal(str(score["coverage"])))
    note = " Because so little could be judged, treat the score as not precise." if coverage < LOW_COVERAGE else ""
    out.append(f"How much of the posting could be judged: {coverage}%.{note}")
    for name, cat in score["categories"].items():
        out.append(f"- {me.CATEGORY_LABELS[name]}: about {me.whole(Decimal(str(cat['score'])))} "
                   f"(counts for {me.whole(Decimal(str(cat['weight'])))}% of the score)")
    return out


def _side_notes(body: dict[str, Any]) -> list[str]:
    """Categories left out, requirements not counted, and the assumptions."""
    score, out = body["score"], []
    if score["left_out"]:
        names = ", ".join(me.CATEGORY_LABELS[c] for c in score["left_out"])
        out += ["", f"The posting did not ask about: {names}, so they did not count."]
    skipped = [r for r in body["requirements"] if not r["counted"]]
    if skipped:
        out += ["", "Noted, not counted at this level:"] + [f"- {r['label']}" for r in skipped]
    if score["equal_weights"]:
        out += ["", "Every topic in this posting is one that this level normally leaves out, so they were weighted "
                    "equally."]
    if body["assumptions"]:
        out += ["", "What I assumed:"] + [f"- {a}" for a in body["assumptions"]]
    if body["vague"]:
        out += ["", "This posting was vague in several places, so the range is wider than usual."]
    return out


def report(body: dict[str, Any]) -> str:
    """The whole report as text: gaps, scores, side notes, then the caveat."""
    lines = [f"Match for: {body.get('label') or 'this posting'}", ""]
    lines += _gap_block(body) + _shown_block(body) + _score_block(body) + _side_notes(body)
    lines += ["", body["caveat"]]
    return "\n".join(lines) + "\n"
