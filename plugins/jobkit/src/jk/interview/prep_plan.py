"""The preparation planner: what to practise next, why, and which experience to use.

A pure module: plain data in, an ordered list of explained actions out. It reads no database, file or
network, and takes the date as an argument, so the same snapshot and date always give the same plan.
Nothing calls it yet; the caller (later, the practice commands) builds the `Snapshot`.

Resume lines may be passed as `leads`: hints that name a line in a question, never evidence.

Three kinds of evidence stay apart: experience (confirmed facts and stories), knowledge (a passed quiz or a
good answer) and performance (graded drill answers). A quiz never creates experience; no grade is ever
invented from a coarse self-rating.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final

from jk.common import ToolError

REASSESS_DAYS: Final[int] = 30
GOOD: Final[int] = 2
KINDS: Final[tuple[str, ...]] = ("technical", "leadership", "general")
CATEGORIES: Final[dict[str, int]] = {      # reason code -> priority category (1 is most urgent)
    "fact_unconfirmed": 1, "ownership_unclear": 1, "prerequisite_unmet": 2,
    "profile_gap": 3, "untested": 3, "untested_with_story": 3,
    "weak": 4, "weak_with_story": 4, "answer_old": 5}


@dataclass(frozen=True)
class Competency:
    """One thing a person can know or have done, with aliases, prerequisites and related competencies."""

    id: str
    name: str
    kind: str
    aliases: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    related: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fact:
    """A recorded fact about an engagement; `status` is confirmed, proposed or unsure; `ownership` is own, team
    or unclear."""

    engagement: str
    fact_id: str
    competencies: tuple[str, ...]
    status: str = "confirmed"
    ownership: str = "own"


@dataclass(frozen=True)
class Story:
    """A narrative about one engagement, with the facts it uses."""

    id: str
    engagement: str
    competencies: tuple[str, ...]
    done: bool = False
    ownership: str = "own"
    facts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Attempt:
    """One logged answer. `kind` is drill, quiz or lesson; `grade` is 0 weak, 1 some gaps, 2 good (a quiz:
    1 passed, 0 not passed); a lesson has no grade."""

    id: str
    competency: str
    day: date
    kind: str
    grade: int | None = None


@dataclass(frozen=True)
class Lead:
    """A stored resume line (by reference) that mentions a competency. It is a hint for a question, never
    evidence: it is not a fact and counts as no experience."""

    competency: str
    ref: str


@dataclass(frozen=True)
class Snapshot:
    """Everything the planner reads, as of one moment."""

    vocabulary: tuple[Competency, ...]
    facts: tuple[Fact, ...] = ()
    stories: tuple[Story, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    self_rated: dict[str, int] = field(default_factory=dict)
    leads: tuple[Lead, ...] = ()


@dataclass(frozen=True)
class Experience:
    """The distinct engagements that show a person did this."""

    engagements: tuple[str, ...]
    stories: tuple[str, ...]
    transferable: bool = False


@dataclass(frozen=True)
class Action:  # pylint: disable=too-many-instance-attributes
    """One suggestion. `evidence` and `observations` hold references like `story:s1`, `fact:e1/f1`,
    `attempt:a1`; the caller words the reply, this holds the reason."""

    competency: str
    type: str
    reason_code: str
    reason: str
    evidence: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    target: str | None = None
    age_days: int | None = None
    choices: tuple[str, ...] = ()
    transferable: bool = False
    self_rated: int | None = None
    leads: tuple[str, ...] = ()


def _seed(rows: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]]) -> tuple[Competency, ...]:
    return tuple(Competency(i, n, k, a, r, x) for i, n, k, a, r, x in rows)


SEED: Final[tuple[Competency, ...]] = _seed([
    ("containers", "Containers", "technical", ("docker",), (), ()),
    ("kubernetes", "Kubernetes", "technical", ("k8s",), ("containers",), ("ecs",)),
    ("ecs", "ECS", "technical", (), ("containers",), ("kubernetes",)),
    ("event-driven-design", "Event-driven design", "technical", (), (), ()),
    ("giving-feedback", "Giving feedback", "leadership", (), (), ()),
    ("conflict-resolution", "Resolving conflict", "leadership", (), ("giving-feedback",), ()),
    ("delegation", "Delegating work", "leadership", (), (), ()),
    ("negotiation", "Negotiation", "general", (), (), ()),
    ("budget-planning", "Budget planning", "general", (), (), ()),
])


def _by_id(vocabulary: tuple[Competency, ...]) -> dict[str, Competency]:
    return {c.id: c for c in vocabulary}


def _check_names(vocabulary: tuple[Competency, ...]) -> None:
    """Reject a duplicate id, an unknown kind or an alias that resolves to two competencies."""
    seen: dict[str, str] = {}
    for c in vocabulary:
        if c.kind not in KINDS:
            raise ToolError(f"{c.id}: kind must be one of {', '.join(KINDS)}")
        for name in (c.id, c.name, *c.aliases):
            owner = seen.setdefault(name.lower(), c.id)
            if owner != c.id:
                raise ToolError(f"The name {name!r} points at both {owner} and {c.id}")


def _check_links(vocabulary: tuple[Competency, ...]) -> None:
    known = _by_id(vocabulary)
    for c in vocabulary:
        for ref in (*c.requires, *c.related):
            if ref not in known:
                raise ToolError(f"{c.id} refers to {ref}, which does not exist")


def _find_cycle(vocabulary: tuple[Competency, ...]) -> list[str] | None:
    """A prerequisite cycle as a path, or None. Depth is bounded by the number of competencies."""
    known = _by_id(vocabulary)
    state: dict[str, int] = {}

    def visit(cid: str, path: list[str]) -> list[str] | None:
        if state.get(cid) == 1:
            return path[path.index(cid):] + [cid]
        if state.get(cid) == 2:
            return None
        state[cid] = 1
        for ref in known[cid].requires:
            found = visit(ref, [*path, cid])
            if found:
                return found
        state[cid] = 2
        return None

    for c in vocabulary:
        found = visit(c.id, [])
        if found:
            return found
    return None


def check_vocabulary(vocabulary: tuple[Competency, ...]) -> None:
    """Raise `ToolError` for a prerequisite cycle, an alias with two targets or a reference to nothing."""
    _check_names(vocabulary)
    _check_links(vocabulary)
    cycle = _find_cycle(vocabulary)
    if cycle:
        raise ToolError("Prerequisites form a loop: " + " -> ".join(cycle))


def resolve(vocabulary: tuple[Competency, ...], name: str) -> Competency | None:
    """The competency a name, id or alias stands for. Related competencies are not aliases."""
    wanted = name.strip().lower()
    for c in vocabulary:
        if wanted in (c.id, c.name.lower(), *(a.lower() for a in c.aliases)):
            return c
    return None


def _related(snapshot: Snapshot, cid: str) -> set[str]:
    """Related competencies, in either direction."""
    out = set(_by_id(snapshot.vocabulary)[cid].related)
    out.update(c.id for c in snapshot.vocabulary if cid in c.related)
    return out


def graded(snapshot: Snapshot, cid: str) -> list[Attempt]:
    """Graded drill answers for a competency, oldest first. Quizzes, lessons and self-ratings are not here."""
    rows = [a for a in snapshot.attempts if a.competency == cid and a.kind == "drill" and a.grade is not None]
    return sorted(rows, key=lambda a: (a.day, a.id))


def knows(snapshot: Snapshot, cid: str) -> bool:
    """Knowledge: a passed quiz or a good drill answer. It says nothing about work experience."""
    return any((a.kind == "quiz" and (a.grade or 0) >= 1) or (a.kind == "drill" and a.grade == GOOD)
               for a in snapshot.attempts if a.competency == cid)


def _story_fact_refs(snapshot: Snapshot, cid: str) -> set[tuple[str, str]]:
    refs = {(f.engagement, f.fact_id) for f in snapshot.facts if cid in f.competencies}
    for s in snapshot.stories:
        if cid in s.competencies:
            refs.update(s.facts)
    return refs


def _sound(fact: Fact) -> bool:
    return fact.status == "confirmed" and fact.ownership == "own"


def _unclear(snapshot: Snapshot, cid: str) -> tuple[str, tuple[str, ...], str] | None:
    """The first thing that stops evidence counting: (reason code, evidence refs, reason text), or None."""
    refs = _story_fact_refs(snapshot, cid)
    bad = sorted((f for f in snapshot.facts if (f.engagement, f.fact_id) in refs and not _sound(f)),
                 key=lambda f: (f.engagement, f.fact_id))
    if bad:
        keys = tuple(f"fact:{f.engagement}/{f.fact_id}" for f in bad)
        return ("fact_unconfirmed", keys,
                "A fact behind this is not confirmed yet, or it is not clear it was your own work. Ask which.")
    unclear = sorted(s.id for s in snapshot.stories if cid in s.competencies and s.ownership != "own")
    if unclear:
        return ("ownership_unclear", tuple(f"story:{s}" for s in unclear),
                "It is not clear how much of this story was your own work. Ask which part you did.")
    return None


def _direct_stories(snapshot: Snapshot, cid: str) -> list[Story]:
    return sorted((s for s in snapshot.stories if cid in s.competencies and s.ownership == "own"),
                  key=lambda s: s.id)


def experience(snapshot: Snapshot, cid: str) -> Experience:
    """Distinct engagements showing real use of the competency. Several stories on one engagement count once;
    unconfirmed or not-own evidence counts for nothing."""
    stories = _direct_stories(snapshot, cid)
    engagements = {f.engagement for f in snapshot.facts if cid in f.competencies and _sound(f)}
    engagements.update(s.engagement for s in stories)
    return Experience(tuple(sorted(engagements)), tuple(s.id for s in stories))


def _transferable(snapshot: Snapshot, cid: str) -> Experience:
    engagements: set[str] = set()
    stories: list[str] = []
    for other in sorted(_related(snapshot, cid)):
        exp = experience(snapshot, other)
        engagements.update(exp.engagements)
        stories.extend(exp.stories)
    return Experience(tuple(sorted(engagements)), tuple(sorted(stories)), True)


def _unmet(snapshot: Snapshot, cid: str, seen: frozenset[str] = frozenset()) -> list[str]:
    """Prerequisites without knowledge, deepest first (a prerequisite's own gaps come before it)."""
    known = _by_id(snapshot.vocabulary)
    out: list[str] = []
    for ref in known[cid].requires:
        if ref in seen or knows(snapshot, ref):
            continue
        out.extend(x for x in _unmet(snapshot, ref, seen | {cid}) if x not in out)
        if ref not in out:
            out.append(ref)
    return out


def _clarify(snapshot: Snapshot, cid: str) -> Action | None:
    found = _unclear(snapshot, cid)
    if not found:
        return None
    code, evidence, reason = found
    return Action(cid, "clarify_fact", code, reason, evidence=evidence)


def _teach(snapshot: Snapshot, cid: str) -> Action | None:
    if knows(snapshot, cid):
        return None
    unmet = _unmet(snapshot, cid)
    if not unmet:
        return None
    name = _by_id(snapshot.vocabulary)[cid].name
    return Action(unmet[0], "teach_prerequisite", "prerequisite_unmet",
                  f"Learn this first: it is needed before {name}.", target=cid)


def _story_action(snapshot: Snapshot, cid: str, code: str, reason: str, seen: tuple[str, ...]) -> Action | None:
    """A rehearse_story action from direct stories, else from related ones (marked transferable)."""
    exp = experience(snapshot, cid)
    transferable = not exp.stories
    if transferable:
        exp = _transferable(snapshot, cid)
    if not exp.stories:
        return None
    note = " It comes from related work, not this exact skill." if transferable else ""
    return Action(cid, "rehearse_story", code, reason + note, evidence=tuple(f"story:{s}" for s in exp.stories[:1]),
                  observations=seen, choices=exp.stories, transferable=transferable,
                  self_rated=snapshot.self_rated.get(cid))


def _latest_state(snapshot: Snapshot, cid: str, today: date, window: int) -> tuple[str, Attempt | None]:
    """How the competency stands: untested, weak, due or fine, with the latest graded answer."""
    rows = graded(snapshot, cid)
    if not rows:
        return "untested", None
    last = rows[-1]
    if (last.grade or 0) < GOOD:
        return "weak", last
    return ("due" if (today - last.day).days > window else "fine"), last


def _practice(snapshot: Snapshot, cid: str, state: str, last: Attempt | None, today: date) -> Action | None:
    name = _by_id(snapshot.vocabulary)[cid].name
    seen = (f"attempt:{last.id}",) if last else ()
    if state == "due" and last:
        age = (today - last.day).days
        return Action(cid, "reassess", "answer_old", f"Your last good answer on {name} was {age} days ago. "
                      "Try a fresh question to check it still holds.", observations=seen, age_days=age)
    if state == "weak":
        done = _story_action(snapshot, cid, "weak_with_story",
                             f"Your last answer on {name} had gaps. Rehearse a story you can use.", seen)
        return done or Action(cid, "practise_concept", "weak", f"Your last answer on {name} had gaps. "
                              "Practise it again.", observations=seen)
    if state == "untested":
        return _untested(snapshot, cid, name, seen)
    return None


def _untested(snapshot: Snapshot, cid: str, name: str, seen: tuple[str, ...]) -> Action:
    """No graded drill yet: rehearse a story if one exists; ask for an example if nothing is recorded (a gap in
    the record, whatever a quiz showed); otherwise practise."""
    rated = snapshot.self_rated.get(cid)
    done = _story_action(snapshot, cid, "untested_with_story",
                         f"You have not been tested on {name}, and you have a story for it.", seen)
    if done:
        return done
    if experience(snapshot, cid).engagements:
        return Action(cid, "practise_concept", "untested", f"You have not been tested on {name}.", self_rated=rated)
    leads = tuple(sorted({lead.ref for lead in snapshot.leads if lead.competency == cid}))
    note = " Your resume has lines that mention it." if leads else ""
    return Action(cid, "clarify_fact", "profile_gap", f"Nothing is recorded yet that shows you have used {name}. "
                  "Ask whether you have used it at work, and for a real example." + note,
                  self_rated=rated, leads=leads)


def _action(snapshot: Snapshot, cid: str, today: date, window: int) -> Action | None:
    """The single most urgent action for one competency."""
    early = _clarify(snapshot, cid) or _teach(snapshot, cid)
    if early:
        return early
    state, last = _latest_state(snapshot, cid, today, window)
    return _practice(snapshot, cid, state, last, today)


def _category(action: Action) -> int:
    return CATEGORIES[action.reason_code]


def plan(snapshot: Snapshot, today: date, focus: tuple[str, ...] = (), reassess_days: int = REASSESS_DAYS) -> list[Action]:
    """Ordered actions: factual blockers, unmet prerequisites, untested, observed weaknesses, due reassessments.
    Within a group, focused competencies first, then by id. A focus never skips a blocker."""
    actions: dict[tuple[str, str], Action] = {}
    for c in sorted(snapshot.vocabulary, key=lambda c: c.id):
        act = _action(snapshot, c.id, today, reassess_days)
        if act:
            actions.setdefault((act.type, act.competency), act)
    return sorted(actions.values(), key=lambda a: (_category(a), a.reason_code != "profile_gap",
                                                   a.competency not in focus, a.competency, a.type))
