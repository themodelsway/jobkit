"""The match-score part of the resume-workflows skill and its rubric file."""
import json
import re
import unittest

from jk.resumes import match_engine as me
from jk.resumes import match_score as ms
from tests.support import PLUGIN_ROOT

SKILL = PLUGIN_ROOT / "skills" / "resume-workflows"


def section() -> list[str]:
    """Lines of the match section of the skill."""
    lines = (SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith("## Rating how well the resume matches"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    return lines[start:end]


class SkillSectionTests(unittest.TestCase):
    def test_no_question_to_the_user_while_scoring(self):
        for line in section():
            if line.strip().startswith(">"):
                self.assertNotIn("?", line, line)

    def test_steps_run_in_order(self):
        text = "\n".join(section())
        positions = [text.index(x) for x in ("match-score extract", "match-score check", "match-score run",
                                             "lead profile show", "profile open add")]
        self.assertEqual(positions, sorted(positions))

    def test_the_skill_forbids_questions_and_calls_it_an_estimate(self):
        text = "\n".join(section())
        self.assertIn("never ask the user anything", text)
        self.assertIn("not the score any employer's tracking software gives", text)
        self.assertIn("This feature is an early preview", text)
        self.assertNotIn("ATS", text)

    def test_the_rubric_is_named_from_the_skill_folder(self):
        self.assertIn("`match-rubric.md` (in this skill's folder)", "\n".join(section()))


class RubricTests(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / "match-rubric.md").read_text(encoding="utf-8")

    def test_it_is_addressed_to_the_agent_not_to_an_app(self):
        self.assertIn("This file is for the agent, not the user.", self.text)

    def test_version_line_equals_the_engine_version(self):
        found = re.search(r"^Rubric version: (\S+)$", self.text, re.M)
        self.assertIsNotNone(found)
        self.assertEqual(found.group(1), me.RUBRIC_VERSION)

    def test_five_examples_cover_different_dimensions(self):
        titles = re.findall(r"^### Example \d: (.+)$", self.text, re.M)
        self.assertEqual(len(titles), 5, titles)
        for word in ("people leadership", "impact", "domain", "skill", "field other than engineering"):
            self.assertTrue(any(word in t for t in titles), word)

    def test_it_uses_the_engine_vocabulary(self):
        for name in (*me.CATEGORIES, *me.LEVELS, *me.PRIORITIES, *me.BAND_ORDER):
            self.assertIn(f"`{name}`", self.text, name)

    def test_the_agreed_rules_are_written_down(self):
        for phrase in ("Mentoring four engineers is not leading a team", "\"Managed\" and \"led\" both count",
                       "not shown in your profile yet", "Never ask the user anything"):
            self.assertIn(phrase, self.text)

    def test_the_request_example_is_accepted_by_the_checker(self):
        block = re.search(r"```json\n(.*?)```", self.text, re.S).group(1)
        data = json.loads(block)
        self.assertEqual(data["schema_version"], 1)
        self.assertIn(data["band"], me.BANDS)
        self.assertIn(data["requirements"][0]["category"], me.CATEGORIES)
        self.assertIn(data["requirements"][0]["flag"]["kind"], ("level", "category", "priority"))

    def test_the_commands_named_exist(self):
        words = {"extract", "check", "run", "list", "show"}
        parser = ms.build_parser()
        names = set(next(a.choices for a in parser._actions if hasattr(a, "choices") and a.choices))
        self.assertTrue(words <= names)
