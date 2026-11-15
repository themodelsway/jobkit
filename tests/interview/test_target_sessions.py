"""Sessions and the readiness report for a researched company (`--target`), and the style each answer records.
All data is fictional. Run: uv run python -m unittest discover -s tests -t ."""
import json
import random
from datetime import date
from unittest import mock

from jk import records, store
from jk.interview import readiness, sessions, tables
from jk.interview import target_tables as tt
from jk.user import profile as up
from tests.interview.test_sessions import SessionCase
from tests.interview.test_targets import fact, store_company


def story(sid, theme="other", status="draft", action=""):
    """A fictional story with the fields the queue and the matching read."""
    return {"id": sid, "company": "acme", "company_name": "Acme", "theme": theme, "headline": sid,
            "metrics_on_resume": [], "anchor_bullets": [], "situation": None, "task": None, "action": action or None,
            "result": None, "metric": None, "lessons": None, "notes": None, "follow_ups": [], "status": status,
            "also_themes": []}


class TargetCase(SessionCase):
    def setUp(self):
        super().setUp()
        tables.replace_stories({"stories": [
            story("s1"), story("s2", theme="mentoring"), story("s3", action="We met a hard deadline."),
            story("s4", theme="delivery"), story("s5")]})
        self.company = store_company(
            fact("v1", name="Growth", themes=["mentoring", "delivery"], hints=[]),
            fact("v2", name="Pace", themes=["delivery"], hints=["deadline"]),
            fact("v3", name="Judgment", themes=[], hints=[]),
            fact("q3", kind="question", value="v3", wording="Tell me about a hard call."),
            fact("g1", kind="grading", wording="Interviewers score ownership of the result."))

    def started(self, *extra):
        code, out, err = self.cli(sessions.main, "new", "Company prep", "--mode", "stories", *extra)
        self.assertEqual(code, 0, err)
        return out.split("Started session ")[1].split(" ")[0], out

    def queue(self, sid):
        return [q["id"] for q in self.session(sid)["queue"]]

    def log(self, sid, item, *extra):
        return self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "An answer.", *extra)


class CompanySessionTests(TargetCase):
    def test_company_and_style_are_recorded_and_shown(self):
        sid, _ = self.started("--target", "company x", "--style", "soar")
        session = self.session(sid)
        self.assertEqual((session["target"], session["style"]), ("Company X", "soar"))
        self.assertIn("style soar  company Company X", self.cli(sessions.main, "list")[1])
        out = self.cli(sessions.main, "resume", sid)[1]
        self.assertIn("style: soar | company: Company X", out)

    def test_unknown_company_or_style_creates_no_session(self):
        for extra in (("--target", "Nobody"), ("--style", "best")):
            code, _, _ = self.cli(sessions.main, "new", "x", "--mode", "stories", *extra)
            self.assertEqual(code, 1)
        self.assertIn("No sessions yet", self.cli(sessions.main, "list")[1])

    def test_without_target_no_company_is_stored_whatever_the_default(self):
        up.save({"resume_root": "x", "target_company": "Company X", "answer_style": "carl"})
        sid, _ = self.started()
        self.assertEqual((self.session(sid)["target"], self.session(sid)["style"]), (None, "carl"))

    def test_matching_items_first_more_values_first_and_nothing_removed(self):
        sid, out = self.started("--target", "Company X")
        self.assertEqual(self.queue(sid), ["s4", "s2", "s3", "s1", "s5"])
        self.assertIn("s4: Growth (theme), Pace (theme)", out)
        self.assertIn("s3: Pace (word)", out)

    def test_random_order_shuffles_only_inside_each_group(self):
        for seed in range(5):
            random.seed(seed)
            sid, _ = self.started("--target", "Company X", "--order", "random")
            queue = self.queue(sid)
            self.assertEqual(set(queue[:2]), {"s2", "s4"})
            self.assertEqual(queue[2], "s3")
            self.assertEqual(set(queue[3:]), {"s1", "s5"})

    def test_count_keeps_the_best_matches(self):
        sid, _ = self.started("--target", "Company X", "--count", "3")
        self.assertEqual(self.queue(sid), ["s4", "s2", "s3"])

    def test_nothing_matching_still_creates_the_session(self):
        store_company(fact("v9", name="Other", themes=["nothing-here"], hints=[]), name="Other Co")
        sid, out = self.started("--target", "Other Co")
        self.assertEqual(len(self.queue(sid)), 5)
        self.assertIn("No story or leadership question in this queue matches Other Co yet.", out)

    def test_architecture_cards_keep_their_order(self):
        plain = self.new_session()
        code, out, err = self.cli(sessions.main, "new", "Cards", "--count", "3", "--target", "Company X")
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual(self.session(sid)["queue"], self.session(plain)["queue"])
        self.assertIn("does not change the order of architecture cards", out)

    def test_with_a_job_description_cards_keep_their_places_and_stories_are_ordered(self):
        mixed = [{"id": "c1", "kind": "card"}, {"id": "s1", "kind": "story"}, {"id": "c2", "kind": "card"},
                 {"id": "s4", "kind": "story"}]
        ordered, note = sessions.session_company.order(mixed, self.company, False)
        self.assertEqual([q["id"] for q in ordered], ["c1", "s4", "c2", "s1"])
        self.assertIsNone(note)


