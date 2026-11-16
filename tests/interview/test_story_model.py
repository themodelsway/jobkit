"""Pins the exact messages and ordering of story_model.validate_* and the markdown/search output.
Messages and their order are part of the prep.py contract (the skills quote them). Run: uv run python -m unittest discover -s tests -t ."""
import copy
import unittest


from jk.interview import story_model as sm

ENG = {"id": "e1", "title": "T", "my_role": "lead", "counters": {}, "people": [], "facts": [
    {"id": "f1", "text": "cut cost by 30%", "basis": "stated"},
    {"id": "f2", "text": "about 5000 users", "basis": "unsure"},
    {"id": "f3", "text": "x", "basis": "verified-doc"},
    {"id": "f1", "text": "", "basis": "bogus"}],
    "decisions": [{"id": "d1", "what": "", "ownership": "boss"},
                  {"id": "d2", "what": "use a queue", "why": "scale", "alternatives": ["polling", "webhooks"],
                   "tradeoffs": "ordering", "ownership": "mine"}]}


def story(**kw):
    base = {"id": "s1", "company": "c", "theme": "t", "headline": "H", "company_name": "C"}
    return sm.normalize_story({**base, **kw})


def eng():
    return sm.normalize_engagement(copy.deepcopy(ENG))


class ValidateTests(unittest.TestCase):
    def test_empty_story_has_no_issues(self):
        self.assertEqual(sm.validate_story(story()), [])

    def test_done_without_star_text(self):
        self.assertEqual(sm.validate_story(story(status="done")), [
            ("error", "s1: cannot be done, still empty: situation, task, action, result"),
            ("warn", "s1: no engagement linked (facts and decisions are not tracked for this story)")])

    def test_numbers_and_voice_warnings_in_order(self):
        s = story(status="draft", situation="We did it", action="we built our thing for us, I did one",
                  result="Saved $2M and 45% and 99%")
        self.assertEqual(sm.validate_story(s), [
            ("warn", "s1: no engagement linked (facts and decisions are not tracked for this story)"),
            ("warn", "s1: number $2M in the text has no metric or fact behind it"),
            ("warn", "s1: number 45% in the text has no metric or fact behind it"),
            ("warn", "s1: number 99% in the text has no metric or fact behind it"),
            ("warn", "s1: action says 'we/our' 3 times and 'I' 1 times: make your own part clear")])

    def test_links_metrics_spoken_and_follow_ups_in_order(self):
        s = story(status="done", engagement="e1", uses_facts=["f1", "f2", "zz"], situation="s", task="t",
                  action="a", result="r", follow_ups=["q1", "q2"],
                  metrics=[{"name": "", "value": "30%", "basis": "bad"}],
                  spoken={"60s": "word " * 200, "2min": "x " * 400})
        self.assertEqual(sm.validate_story(s, eng()), [
            ("error", "s1: fact f1 is 'bogus' and cannot back a story: confirm it (fact set --basis stated) or unlink it"),
            ("error", "s1: fact f2 is 'unsure' and cannot back a story: confirm it (fact set --basis stated) or unlink it"),
            ("error", "s1: uses fact zz, which is not in the engagement"),
            ("error", "s1: metric '' basis must be one of measured, estimated, stated, unknown"),
            ("error", "s1: every metric needs a name and a value"),
            ("warn", "s1: spoken 60s is 200 words; aim for 160 or fewer"),
            ("warn", "s1: spoken 2min is 400 words; aim for 330 or fewer"),
            ("warn", "s1: 2 follow-up(s) still open")])

    def test_unlinked_engagement_and_bad_status(self):
        s = story(status="weird", engagement="nope", uses_facts=["f1"])
        self.assertEqual([m for _, m in sm.validate_story(s)][:2], [
            "s1: status must be one of empty, draft, done", "s1: linked engagement nope does not exist"])

    def test_never_say_is_case_insensitive(self):
        s = story(status="draft", situation="Our Secret sauce", never_say=["SECRET"])
        self.assertIn(("error", "s1: text contains a never_say term: 'SECRET'"), sm.validate_story(s))

    def test_estimate_must_be_hedged(self):
        s = story(status="draft", result="Cut 45% of cost", metrics=[{"name": "c", "value": "45%", "basis": "estimated"}])
        self.assertIn(("warn", "s1: number 45% is an estimate: say 'estimated' or 'about' when you quote it"),
                      sm.validate_story(s))
        s["result"] = "Cut about 45% of cost"
        self.assertEqual([m for lvl, m in sm.validate_story(s) if "estimate" in m], [])

    def test_a_number_needs_the_exact_number_behind_it(self):
        s = story(status="draft", result="Cut 10% of cost.", metrics=[{"name": "c", "value": "100%", "basis": "measured"}])
        self.assertIn(("warn", "s1: number 10% in the text has no metric or fact behind it"), sm.validate_story(s))
        s["result"] = "Cut 100% of cost."
        self.assertEqual([m for _, m in sm.validate_story(s) if "number" in m], [])

    def test_the_hedge_must_be_in_the_same_sentence_or_part(self):
        s = story(status="draft", situation="About forty people worked there", result="Cut 45% of cost",
                  metrics=[{"name": "c", "value": "45%", "basis": "estimated"}])
        self.assertIn(("warn", "s1: number 45% is an estimate: say 'estimated' or 'about' when you quote it"),
                      sm.validate_story(s))

    def test_engagement_validation(self):
        self.assertEqual(sm.validate_engagement(eng()), [
            ("error", "e1.f3: a verified-doc fact needs a source URL"),
            ("error", "e1: duplicate fact id f1"),
            ("error", "e1.f1: fact has no text"),
            ("error", "e1.f1: basis must be one of stated, estimate, unsure, verified-doc, proposed"),
            ("error", "e1.d1: ownership must be one of mine, team, client, shared, unsure"),
            ("error", "e1.d1: decision has no 'what'")])


