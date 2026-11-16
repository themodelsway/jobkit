"""Tests for interview/styles.py: the three styles, the part mapping, the challenge save rule and the style in force."""
import copy
import unittest

from jk.common import ToolError
from jk.interview import styles
from jk.user import profile
from tests.support import HomeCase


def story(**fields):
    """A story with the stored fields a style reads (everything else empty)."""
    base = {"situation": None, "task": None, "action": None, "result": None, "lessons": None}
    base.update(fields)
    return base


def full(**fields):
    """A story filled in every field a style reads."""
    return story(**{"situation": "Sit.", "task": "Task.", "action": "Act.", "result": "Res.", "lessons": "Learn.",
                    **fields})


class TestRegistry(unittest.TestCase):
    def test_exactly_three_styles_in_order(self):
        self.assertEqual(styles.names(), ("star", "soar", "carl"))

    def test_parts_in_order(self):
        order = {name: [p.label for p in styles.get(name).parts] for name in styles.names()}
        self.assertEqual(order["star"], ["Situation", "Task", "Action", "Result"])
        self.assertEqual(order["soar"], ["Situation", "Obstacle", "Action", "Result"])
        self.assertEqual(order["carl"], ["Challenge", "Action", "Result", "Learning"])

    def test_listing_shows_parts_and_a_use_for_each_style(self):
        lines = styles.listing()
        self.assertEqual(len(lines), 3)
        self.assertIn("Situation, Task, Action, Result", lines[0])
        self.assertIn("Challenge, Action, Result, Learning", lines[2])
        self.assertTrue(all(":" in line and line.split(": ", 1)[1] for line in lines))

    def test_unknown_style_names_the_three(self):
        with self.assertRaises(ToolError) as caught:
            styles.get("bogus")
        for name in ("star", "soar", "carl"):
            self.assertIn(name, str(caught.exception))


class TestMapping(unittest.TestCase):
    def test_obstacle_is_the_task_field(self):
        stored = story(task="The vendor was late.")
        self.assertEqual(styles.part_text(styles.part_for("soar", "obstacle"), stored), "The vendor was late.")

    def test_challenge_is_situation_then_task(self):
        stored = story(situation="Demand doubled.", task="Keep latency flat.")
        self.assertEqual(styles.part_text(styles.part_for("carl", "challenge"), stored),
                         "Demand doubled. Keep latency flat.")

    def test_challenge_with_only_one_piece_has_no_stray_separator(self):
        self.assertEqual(styles.part_text(styles.part_for("carl", "challenge"), story(task="Only this.")), "Only this.")

    def test_learning_is_the_lessons_field(self):
        self.assertEqual(styles.part_text(styles.part_for("carl", "learning"), story(lessons="Measure first.")),
                         "Measure first.")

    def test_action_and_result_map_to_themselves_in_every_style(self):
        stored = story(action="Built it.", result="It shipped.")
        for name in styles.names():
            self.assertEqual(styles.part_text(styles.part_for(name, "action"), stored), "Built it.")
            self.assertEqual(styles.part_text(styles.part_for(name, "result"), stored), "It shipped.")

    def test_a_part_of_another_style_lists_the_parts_that_belong(self):
        with self.assertRaises(ToolError) as caught:
            styles.part_for("carl", "situation")
        self.assertIn("challenge, action, result, learning", str(caught.exception))

    def test_reading_never_changes_the_story(self):
        stored = full()
        before = copy.deepcopy(stored)
        for name in styles.names():
            for part in styles.get(name).parts:
                styles.part_text(part, stored)
            styles.missing_parts(name, stored)
        self.assertEqual(stored, before)