class SessionStyleShownTests(TargetCase):
    def test_next_story_is_shown_in_the_session_style(self):
        sid, out = self.started("--target", "Company X", "--style", "carl")
        self.assertIn("style: carl", out)
        self.assertNotIn("style: star", out)
        out = self.cli(sessions.main, "resume", sid, "--style", "soar")[1]
        self.assertIn("style: soar", out.split("Next item")[1])
        self.cli(sessions.main, "close", sid)
        out = self.cli(sessions.main, "reopen", sid)[1]
        self.assertIn("style: soar", out.split("Next item")[1])

    def test_session_style_wins_over_the_profile_default(self):
        up.save({"resume_root": "x", "answer_style": "star"})
        _, out = self.started("--style", "carl")
        self.assertIn("style: carl", out.split("Next item")[1])


class NoneFoundCompanyTests(TargetCase):
    def setUp(self):
        super().setUp()
        tt.save_company({"key": "small co", "name": "Small Co", "outcome": "none found",
                         "researched": date.today().isoformat(), "style": None, "style_basis": None,
                         "style_facts": [], "facts": []})

    def test_company_commands_refuse_it_and_say_to_practise_without(self):
        for main, argv in ((sessions.main, ["new", "x", "--mode", "stories", "--target", "Small Co"]),
                           (readiness.main, ["--target", "Small Co"])):
            code, _, err = self.cli(main, *argv)
            self.assertEqual(code, 1)
            self.assertIn("Practise without the company", err)
        self.assertIn("No sessions yet", self.cli(sessions.main, "list")[1])


class CompanyResumeTests(TargetCase):
    def test_resume_shows_emphasis_style_and_values_to_cover(self):
        sid, _ = self.started("--target", "Company X")
        out = self.cli(sessions.main, "resume", sid)[1]
        self.assertIn("Values still to cover:", out)
        self.assertIn("Judgment (needs your judgment)", out)
        self.assertIn("Q: Tell me about a hard call.", out)
        self.assertIn("Company X graders look for:", out)
        self.assertIn("Interviewers score ownership of the result. [company-references, example.com", out)
        self.assertIn("This item matches: Growth (by theme), Pace (by theme)", out)

    def test_every_value_unmapped_is_listed(self):
        store_company(fact("u1", name="One", themes=[], hints=[]), fact("u2", name="Two", themes=[], hints=[]),
                      name="Open Co")
        sid, _ = self.started("--target", "Open Co")
        out = self.cli(sessions.main, "resume", sid)[1]
        self.assertIn("One (needs your judgment)", out)
        self.assertIn("Two (needs your judgment)", out)

    def test_a_card_gets_no_emphasis(self):
        code, out, err = self.cli(sessions.main, "new", "Cards", "--count", "2", "--target", "Company X")
        self.assertEqual(code, 0, err)
        self.assertNotIn("graders look for", out)

    def test_change_of_style_on_resume_and_the_style_each_answer_keeps(self):
        sid, _ = self.started("--target", "Company X", "--style", "carl")
        self.assertEqual(self.log(sid, "s4")[0], 0)
        out = self.cli(sessions.main, "resume", sid, "--style", "star")[1]
        self.assertIn("Style changed to star", out)
        self.assertEqual(self.log(sid, "s2")[0], 0)
        self.assertEqual(self.log(sid, "s3", "--style", "soar")[0], 0)
        log = self.session(sid)["log"]
        self.assertEqual([(e["style"], e["company"]) for e in log],
                         [("carl", "Company X"), ("star", "Company X"), ("soar", "Company X")])
        self.assertEqual(self.session(sid)["style"], "star")
        self.assertIn("style star", self.cli(sessions.main, "list")[1])

    def test_card_answers_record_no_style_and_old_entries_none(self):
        sid = self.new_session()
        card = self.session(sid)["queue"][0]["id"]
        self.assertEqual(self.log(sid, card)[0], 0)
        entry = self.session(sid)["log"][0]
        self.assertNotIn("style", entry)
        self.assertEqual(self.log(sid, card, "--style", "star")[0], 1)
        with store.transaction(write=False) as conn:
            self.assertEqual(conn.execute("SELECT style, company FROM session_log").fetchone()[:], (None, None))

    def test_session_outlives_its_company_profile(self):
        sid, _ = self.started("--target", "Company X")
        tt.remove_company("Company X")
        out = self.cli(sessions.main, "resume", sid)[1]
        self.assertIn("The profile of Company X no longer exists", out)
        self.assertNotIn("graders look for", out)
        self.assertEqual(self.log(sid, "s4")[0], 0)
        self.assertEqual(self.session(sid)["log"][0]["company"], "Company X")


