"""Tests for plugins/jobkit/src/jk/interview/readiness.py: the readiness report, retest reminders and a company's values."""
import argparse
import json
import unittest
from datetime import date, timedelta
from unittest import mock

from jk import store
from jk.interview import cards, lead, readiness, sessions, tables
from jk.interview import target_tables as tt
from jk.user import profile as up
from tests.interview.support import SessionCase, TargetCase, drop_catalog, fact, store_company


class ReadinessTests(SessionCase):
    def test_report_changes_nothing_in_the_database(self):
        self.new_session()
        files = [store.db_path(), store.db_path().with_name("jobkit.db-wal")]
        before = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()]
        self.cli(readiness.main)
        self.cli(readiness.main)
        self.assertEqual([(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()], before)

    def test_labels(self):
        today = date.today().isoformat()
        old = (date.today() - timedelta(days=90)).isoformat()
        recent = [(date.today() - timedelta(days=n)).isoformat() for n in (1, 2)]
        ev2 = {"graded2": set(recent), "answered": set()}
        ev1 = {"graded2": {recent[0]}, "answered": set()}
        self.assertEqual(readiness.label(0, None, None, 30), "untested")
        self.assertEqual(readiness.label(1, today, None, 30), "some gaps")
        self.assertEqual(readiness.label(2, old, ev2, 30), "aging")
        self.assertEqual(readiness.label(2, today, ev2, 30), "solid-repeated")
        self.assertEqual(readiness.label(2, today, ev1, 30), "solid-once")
        self.assertEqual(readiness.label(2, today, None, 30), "solid-unlogged")

    def test_lessons_do_not_count_but_quizzes_do(self):
        sid = self.new_session("--mode", "tutor", "--topic", "knowledge")
        item = self.session(sid)["queue"][0]["id"]
        self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "lesson", "--confidence", "1")
        self.assertNotIn(item, readiness.attempts())
        self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "ok", "--grade", "g", "--confidence", "2", "--quiz")
        self.assertEqual(readiness.attempts()[item]["graded2"], {date.today().isoformat()})

    def test_report_sections_and_jd_filter(self):
        code, out, _ = self.cli(readiness.main)
        self.assertEqual(code, 0)
        for text in ("ROLE KNOWLEDGE", "LEADERSHIP", "STAR STORIES: none yet", "WORK ON NEXT", "Note: labels come from"):
            self.assertIn(text, out)
        jd = self.tmp / "jd.txt"
        jd.write_text("We need VPC expertise.", encoding="utf-8")
        out = self.cli(readiness.main, "--jd", str(jd))[1]
        self.assertIn("(cards matching the JD)", out)
        self.assertIn("LEADERSHIP: not filtered by a JD", out)

    def test_case_and_role_play_cards_are_labelled_per_area(self):
        seed = {"label": "Product", "family": "product", "source_hosts": ["www.gov.uk"],
                "cases": [{"title": "Sign-ups fell", "situation": "Sign-ups fell. Why?"}],
                "role_plays": [{"title": "Push back", "part": "a sales director", "goal": "agree a plan"}]}
        self.assertEqual(self.cli(cards.main, "track", "add", "product", "--seed", "-", stdin=json.dumps(seed))[0], 0)
        self.cli(cards.main, "init", "--track", "product")
        out = self.cli(readiness.main)[1]
        self.assertRegex(out, r"product: Cases\s+1 items")
        self.assertRegex(out, r"product: Role-plays\s+1 items")
        sid = self.new_session("--kind", "role-play")
        self.assertEqual([i["id"] for i in self.session(sid)["queue"]], ["product-role-push-back"])

    def test_requires_catalog(self):
        drop_catalog()
        code, _, err = self.cli(readiness.main)
        self.assertEqual((code, "cards init --track NAME" in err), (1, True))