class TestCompleteness(unittest.TestCase):
    def test_carl_is_complete_without_a_task(self):
        stored = full(task=None)
        self.assertEqual(styles.missing_parts("carl", stored), [])
        self.assertEqual([p.name for p in styles.missing_parts("star", stored)], ["task"])

    def test_carl_without_lessons_names_the_learning(self):
        self.assertEqual([p.name for p in styles.missing_parts("carl", full(lessons=None))], ["learning"])

    def test_star_needs_no_lessons(self):
        self.assertEqual(styles.missing_parts("star", full(lessons=None)), [])

    def test_whitespace_is_not_text(self):
        self.assertEqual([p.name for p in styles.missing_parts("soar", full(task="   "))], ["obstacle"])

    def test_complete_styles(self):
        self.assertEqual(styles.complete_styles(full()), ["star", "soar", "carl"])
        self.assertEqual(styles.complete_styles(full(task=None)), ["carl"])
        self.assertEqual(styles.complete_styles(full(action=None)), [])

    def test_next_prompt_in_soar_asks_what_stood_in_the_way(self):
        prompt = styles.next_prompt("soar", story(situation="Sit.", action="Act.", result="Res."))
        self.assertIn("stood in the way", prompt)
        self.assertNotIn("task", prompt.lower())

    def test_next_prompt_in_carl_asks_what_was_learned(self):
        prompt = styles.next_prompt("carl", full(lessons=None))
        self.assertIn("learn", prompt)
        self.assertIn("differently", prompt)

    def test_next_prompt_is_none_when_complete(self):
        self.assertIsNone(styles.next_prompt("star", full()))


class TestSavePart(unittest.TestCase):
    def test_challenge_with_empty_task_is_stored_as_the_situation(self):
        stored = story()
        message = styles.save_part(stored, "carl", "challenge", "Demand doubled.")
        self.assertEqual(stored["situation"], "Demand doubled.")
        self.assertIn("situation", message)

    def test_challenge_over_a_task_without_merge_is_refused_and_stores_nothing(self):
        stored = story(situation="Old.", task="Keep latency flat.")
        before = copy.deepcopy(stored)
        with self.assertRaises(ToolError) as caught:
            styles.save_part(stored, "carl", "challenge", "New.")
        self.assertEqual(stored, before)
        self.assertIn("--merge", str(caught.exception))
        self.assertIn("separately", str(caught.exception))

    def test_merge_stores_the_situation_empties_the_task_and_says_so(self):
        stored = story(situation="Old.", task="Keep latency flat.")
        message = styles.save_part(stored, "carl", "challenge", "New.", merge=True)
        self.assertEqual((stored["situation"], stored["task"]), ("New.", None))
        self.assertIn("folded", message)

    def test_read_edit_merge_read_gives_exactly_the_edited_text(self):
        stored = story(situation="Demand doubled.", task="Keep latency flat.")
        challenge = styles.part_for("carl", "challenge")
        shown = styles.part_text(challenge, stored)
        edited = shown.replace("doubled", "tripled")
        styles.save_part(stored, "carl", "challenge", edited, merge=True)
        self.assertEqual(styles.part_text(challenge, stored), edited)
        self.assertEqual(styles.part_text(challenge, stored).count("Keep latency flat"), 1)

    def test_other_parts_write_to_the_field_they_map_to(self):
        stored = story()
        self.assertIn("task", styles.save_part(stored, "soar", "obstacle", "Late vendor."))
        styles.save_part(stored, "carl", "learning", "Measure first.")
        self.assertEqual((stored["task"], stored["lessons"]), ("Late vendor.", "Measure first."))

    def test_a_part_that_is_not_in_the_style_is_refused(self):
        with self.assertRaises(ToolError):
            styles.save_part(story(), "star", "learning", "x")


class TestStyleInForce(HomeCase):
    def set_default(self, value):
        data = profile.load()
        data["resume_root"] = str(self.home)
        data["answer_style"] = value
        profile.save(data)

    def test_nothing_chosen_is_star(self):
        self.assertEqual(styles.in_force(), "star")

    def test_profile_default(self):
        self.set_default("carl")
        self.assertEqual(styles.in_force(), "carl")

    def test_session_before_profile(self):
        self.set_default("star")
        self.assertEqual(styles.in_force(session="soar"), "soar")

    def test_option_before_session_and_profile(self):
        self.set_default("carl")
        self.assertEqual(styles.in_force("star", session="soar"), "star")

    def test_unknown_option_is_refused(self):
        with self.assertRaises(ToolError):
            styles.in_force("bogus")

    def test_an_option_leaves_the_stored_default_alone(self):
        self.set_default("carl")
        styles.in_force("soar")
        self.assertEqual(profile.answer_style(), "carl")
