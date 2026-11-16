"""Tests for the `prep` commands in an answer style (STAR, CARL, SOAR): show, cheat sheet, set, done and validate."""
import json

from jk.interview import tables
from jk.user import profile
from tests.interview.support import PrepCase, run_prep


class StyleCase(PrepCase):
    """Answer styles on the prep commands (the story id is acme-topic-a)."""

    sid = "acme-topic-a"

    def set_default_style(self, style):
        data = profile.load()
        data["resume_root"] = str(self.home)
        data["answer_style"] = style
        profile.save(data)

    def fill(self, **fields):
        for name, text in fields.items():
            self.assertEqual(run_prep("set", self.sid, name, text)[0], 0, name)

    def stored(self):
        """The stored story exactly as the database holds it."""
        return json.dumps(tables.load_stories(), sort_keys=True)


class TestShowInAStyle(StyleCase):
    def setUp(self):
        super().setUp()
        self.fill(situation="Demand doubled.", task="Keep latency flat.", action="I resized.", result="Held.",
                  lessons="Measure first.", notes="n")

    def test_star_is_the_default_and_the_layout_is_the_old_one(self):
        _, out = run_prep("show", self.sid)
        for line in ("  situation: Demand doubled.", "  task: Keep latency flat.", "  action: I resized.",
                     "  result: Held.", "  lessons: Measure first.", "  notes: n"):
            self.assertIn(line, out)

    def test_soar_names_the_task_an_obstacle(self):
        _, out = run_prep("show", self.sid, "--style", "soar")
        self.assertIn("  obstacle: Keep latency flat.", out)
        self.assertNotIn("  task:", out)
        self.assertIn("  lessons: Measure first.", out)

    def test_carl_joins_the_challenge_and_shows_the_learning(self):
        _, out = run_prep("show", self.sid, "--style", "carl")
        self.assertIn("  challenge: Demand doubled. Keep latency flat.", out)
        self.assertIn("  learning: Measure first.", out)
        self.assertNotIn("  situation:", out)
        self.assertNotIn("  lessons:", out)

    def test_profile_default_applies_when_no_style_is_given(self):
        self.set_default_style("carl")
        self.assertIn("  challenge:", run_prep("show", self.sid)[1])
        self.assertIn("  situation:", run_prep("show", self.sid, "--style", "star")[1])

    def test_showing_in_every_style_leaves_the_stored_story_byte_identical(self):
        before = self.stored()
        for style in ("star", "soar", "carl", "star"):
            self.assertEqual(run_prep("show", self.sid, "--style", style)[0], 0)
            self.assertEqual(self.stored(), before, style)

    def test_unknown_style_fails_naming_the_three_and_changes_nothing(self):
        before = self.stored()
        code, out = run_prep("show", self.sid, "--style", "bogus")
        self.assertEqual(code, 1)
        for name in ("star", "soar", "carl"):
            self.assertIn(name, out)
        self.assertEqual(self.stored(), before)

    def test_spoken_versions_are_shown_as_written_with_a_note(self):
        self.fill(**{"spoken.60s": "I resized the fleet and held latency."})
        for style in ("star", "carl"):
            _, out = run_prep("show", self.sid, "--style", style)
            self.assertIn("  spoken 60s: I resized the fleet and held latency.", out)
            self.assertIn(f"not rearranged to {style}", out)

    def test_no_note_when_there_is_no_spoken_version(self):
        self.assertNotIn("not rearranged", run_prep("show", self.sid, "--style", "carl")[1])

    def test_styles_command_lists_the_three_with_their_parts(self):
        code, out = run_prep("styles")
        self.assertEqual(code, 0)
        self.assertIn("Challenge, Action, Result, Learning", out)
        self.assertIn("Situation, Obstacle, Action, Result", out)
        self.assertIn("In force: star", out)


class TestCheatSheetStyles(StyleCase):
    def setUp(self):
        super().setUp()
        self.fill(situation="Demand doubled.", task="Keep latency flat.", action="I resized.", result="Held.",
                  lessons="Measure first.", **{"spoken.60s": "I resized the fleet."})

    def md(self, *extra):
        code, out = run_prep("export", "--story", self.sid, "--format", "md", *extra)
        self.assertEqual(code, 0, out)
        return out

    def test_headings_follow_the_style(self):
        self.assertIn("## Task", self.md())
        soar = self.md("--style", "soar")
        self.assertIn("## Obstacle", soar)
        self.assertNotIn("## Task", soar)
        carl = self.md("--style", "carl")
        for heading in ("## Challenge", "## Learning"):
            self.assertIn(heading, carl)
        self.assertNotIn("## Lessons", carl)
        self.assertIn("Demand doubled. Keep latency flat.", carl)

    def test_star_and_soar_keep_a_lessons_section(self):
        self.assertIn("## Lessons", self.md())
        self.assertIn("## Lessons", self.md("--style", "soar"))

    def test_spoken_version_is_unchanged_with_a_note(self):
        carl = self.md("--style", "carl")
        self.assertIn("I resized the fleet.", carl)
        self.assertIn("not rearranged to carl", carl)