def levels(issues, level):
    """The messages of one level, without the story id."""
    return [m.split(": ", 1)[1] for lvl, m in issues if lvl == level]


class StyleValidationTests(unittest.TestCase):
    """The done rule per style; fact, metric, hedging and 'we versus I' checks do not depend on the style."""

    def test_marking_done_in_star_needs_the_task(self):
        s = story(status="done", situation="S", action="A", result="R", lessons="L")
        errors = levels(sm.validate_story(s, style="star", marking=True), "error")
        self.assertEqual(errors, ["cannot be done, still empty: task"])

    def test_marking_done_in_soar_names_the_obstacle(self):
        s = story(status="done", situation="S", action="A", result="R")
        errors = levels(sm.validate_story(s, style="soar", marking=True), "error")
        self.assertEqual(errors, ["cannot be done, still empty: obstacle"])

    def test_marking_done_in_soar_accepts_the_task_field_as_the_obstacle(self):
        s = story(status="done", situation="S", task="T", action="A", result="R")
        self.assertEqual(levels(sm.validate_story(s, style="soar", marking=True), "error"), [])

    def test_marking_done_in_carl_needs_no_task_but_needs_learning(self):
        s = story(status="done", situation="S", action="A", result="R", lessons="L")
        self.assertEqual(levels(sm.validate_story(s, style="carl", marking=True), "error"), [])
        s["lessons"] = None
        self.assertEqual(levels(sm.validate_story(s, style="carl", marking=True), "error"),
                         ["cannot be done, still empty: learning"])

    def test_a_task_alone_is_a_challenge(self):
        s = story(status="done", task="T", action="A", result="R", lessons="L")
        self.assertEqual(levels(sm.validate_story(s, style="carl", marking=True), "error"), [])

    def test_done_in_carl_without_a_task_stays_valid_when_star_is_in_force(self):
        s = story(status="done", situation="S", action="A", result="R", lessons="L")
        issues = sm.validate_story(s, style="star")
        self.assertEqual(levels(issues, "error"), [])
        self.assertIn("Task is empty in star", levels(issues, "warn"))

    def test_existing_done_stories_without_lessons_pass_under_a_carl_default(self):
        s = story(status="done", situation="S", task="T", action="A", result="R")
        issues = sm.validate_story(s, style="carl")
        self.assertEqual(levels(issues, "error"), [])
        self.assertIn("Learning is empty in carl", levels(issues, "warn"))

    def test_a_done_story_complete_in_no_style_still_fails(self):
        s = story(status="done", situation="S", task="T", result="R", lessons="L")       # action emptied
        for style in ("star", "soar", "carl"):
            self.assertEqual(levels(sm.validate_story(s, style=style), "error")[0].split(": ")[0],
                             "cannot be done, still empty", style)

    def test_estimated_figure_without_hedging_warns_in_every_style(self):
        s = story(status="draft", result="Cut 45% of cost", metrics=[{"name": "c", "value": "45%", "basis": "estimated"}])
        for style in ("star", "soar", "carl"):
            self.assertIn("number 45% is an estimate: say 'estimated' or 'about' when you quote it",
                          levels(sm.validate_story(s, style=style), "warn"), style)

    def test_a_number_in_the_learning_is_checked_only_when_carl_is_in_force(self):
        s = story(status="draft", lessons="Cut 45% of cost")
        self.assertEqual([m for m in levels(sm.validate_story(s, style="star"), "warn") if "45%" in m], [])
        self.assertEqual(len([m for m in levels(sm.validate_story(s, style="carl"), "warn") if "45%" in m]), 1)

    def test_we_versus_i_warning_applies_in_every_style(self):
        s = story(status="draft", action="we built our thing for us, I did one")
        for style in ("star", "soar", "carl"):
            self.assertIn("action says 'we/our' 3 times and 'I' 1 times: make your own part clear",
                          levels(sm.validate_story(s, style=style), "warn"), style)

    def test_spoken_limits_are_the_same_in_every_style(self):
        s = story(status="draft", spoken={"60s": "word " * 200, "2min": None})
        for style in ("star", "soar", "carl"):
            self.assertIn("spoken 60s is 200 words; aim for 160 or fewer", levels(sm.validate_story(s, style=style), "warn"))

    def test_never_say_is_checked_in_the_learning_under_carl(self):
        s = story(status="draft", lessons="Our secret sauce", never_say=["secret"])
        self.assertEqual(levels(sm.validate_story(s, style="star"), "error"), [])
        self.assertEqual(levels(sm.validate_story(s, style="carl"), "error"), ["text contains a never_say term: 'secret'"])


