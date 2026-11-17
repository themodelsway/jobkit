"""Tests for plugins/jobkit/src/jk/resumes/match_request.py: request validation, evidence references and the fixed
priority rules, and that the engine imports no database or command module."""
import ast
import copy
import unittest
from pathlib import Path

from jk import common
from jk.resumes import match_engine as me
from jk.resumes import match_facts as mf
from jk.resumes import match_request as mr
from tests.resumes.match.support import facts, request

FACTS = facts()


def problems(data) -> str:
    """The text of the error `parse_request` raises ('' when the request is valid)."""
    try:
        mr.parse_request(data, FACTS, me.BANDS)
    except common.ToolError as exc:
        return str(exc)
    return ""


def edited(index=None, **changes):
    """The valid request with one requirement (or the header) changed."""
    data = copy.deepcopy(request())
    target = data["requirements"][index] if index is not None else data
    target.update(changes)
    return data


class ValidationTests(unittest.TestCase):
    def test_valid_request_passes(self):
        self.assertEqual(problems(request()), "")

    def test_each_problem_alone_names_its_field(self):
        cases = {
            "requirements[1].id": edited(1, id="r1"),
            "requirements[0] (r1).category": edited(0, category="hobbies"),
            "requirements[0] (r1).priority": edited(0, priority="vital"),
            "requirements[0] (r1).level": edited(0, level="great"),
            "requirements[0] (r1).importance": edited(0, importance=0),
            "importance ": edited(0, importance=float("inf")),
            "requirements[0] (r1).confidence": edited(0, confidence=1.5),
            "requirements[1] (r2).evidence": edited(1, evidence=[]),
            "requirements[2] (r3).evidence": edited(2, evidence=["bullet:b1"]),
            "band: ": edited(band="intern"),
            "band_reason": edited(band_reason=""),
            "schema_version": edited(schema_version=2),
            "nothing to score": edited(requirements=[]),
        }
        for expected, data in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected.strip(), problems(data))

    def test_two_problems_are_reported_together(self):
        data = edited(0, category="hobbies")
        data["requirements"][1]["id"] = "r1"
        text = problems(data)
        self.assertIn("category", text)
        self.assertIn("used twice", text)

    def test_nothing_is_repaired(self):
        data = edited(0, level="great", importance=-1)
        before = copy.deepcopy(data)
        self.assertNotEqual(problems(data), "")
        self.assertEqual(data, before)

    def test_unknown_evidence_names_the_requirement(self):
        text = problems(edited(0, evidence=["bullet:nope"]))
        self.assertIn("requirements[0] (r1).evidence[0]", text)
        self.assertIn("no stored line", text)

    def test_shared_line_id_asks_for_the_company_form(self):
        self.assertIn("bullet:COMPANY_ID:dup", problems(edited(0, evidence=["bullet:dup"])))
        self.assertEqual(problems(edited(0, evidence=["bullet:acme:dup"])), "")
        self.assertEqual(mf.bullet_ref(FACTS, "acme", "dup"), "bullet:acme:dup")
        self.assertEqual(mf.bullet_ref(FACTS, "acme", "b1"), "bullet:b1")

    def test_other_reference_kinds(self):
        for ref in ("skill:k8s", "education:2", "certification:example certified coach - associate",
                    "role:acme-2"):
            with self.subTest(ref=ref):
                self.assertEqual(problems(edited(0, evidence=[ref])), "")
        for ref in ("education:3", "skill:Cobol", "certification:PMP", "role:nowhere", "thing:1", "plain"):
            with self.subTest(ref=ref):
                self.assertNotEqual(problems(edited(0, evidence=[ref])), "")

    def test_flag_needs_two_valid_readings(self):
        good = {"kind": "level", "readings": ["partial", "substantial"]}
        self.assertEqual(problems(edited(0, flag=good)), "")
        for bad in ({"kind": "level", "readings": ["partial", "partial"]}, {"kind": "mood", "readings": ["a", "b"]},
                    {"kind": "category", "readings": ["impact", "domain", "education"]},
                    {"kind": "priority", "readings": ["required", "vital"]}):
            with self.subTest(bad=bad):
                self.assertIn(".flag", problems(edited(0, flag=bad)))


class PriorityRuleTests(unittest.TestCase):
    def test_preferred_and_required_is_required(self):
        self.assertEqual(mr.settle_priority(("preferred", "required"), "nice to have"), "required")
        self.assertEqual(mr.settle_priority(("required", "preferred"), ""), "required")

    def test_required_and_critical_needs_must_have_wording(self):
        self.assertEqual(mr.settle_priority(("required", "critical"), "Kubernetes is a must have."), "critical")
        self.assertEqual(mr.settle_priority(("required", "critical"), "Kubernetes experience is expected."),
                         "required")

    def test_other_pairs_are_not_settled(self):
        self.assertIsNone(mr.settle_priority(("preferred", "critical"), "must"))

    def test_rules_settle_flags_on_a_request(self):
        data = edited(0, flag={"kind": "priority", "readings": ["preferred", "required"]})
        request_ = mr.parse_request(data, FACTS, me.BANDS)
        mr.apply_priority_rules(request_)
        self.assertEqual((request_.items[0].priority, request_.items[0].flag), ("required", None))
        self.assertEqual(len(request_.rules_applied), 1)


class BandChoiceTests(unittest.TestCase):
    def test_ambiguous_band_takes_the_lower_one(self):
        data = edited(band="senior-executive", band_alternatives=["executive"])
        request_ = mr.parse_request(data, FACTS, me.BANDS)
        band, note = mr.choose_band(request_)
        self.assertEqual(band, "executive")
        self.assertIn("lower", note)

    def test_single_band_has_no_assumption(self):
        self.assertEqual(mr.choose_band(mr.parse_request(request(), FACTS, me.BANDS)), ("mid-manager", None))


def imported_modules(source: str) -> set[str]:
    """Every module a source file imports; a relative import counts as part of the `jk` package."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(f"jk.{node.module or ''}" if node.level else node.module or "")
    return found


class EngineIsolationTests(unittest.TestCase):
    def test_engine_imports_no_database_or_command_module(self):
        imported = imported_modules(Path(me.__file__).read_text(encoding="utf-8"))
        self.assertFalse({m for m in imported if m == "jk" or m.startswith("jk.")}, imported)
        self.assertFalse({"sqlite3", "subprocess", "socket"} & imported)

    def test_the_check_sees_package_imports(self):
        imported = imported_modules("from jk import store\nimport jk.common\nfrom . import tables\n")
        self.assertEqual(imported, {"jk", "jk.common", "jk."})
