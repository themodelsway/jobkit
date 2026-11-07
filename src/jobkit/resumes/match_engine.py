"""The match-score arithmetic: how well rated job requirements cover a job posting, as a lower and an upper score.

Pure and deterministic: standard library only, `Decimal` arithmetic, no database, no model. The same input
always gives the same output. Every number here (credits, multipliers, band weights) is a placeholder default,
versioned by `WEIGHTS_VERSION`; changing one means bumping the version, which retires cached results.

A requirement has a *reading* (category, priority, level). A flagged requirement that took its fixed fallback
also carries the other defensible reading (`alt`): the lower score uses the fallback, the upper score uses
whichever of the two gives the higher lower score, and unknown counts 0 in the lower and 1 in the upper score.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Any, Final

RUBRIC_VERSION: Final[str] = "1"
WEIGHTS_VERSION: Final[str] = "1"

LEVELS: Final[tuple[str, ...]] = ("full", "substantial", "partial", "profile_miss", "unknown")
CREDITS: Final[dict[str, Decimal]] = {
    "full": Decimal("1.00"), "substantial": Decimal("0.75"), "partial": Decimal("0.40"), "profile_miss": Decimal(0)}
PRIORITIES: Final[tuple[str, ...]] = ("critical", "required", "preferred")
MULTIPLIERS: Final[dict[str, Decimal]] = {"critical": Decimal(3), "required": Decimal(2), "preferred": Decimal(1)}
CATEGORIES: Final[tuple[str, ...]] = (
    "core_skills", "impact", "functional_leadership", "people_leadership", "strategy", "domain", "education")
CATEGORY_LABELS: Final[dict[str, str]] = {
    "core_skills": "core skills and tools", "impact": "results and impact",
    "functional_leadership": "technical or functional leadership", "people_leadership": "people leadership",
    "strategy": "strategy, budget and influence", "domain": "domain knowledge",
    "education": "education and certifications"}
BAND_LABELS: Final[dict[str, str]] = {
    "junior-ic": "early-career individual contributor", "mid-senior-ic": "mid to senior individual contributor",
    "mid-manager": "manager (up to senior manager)", "executive": "director or senior director",
    "senior-executive": "vice president or above"}
LEVEL_WORDS: Final[dict[str, str]] = {
    "full": "shown clearly", "substantial": "mostly shown", "partial": "partly shown",
    "profile_miss": "not shown in your profile yet", "unknown": "could not be judged"}
GAP_LEVELS: Final[frozenset[str]] = frozenset({"partial", "profile_miss", "unknown"})
TOLERANCE: Final[Decimal] = Decimal("1e-9")
PRECISION: Final[int] = 50


def _band(*weights: str) -> dict[str, Decimal]:
    """Band weights in the order of `CATEGORIES`."""
    return dict(zip(CATEGORIES, (Decimal(w) for w in weights), strict=True))


BAND_ORDER: Final[tuple[str, ...]] = ("junior-ic", "mid-senior-ic", "mid-manager", "executive", "senior-executive")
BANDS: Final[dict[str, dict[str, Decimal]]] = {
    "junior-ic": _band(".50", ".15", "0", "0", "0", ".10", ".25"),
    "mid-senior-ic": _band(".30", ".25", ".15", "0", ".05", ".15", ".10"),
    "mid-manager": _band(".15", ".25", ".10", ".25", ".10", ".10", ".05"),
    "executive": _band(".05", ".25", ".05", ".20", ".20", ".20", ".05"),
    "senior-executive": _band("0", ".25", "0", ".20", ".30", ".20", ".05"),
}


@dataclass(frozen=True)
class Reading:
    """One way of reading a requirement."""

    category: str
    priority: str
    level: str


@dataclass(frozen=True)
class Requirement:
    """A rated requirement; `alt` is the other reading of a flag that took its fallback."""

    id: str
    reading: Reading
    importance: Decimal = Decimal(1)
    alt: Reading | None = None


@dataclass(frozen=True)
class CategoryScore:
    """Scores of one category (0 to 100 as `Decimal`) and its share of the overall score."""

    score: Decimal
    upper: Decimal
    coverage: Decimal
    weight: Decimal


@dataclass(frozen=True)
class RequirementResult:
    """What one requirement contributed (the lower reading) and how much of the overall score rides on it."""

    id: str
    category: str
    priority: str
    level: str
    credit: Decimal
    share: Decimal
    counted: bool


@dataclass(frozen=True)
class Score:
    """The result of scoring a list of requirements."""

    lower: Decimal
    upper: Decimal
    coverage: Decimal
    categories: dict[str, CategoryScore]
    left_out: list[str]
    not_counted: list[str]
    equal_weights: bool
    gaps: dict[str, list[str]]
    requirements: list[RequirementResult] = field(default_factory=list)
    unmet_critical: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form: numbers keep one decimal."""
        return {
            "lower": float(round1(self.lower)), "upper": float(round1(self.upper)),
            "coverage": float(round1(self.coverage)),
            "categories": {name: {"score": float(round1(c.score)), "upper": float(round1(c.upper)),
                                  "coverage": float(round1(c.coverage)), "weight": float(round1(c.weight * 100))}
                           for name, c in self.categories.items()},
            "left_out": self.left_out, "not_counted": self.not_counted, "equal_weights": self.equal_weights,
            "gaps": self.gaps, "unmet_critical": self.unmet_critical,
            "requirements": [{"id": r.id, "category": r.category, "priority": r.priority, "level": r.level,
                              "credit": float(r.credit), "share": float(round1(r.share * 100)),
                              "counted": r.counted} for r in self.requirements]}