class TestSetByPartName(StyleCase):
    def test_learning_in_carl_is_saved_as_the_lessons_and_says_so(self):
        code, out = run_prep("set", self.sid, "learning", "Measure first.", "--style", "carl")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.story()["lessons"], "Measure first.")
        self.assertIn("lessons", out)

    def test_obstacle_in_soar_is_saved_as_the_task(self):
        code, out = run_prep("set", self.sid, "obstacle", "Vendor was late.", "--style", "soar")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.story()["task"], "Vendor was late.")
        self.assertIn("task", out)
        self.assertEqual(self.story()["status"], "draft")

    def test_a_part_of_another_style_is_refused_and_the_parts_are_listed(self):
        before = self.stored()
        code, out = run_prep("set", self.sid, "obstacle", "x", "--style", "carl")
        self.assertEqual(code, 1)
        self.assertIn("challenge, action, result, learning", out)
        self.assertEqual(self.stored(), before)

    def test_a_style_name_that_is_not_in_the_default_style_is_refused(self):
        code, out = run_prep("set", self.sid, "learning", "x")
        self.assertEqual(code, 1)
        self.assertIn("situation, task, action, result", out)

    def test_stored_field_names_keep_working_whatever_the_default(self):
        self.set_default_style("carl")
        self.assertEqual(run_prep("set", self.sid, "task", "Keep latency flat.")[0], 0)
        self.assertEqual(self.story()["task"], "Keep latency flat.")

    def test_challenge_over_an_empty_task_is_stored_as_the_situation(self):
        code, out = run_prep("set", self.sid, "challenge", "Demand doubled.", "--style", "carl")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.story()["situation"], "Demand doubled.")
        self.assertIn("situation", out)

    def test_challenge_over_a_task_is_refused_without_merge(self):
        self.fill(situation="Old.", task="Keep latency flat.")
        before = self.stored()
        code, out = run_prep("set", self.sid, "challenge", "New.", "--style", "carl")
        self.assertEqual(code, 1)
        self.assertIn("--merge", out)
        self.assertEqual(self.stored(), before)

    def test_merge_folds_the_task_into_the_challenge_and_says_so(self):
        self.fill(situation="Old.", task="Keep latency flat.")
        code, out = run_prep("set", self.sid, "challenge", "New.", "--style", "carl", "--merge")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.story()["situation"], self.story()["task"]), ("New.", None))
        self.assertIn("folded", out)

    def test_read_edit_merge_read_shows_exactly_the_edited_text(self):
        self.fill(situation="Demand doubled.", task="Keep latency flat.")
        shown = next(ln for ln in run_prep("show", self.sid, "--style", "carl")[1].splitlines()
                     if ln.startswith("  challenge:")).split(": ", 1)[1]
        edited = shown.replace("doubled", "tripled")
        self.assertEqual(run_prep("set", self.sid, "challenge", edited, "--style", "carl", "--merge")[0], 0)
        again = next(ln for ln in run_prep("show", self.sid, "--style", "carl")[1].splitlines()
                     if ln.startswith("  challenge:")).split(": ", 1)[1]
        self.assertEqual(again, edited)


class TestDoneInAStyle(StyleCase):
    def test_done_in_carl_accepts_a_story_with_no_task(self):
        self.fill(situation="S", action="A", result="R", lessons="L")
        code, out = run_prep("set", self.sid, "status", "done", "--style", "carl")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.story()["status"], "done")

    def test_done_in_star_refuses_the_same_story_and_names_the_task(self):
        self.fill(situation="S", action="A", result="R", lessons="L")
        code, out = run_prep("set", self.sid, "status", "done", "--style", "star")
        self.assertEqual(code, 1)
        self.assertIn("task", out)
        self.assertEqual(self.story()["status"], "draft")

    def test_done_in_carl_without_learning_names_it_and_leaves_the_status(self):
        self.fill(situation="S", task="T", action="A", result="R")
        code, out = run_prep("set", self.sid, "status", "done", "--style", "carl")
        self.assertEqual(code, 1)
        self.assertIn("learning", out)
        self.assertEqual(self.story()["status"], "draft")

    def test_the_profile_default_decides_when_no_style_is_given(self):
        self.fill(situation="S", task="T", action="A", result="R")
        self.set_default_style("carl")
        self.assertEqual(run_prep("set", self.sid, "status", "done")[0], 1)
        self.set_default_style("star")
        self.assertEqual(run_prep("set", self.sid, "status", "done")[0], 0)


class TestValidateInAStyle(StyleCase):
    def test_changing_the_default_never_fails_validation_for_done_stories(self):
        self.fill_star(self.sid)
        self.assertEqual(run_prep("set", self.sid, "status", "done")[0], 0)
        self.set_default_style("carl")
        code, out = run_prep("validate")
        self.assertEqual(code, 0, out)
        self.assertIn("Learning is empty in carl", out)
        self.assertIn("0 error(s)", out)

    def test_done_in_carl_without_a_task_validates_under_star_with_a_warning(self):
        self.fill(situation="S", action="A", result="R", lessons="L")
        self.assertEqual(run_prep("set", self.sid, "status", "done", "--style", "carl")[0], 0)
        code, out = run_prep("validate", "--style", "star")
        self.assertEqual(code, 0, out)
        self.assertIn("Task is empty in star", out)

    def test_a_done_story_with_its_action_emptied_still_fails_in_every_style(self):
        self.fill_star(self.sid)
        self.assertEqual(run_prep("set", self.sid, "status", "done")[0], 0)
        run_prep("set", self.sid, "action", "")
        for style in ("star", "soar", "carl"):
            self.assertEqual(run_prep("validate", "--style", style)[0], 1, style)