class HelperTests(unittest.TestCase):
    def test_next_id_never_reuses_removed_ids(self):
        e = {"facts": [{"id": "f1"}, {"id": "f2"}]}
        self.assertEqual(sm.next_id(e, "facts", "f"), "f3")
        e["facts"].pop()
        self.assertEqual(sm.next_id(e, "facts", "f"), "f4")

    def test_normalize_keeps_existing_content(self):
        s = sm.normalize_story({"id": "x", "situation": "kept", "spoken": {"60s": "hi"}})
        self.assertEqual((s["situation"], s["spoken"], s["status"], s["metrics"]), ("kept", {"60s": "hi", "2min": None}, "empty", []))

    def test_render_markdown_sections(self):
        s = story(status="draft", situation="S", metrics=[{"name": "n", "value": "1", "basis": "stated", "note": "q"}],
                  spoken={"60s": "one two three"}, likely_questions=["why?"], never_say=["x"], follow_ups=["f"])
        md = sm.render_story_md(s, eng())
        for expected in ("# s1: H", "## Situation\nS", "- n: 1 (stated) - q", "## Spoken (60s, 3 words)\none two three",
                         "- why?", "## Unsure (say 'I believe' or leave out)\n- about 5000 users",
                         "- use a queue - why: scale; alternatives: polling, webhooks; trade-offs: ordering", "## Open follow-ups\n- f"):
            self.assertIn(expected, md)
        self.assertTrue(md.endswith("\n"))

    def test_search_snippets(self):
        s = story(situation="x" * 60 + " batch size matters " + "y" * 80)
        hits = sm.search([s], [eng()], "batch size")
        self.assertEqual(hits[0][:3], ("story", "s1", "situation"))
        self.assertTrue(hits[0][3].startswith("..."))
        self.assertEqual([h[:3] for h in sm.search([], [eng()], "a queue")], [("engagement", "e1", "decision d2.what")])


if __name__ == "__main__":
    unittest.main()