class CompanyDueTests(TargetCase):
    def rows(self, *pairs):
        return [{"id": i, "name": i, "last": "2026-01-01", "age_days": age} for i, age in pairs]

    def due_session(self, rows, *extra):
        with mock.patch.object(sessions.readiness, "due_items", return_value=rows):
            return self.cli(sessions.main, "new", "Retest", "--due", "--target", "Company X", *extra)

    def test_due_items_matching_the_company_come_first(self):
        code, out, err = self.due_session(self.rows(("s1", 70), ("s4", 50), ("s5", 40)))
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual(self.queue(sid), ["s4", "s1", "s5"])

    def test_count_keeps_the_matching_ones_due_longest_first(self):
        code, out, err = self.due_session(self.rows(("s1", 90), ("s2", 70), ("s5", 60), ("s4", 50)), "--count", "2")
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual(self.queue(sid), ["s4", "s2"])

    def test_same_group_keeps_the_one_due_longest_first(self):
        code, out, err = self.due_session(self.rows(("s1", 90), ("s5", 70)))
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual(self.queue(sid), ["s1", "s5"])

    def test_nothing_due_creates_no_session(self):
        code, _, err = self.due_session([])
        self.assertEqual(code, 1)
        self.assertIn("Nothing is due", err)


class CompanyReadinessTests(TargetCase):
    def report(self, *extra):
        code, out, err = self.cli(readiness.main, "--target", "Company X", *extra)
        self.assertEqual(code, 0, err)
        return out.split("COMPANY: Company X", 1)[1]

    def test_values_with_their_states_and_items(self):
        stories = tables.load_stories()
        stories["stories"][1]["status"] = "done"
        tables.replace_stories(stories)
        rehearsed = {"s2": {"graded2": set(), "answered": {date.today().isoformat()}}}
        with mock.patch.object(readiness.tables, "evidence", return_value=rehearsed):
            section = self.report()
        self.assertIn("Growth: covered", section)
        self.assertIn("s2 [done-rehearsed]", section)
        self.assertIn("s3 [draft] matched by word", section)
        self.assertIn("Judgment: needs your judgment", section)
        self.assertNotIn("%", section)

    def test_value_with_nothing_reads_no_story(self):
        store_company(fact("n1", name="Nothing", themes=["absent"], hints=["zebra"]), name="Company X")
        self.assertIn("Nothing: no story", self.report())

    def test_report_without_target_is_unchanged_by_a_default_company(self):
        before = self.cli(readiness.main)[1]
        up.save({"resume_root": "x", "target_company": "Company X"})
        self.assertEqual(self.cli(readiness.main)[1], before)

    def test_with_a_job_description_values_stay_and_items_narrow(self):
        jd = self.tmp / "jd.txt"
        jd.write_text("mentoring", encoding="utf-8")
        with mock.patch.object(readiness.qr, "analyze", return_value=mock.Mock(themes={"mentoring"})):
            section = self.report("--jd", str(jd))
        self.assertIn("Pace:", section)
        self.assertIn("s2 [draft]", section)
        self.assertNotIn("s4", section)

    def test_due_for_a_company_lists_only_matching_items(self):
        rows = [{"id": i, "name": i, "last": "2026-01-01", "age_days": a} for i, a in (("s1", 70), ("s4", 50), ("s5", 40))]
        with mock.patch.object(readiness, "due_items", return_value=rows):
            out = self.cli(readiness.main, "--due", "--target", "Company X")[1]
            self.assertIn("s4", out)
            self.assertNotIn("s1", out)
        with mock.patch.object(readiness, "due_items", return_value=rows[:1] + rows[2:]):
            out = self.cli(readiness.main, "--due", "--target", "Company X")[1]
        self.assertIn("2 item(s) due for a retest in all; none match Company X", out)

    def test_company_report_changes_nothing(self):
        before = json.dumps([tables.load_stories(), tt.load_companies()], sort_keys=True)
        self.report()
        self.assertEqual(json.dumps([tables.load_stories(), tt.load_companies()], sort_keys=True), before)


class CompanySessionExportTests(TargetCase):
    def test_exported_session_and_entries_carry_company_and_style(self):
        sid, _ = self.started("--target", "Company X", "--style", "soar")
        self.assertEqual(self.log(sid, "s4")[0], 0)
        exported = records.kind("sessions").export()[sid]
        self.assertEqual((exported["target"], exported["style"]), ("Company X", "soar"))
        self.assertEqual([(e["company"], e["style"]) for e in exported["log"]], [("Company X", "soar")])