@dataclass
class _Totals:
    """Sums for one category in one pass."""

    weight: Decimal = Decimal(0)
    credit: Decimal = Decimal(0)
    assessed: Decimal = Decimal(0)


def round1(value: Decimal) -> Decimal:
    """One decimal place, half up (display only; never used inside the arithmetic)."""
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def whole(value: Decimal) -> int:
    """A whole number, half up (what the plain report shows)."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def validate_band(name: str, weights: Mapping[str, Any]) -> dict[str, Decimal]:
    """The band's weights as `Decimal`, or raise ValueError listing every problem.

    Weights must cover exactly the categories, be finite and not negative, total 1 (within 1e-9) and have at
    least one above zero.
    """
    problems = [f"unknown category {key!r}" for key in weights if key not in CATEGORIES]
    problems += [f"missing category {key!r}" for key in CATEGORIES if key not in weights]
    values: dict[str, Decimal] = {}
    for key in CATEGORIES:
        if key in weights:
            number = _number(weights[key])
            if number is None or not number.is_finite() or number < 0:
                problems.append(f"weight of {key!r} must be a number that is not negative")
            else:
                values[key] = number
    if not problems:
        problems += _total_problems(values)
    if problems:
        raise ValueError(f"Band {name!r}: " + "; ".join(problems))
    return values


def _number(value: Any) -> Decimal | None:
    """A `Decimal` from a number or numeric text, else None (booleans are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def _total_problems(values: Mapping[str, Decimal]) -> list[str]:
    """Problems with the total of a complete set of weights."""
    total = sum(values.values(), Decimal(0))
    if abs(total - 1) > TOLERANCE:
        return [f"weights total {total}, not 1"]
    if not any(v > 0 for v in values.values()):
        return ["at least one weight must be above zero"]
    return []


def _collect(rows: Sequence[tuple[Requirement, Reading]], unknown: Decimal) -> dict[str, _Totals]:
    """Per-category sums for the chosen reading of each requirement."""
    cats: dict[str, _Totals] = {}
    for req, reading in rows:
        weight = MULTIPLIERS[reading.priority] * req.importance
        totals = cats.setdefault(reading.category, _Totals())
        totals.weight += weight
        totals.credit += weight * CREDITS.get(reading.level, unknown)
        if reading.level != "unknown":
            totals.assessed += weight
    return cats


def must_have_weights(reqs: Sequence[Requirement], weights: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """The band weights, except that a category holding a critical requirement never counts for less than the
    smallest positive weight of the band: an explicit must-have is not dropped by a role-level preset."""
    floor = min((w for w in weights.values() if w > 0), default=Decimal(0))
    adjusted = dict(weights)
    for req in reqs:
        for reading in (req.reading, req.alt):
            if reading is not None and reading.priority == "critical" and adjusted[reading.category] == 0:
                adjusted[reading.category] = floor
    return adjusted


def _effective(cats: Mapping[str, _Totals], weights: Mapping[str, Decimal]) -> tuple[dict[str, Decimal], bool]:
    """Band weights of the populated categories rescaled to total 1, and whether equal weights were needed.

    A category with weight 0 does not count. When every populated category has weight 0, they share equally.
    """
    active = {c: weights[c] for c in cats if weights[c] > 0}
    equal = not active
    if equal:
        active = {c: Decimal(1) for c in cats}
    total = sum(active.values(), Decimal(0))
    return {c: w / total for c, w in active.items()}, equal


def _overall(cats: Mapping[str, _Totals], eff: Mapping[str, Decimal]) -> tuple[Decimal, Decimal]:
    """(score, coverage), both 0 to 100, for one pass."""
    points = sum((eff[c] * cats[c].credit / cats[c].weight for c in eff), Decimal(0)) * 100
    coverage = sum((eff[c] * cats[c].assessed / cats[c].weight for c in eff), Decimal(0)) * 100
    return points, coverage


def _lower_with(reqs: Sequence[Requirement], weights: Mapping[str, Decimal], use_alt: frozenset[str]) -> Decimal:
    """The lower score when the requirements named in `use_alt` take their other reading."""
    rows = [(r, r.alt if r.id in use_alt and r.alt is not None else r.reading) for r in reqs]
    cats = _collect(rows, Decimal(0))
    return _overall(cats, _effective(cats, weights)[0])[0]


def shift(reqs: Sequence[Requirement], weights: Mapping[str, Decimal], req_id: str) -> Decimal:
    """How the lower score changes (signed) when only this flagged requirement takes its other reading."""
    weights = must_have_weights(reqs, weights)
    with localcontext(Context(prec=PRECISION)):
        base = _lower_with(reqs, weights, frozenset())
        return _lower_with(reqs, weights, frozenset({req_id})) - base


def swing(reqs: Sequence[Requirement], weights: Mapping[str, Decimal], req_id: str) -> Decimal:
    """How far the lower score moves when only this flagged requirement takes its other reading."""
    return abs(shift(reqs, weights, req_id))


def _higher_readings(reqs: Sequence[Requirement], weights: Mapping[str, Decimal]) -> list[Reading]:
    """For each requirement the reading the upper score uses (the other reading when it scores strictly higher)."""
    base = _lower_with(reqs, weights, frozenset())
    chosen = []
    for req in reqs:
        take_alt = req.alt is not None and _lower_with(reqs, weights, frozenset({req.id})) > base
        chosen.append(req.alt if take_alt and req.alt is not None else req.reading)
    return chosen


def score(requirements: Sequence[Requirement], weights: Mapping[str, Decimal]) -> Score:
    """Score the requirements against a band's weights.

    Raises:
        ValueError: there are no requirements.
    """
    if not requirements:
        raise ValueError("There is nothing to score: the list of requirements is empty.")
    with localcontext(Context(prec=PRECISION)):
        return _score(list(requirements), must_have_weights(requirements, weights))


def _score(reqs: list[Requirement], weights: Mapping[str, Decimal]) -> Score:
    """The scoring itself (runs at high precision)."""
    low_cats = _collect([(r, r.reading) for r in reqs], Decimal(0))
    eff, equal = _effective(low_cats, weights)
    lower, coverage = _overall(low_cats, eff)
    up_rows = list(zip(reqs, _higher_readings(reqs, weights), strict=True))
    up_cats = _collect(up_rows, Decimal(1))
    up_eff, _ = _effective(up_cats, weights)
    upper = max(_overall(up_cats, up_eff)[0], lower)    # a flag's higher reading never lowers the upper score
    categories = _category_scores(low_cats, up_cats, eff, up_eff)
    results = _results(reqs, low_cats, eff)
    return Score(
        lower=lower, upper=upper, coverage=coverage, categories=categories,
        left_out=[c for c in CATEGORIES if c not in low_cats and weights[c] > 0],
        not_counted=[r.id for r in results if not r.counted], equal_weights=equal,
        gaps=_gaps(results), requirements=results,
        unmet_critical=[r.id for r in results if r.priority == "critical" and r.level not in ("full", "substantial")])


def _category_scores(low: Mapping[str, _Totals], up: Mapping[str, _Totals], eff: Mapping[str, Decimal],
                     up_eff: Mapping[str, Decimal]) -> dict[str, CategoryScore]:
    """Per-category lower and upper scores (0 to 100), coverage and effective weight, in category order."""
    out: dict[str, CategoryScore] = {}
    for name in CATEGORIES:
        if name not in eff:
            continue
        mine = low[name]
        lower = mine.credit / mine.weight * 100
        theirs = up.get(name) if name in up_eff else None
        upper = max(theirs.credit / theirs.weight * 100, lower) if theirs else lower
        out[name] = CategoryScore(lower, upper, mine.assessed / mine.weight * 100, eff[name])
    return out


def _results(reqs: Sequence[Requirement], cats: Mapping[str, _Totals], eff: Mapping[str, Decimal]
             ) -> list[RequirementResult]:
    """What each requirement contributed, in input order."""
    out = []
    for req in reqs:
        reading = req.reading
        weight = MULTIPLIERS[reading.priority] * req.importance
        counted = reading.category in eff
        share = eff[reading.category] * weight / cats[reading.category].weight if counted else Decimal(0)
        out.append(RequirementResult(req.id, reading.category, reading.priority, reading.level,
                                     CREDITS.get(reading.level, Decimal(0)), share, counted))
    return out


def _gaps(results: Sequence[RequirementResult]) -> dict[str, list[str]]:
    """Gap lists of the counted requirements, ordered by priority, share of the score, then input order."""
    counted = [(i, r) for i, r in enumerate(results) if r.counted]

    def pick(rule: Any) -> list[str]:
        chosen = [(i, r) for i, r in counted if rule(r)]
        chosen.sort(key=lambda pair: (PRIORITIES.index(pair[1].priority), -pair[1].share, pair[0]))
        return [r.id for _, r in chosen]

    return {
        "critical": pick(lambda r: r.priority == "critical" and r.level != "full"),
        "required": pick(lambda r: r.priority == "required" and r.level in GAP_LEVELS),
        "preferred": pick(lambda r: r.priority == "preferred" and r.level in GAP_LEVELS),
        "unassessed": pick(lambda r: r.level == "unknown"),
    }