class RetestTests(SessionCase):
    """The stored retest window, `readiness --due` and `sessions new --due`."""

    def solid(self, card_id, days_ago):
        progress = tables.load_progress()
        progress[card_id] = {"confidence": 2, "notes": "", "links": {},
                             "last_drilled": (date.today() - timedelta(days=days_ago)).isoformat()}
        tables.replace_progress(progress)

    def cards(self, n=3):
        return [c["id"] for c in cards.catalog()["cards"][:n]]

    def window(self, days):
        up.save({"resume_root": "x", "reassess_days": days})

    def test_lists_only_old_good_answers_oldest_first_with_ages(self):
        a, b, c = self.cards()
        self.solid(a, 50)
        self.solid(b, 60)
        self.solid(c, 5)
        code, out, _ = self.cli(readiness.main, "--due")
        self.assertEqual(code, 0)
        rows = [line for line in out.splitlines() if line.startswith("  ")]
        self.assertEqual([r.split()[0] for r in rows], [b, a])
        self.assertIn("(60 days ago)", rows[0])
        self.assertIn("2 item(s) due", out)
        self.assertNotIn(c, out)

    def test_none_due(self):
        self.solid(self.cards()[0], 5)
        code, out, _ = self.cli(readiness.main, "--due")
        self.assertEqual((code, "none due" in out), (0, True))

    def test_json_and_output_file(self):
        a = self.cards()[0]
        self.solid(a, 40)
        rows = json.loads(self.cli(readiness.main, "--due", "--json")[1])
        self.assertEqual([(r["id"], r["age_days"]) for r in rows], [(a, 40)])
        target = self.tmp / "due.json"
        self.assertEqual(self.cli(readiness.main, "--due", "--json", "-o", str(target))[0], 0)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))[0]["id"], a)

    def test_listing_changes_nothing_in_the_database(self):
        self.solid(self.cards()[0], 40)
        files = [store.db_path(), store.db_path().with_name("jobkit.db-wal")]
        before = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()]
        self.cli(readiness.main, "--due")
        self.assertEqual([(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()], before)

    def test_stored_window_decides_and_days_overrides(self):
        a = self.cards()[0]
        self.solid(a, 45)
        self.window(60)
        self.assertIn("none due", self.cli(readiness.main, "--due")[1])
        self.assertIn(a, self.cli(readiness.main, "--due", "--days", "30")[1])
        self.window(30)
        self.assertIn(a, self.cli(readiness.main, "--due")[1])

    def test_report_label_follows_the_stored_window(self):
        a = self.cards()[0]
        self.solid(a, 45)
        self.assertIn("aging", self.cli(readiness.main)[1])
        self.window(60)
        self.assertNotIn("aging 1", self.cli(readiness.main)[1])

    def test_due_cannot_be_combined_with_jd(self):
        jd = self.tmp / "jd.txt"
        jd.write_text("VPC", encoding="utf-8")
        self.assertEqual(self.cli(readiness.main, "--due", "--jd", str(jd))[0], 1)

    def test_session_queue_holds_exactly_the_due_items(self):
        a, b, c = self.cards()
        self.solid(a, 50)
        self.solid(b, 60)
        self.solid(c, 5)
        sid = self.new_session("--due")
        self.assertEqual({q["id"] for q in self.session(sid)["queue"]}, {a, b})

    def test_session_with_nothing_due_says_so_and_creates_nothing(self):
        self.solid(self.cards()[0], 5)
        code, _, err = self.cli(sessions.main, "new", "Retest", "--due")
        self.assertEqual(code, 1)
        self.assertIn("Nothing is due for a retest", err)
        self.assertIn("No sessions yet", self.cli(sessions.main, "list")[1])

    def due_rows(self, *pairs):
        """A stand-in for readiness.due_items: (id, age in days) pairs, oldest first."""
        return [{"id": i, "name": i, "last": "2026-01-01", "age_days": age} for i, age in pairs]

    def save_story(self):
        tables.replace_stories({"stories": [{
            "id": "acme-topic-a", "company": "acme", "company_name": "Acme", "theme": "topic-a",
            "headline": "h", "metrics_on_resume": [], "anchor_bullets": [], "situation": None, "task": None,
            "action": None, "result": None, "metric": None, "lessons": None, "notes": None, "follow_ups": [],
            "status": "done"}]})
        return "acme-topic-a"

    def test_only_a_leadership_question_is_due(self):
        first = lead.cards()[0]["id"]
        questions = dict(lead.prog()["questions"])
        entry = questions.setdefault(first, lead.blank())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        tables.replace_lead_progress(questions)
        sid = self.new_session("--due")
        self.assertEqual(self.session(sid)["queue"], [{"id": first, "kind": "leader"}])

    def test_due_items_of_every_kind_are_queued_oldest_first_as_retest(self):
        card, story = self.cards()[0], self.save_story()
        rows = self.due_rows((card, 60), (story, 40))
        with mock.patch.object(sessions.readiness, "due_items", return_value=rows):
            sid = self.new_session("--due")
        session = self.session(sid)
        self.assertEqual([q["id"] for q in session["queue"]], [card, story])
        self.assertEqual(session["mode"], "retest")

    def test_a_mode_narrows_the_due_queue(self):
        card, story = self.cards()[0], self.save_story()
        with mock.patch.object(sessions.readiness, "due_items", return_value=self.due_rows((card, 60), (story, 40))):
            sid = self.new_session("--due", "--mode", "stories")
        self.assertEqual([q["id"] for q in self.session(sid)["queue"]], [story])
        self.assertEqual(self.session(sid)["mode"], "stories")

    def test_count_keeps_the_oldest_due_items(self):
        a, b, c = self.cards()
        rows = self.due_rows((b, 70), (c, 50), (a, 40))
        with mock.patch.object(sessions.readiness, "due_items", return_value=rows):
            code, out, err = self.cli(sessions.main, "new", "Retest", "--due", "--count", "2")
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual([q["id"] for q in self.session(sid)["queue"]], [b, c])

    def test_logging_works_per_kind_in_a_retest_session(self):
        card, story = self.cards()[0], self.save_story()
        with mock.patch.object(sessions.readiness, "due_items", return_value=self.due_rows((card, 60), (story, 40))):
            sid = self.new_session("--due")
        for item in (card, story):
            code, _, err = self.cli(sessions.main, "log", sid, item, "--question", "q", "--answer", "an answer")
            self.assertEqual(code, 0, err)
        self.assertEqual([e["item"] for e in self.session(sid)["log"]], [card, story])

    def test_home_with_no_stories_or_questions_does_not_crash(self):
        drop_catalog()
        code, _, err = self.cli(sessions.main, "new", "Retest", "--due")
        self.assertEqual(code, 1)
        self.assertIn("Nothing is due for a retest", err)

    def test_due_and_only_open_conflict(self):
        self.assertEqual(self.cli(sessions.main, "new", "x", "--due", "--only-open")[0], 1)

    def test_queue_aging_follows_the_stored_window(self):
        self.assertEqual(sessions.card_group({"confidence": 2, "last_drilled": (date.today() - timedelta(days=45)).isoformat()}, 30), 1)
        self.assertEqual(sessions.card_group({"confidence": 2, "last_drilled": (date.today() - timedelta(days=45)).isoformat()}, 60), 2)
        first, second = self.cards(2)
        self.solid(first, 5)
        self.solid(second, 45)
        args = argparse.Namespace(order="default", only_open=False, track=None, area=None, tier=None, kind=None)
        queue = [q["id"] for q in sessions.card_queue(args)]
        self.assertLess(queue.index(second), queue.index(first))      # 45 days is aged at the default 30
        for stored, expected in ((None, 30), (60, 60)):
            if stored:
                self.window(stored)
            with mock.patch.object(sessions, "card_group", wraps=sessions.card_group) as spy:
                sessions.card_queue(args)
            self.assertEqual({call.args[1] for call in spy.call_args_list}, {expected})


class ReadinessLabelTests(unittest.TestCase):
    def test_old_solid_answers_read_as_aging_even_with_recent_lesson(self):
        today = date.today()
        old = (today - timedelta(days=90)).isoformat()
        evidence = {"graded2": {old}, "answered": {old}}
        self.assertEqual(readiness.label(2, today.isoformat(), evidence, 30), "aging")
        recent = {"graded2": {today.isoformat()}, "answered": {today.isoformat()}}
        self.assertEqual(readiness.label(2, today.isoformat(), recent, 30), "solid-once")

    def test_story_label_needs_a_recent_answer(self):
        story = {"id": "s", "status": "done"}
        old = (date.today() - timedelta(days=90)).isoformat()
        self.assertEqual(readiness.story_label(story, {"s": {"graded2": set(), "answered": {old}}}, 30), "done-aging")
        now = date.today().isoformat()
        self.assertEqual(readiness.story_label(story, {"s": {"graded2": set(), "answered": {now}}}, 30), "done-rehearsed")


class ReadinessOptionTests(SessionCase):
    def test_days_sets_when_a_solid_answer_ages(self):
        self.cli(cards.main, "set", "vpc", "confidence", "2")
        card = tables.load_progress()["vpc"]
        card["last_drilled"] = "2000-01-01"
        tables.replace_progress({**tables.load_progress(), "vpc": card})

        def aging(days):
            return self.cli(readiness.main, "--days", str(days))[1].count("aging")

        self.assertGreater(aging(30), 0)
        self.assertEqual(aging(100000), 0)


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
