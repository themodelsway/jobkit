"""Tests for sessions.py and readiness.py in a temp folder (the real prep/ is never touched).
Run: uv run python -m unittest discover -s tests -t ."""
import argparse
import contextlib
import io
import json
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

from jk import store
from jk.interview import arch, lead, prep, readiness, sessions, tables
from jk.user import profile as up
from tests.support import drop_catalog, HomeCase

COMPANIES = {"acme": {"id": "acme", "name": "Acme", "bullets": [], "roles": [{"start": "2021-01", "end": None, "titles": ["T"]}]}}
SKILLS = {"groups": {"Cloud": [{"name": "VPC", "aliases": []}]}}


class SessionCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        for obj, name, value in ((arch.qr, "load", (COMPANIES, SKILLS)), (lead.qr, "load", (COMPANIES, SKILLS))):
            patcher = mock.patch.object(obj, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(arch.up, "tier1_services", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cli(arch.main, "init")
        self.cli(lead.main, "init")

    def cli(self, main, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if stdin is not None:
                with mock.patch.object(sys, "stdin", io.StringIO(stdin)):
                    code = main(list(argv))
            else:
                code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def new_session(self, *extra):
        code, out, err = self.cli(sessions.main, "new", "Warm up", "--count", "3", *extra)
        self.assertEqual(code, 0, err)
        return out.split("Started session ")[1].split(" ")[0]

    def session(self, sid):
        return tables.load_session(sid)


class SessionTests(SessionCase):
    def test_new_creates_session_and_index(self):
        sid = self.new_session()
        self.assertTrue(sid.startswith(date.today().isoformat() + "-warm-up"))
        s = self.session(sid)
        self.assertEqual((s["mode"], s["status"], len(s["queue"])), ("architecture", "open", 3))
        self.assertIn(sid, self.cli(sessions.main, "list")[1])
        self.assertNotEqual(self.new_session(), sid)               # same title the same day -> -2

    def test_new_errors(self):
        self.assertEqual(self.cli(sessions.main, "new", "x", "--mode", "jd")[0], 1)
        code, _, err = self.cli(sessions.main, "new", "x", "--area", "no such area")
        self.assertEqual(code, 1)
        self.assertIn("Nothing to ask", err)
        self.assertIn("No sessions yet", self.cli(sessions.main, "list")[1])

    def test_log_records_answer_and_confidence(self):
        sid = self.new_session()
        item = self.session(sid)["queue"][0]["id"]
        code, out, _ = self.cli(sessions.main, "log", sid, item, "--question", "Q?", "--answer", "-", "--grade", "ok",
                                "--confidence", "2", stdin="my full answer\n")
        self.assertEqual(code, 0)
        self.assertIn("Confidence recorded: 2", out)
        entry = self.session(sid)["log"][0]
        self.assertEqual((entry["answer"], entry["confidence_after"], entry["tutor"]), ("my full answer", 2, False))
        self.assertEqual(tables.load_progress()[item]["confidence"], 2)
        self.assertIn("1/3 items", self.cli(sessions.main, "list")[1])

    def test_confidence_is_shared_between_sessions(self):
        first = self.new_session()
        item = self.session(first)["queue"][0]["id"]
        self.cli(sessions.main, "log", first, item, "--question", "Q", "--answer", "one", "--confidence", "1")
        second = self.cli(sessions.main, "new", "Second", "--count", "3")[1].split("Started session ")[1].split(" ")[0]
        self.cli(sessions.main, "log", second, item, "--question", "Q", "--answer", "two", "--confidence", "2")
        self.assertEqual(tables.load_progress()[item]["confidence"], 2)
        self.assertEqual([e["confidence_after"] for e in self.session(first)["log"]], [1])   # the old session is unchanged

    def test_log_validation(self):
        sid = self.new_session()
        item = self.session(sid)["queue"][0]["id"]
        base = ["log", sid, item, "--question", "Q"]
        self.assertIn("Empty answer", self.cli(sessions.main, *base, "--answer", "  ")[2])
        self.assertIn("Unknown item", self.cli(sessions.main, "log", sid, "nope", "--question", "Q", "--answer", "a")[2])
        self.assertIn("--quiz is for tutor sessions", self.cli(sessions.main, *base, "--answer", "a", "--quiz")[2])
        self.cli(sessions.main, "close", sid)
        self.assertIn("is closed", self.cli(sessions.main, *base, "--answer", "a")[2])
        self.assertIn("Reopened", self.cli(sessions.main, "reopen", sid)[1])
        self.assertIn("No session", self.cli(sessions.main, "resume", "../etc")[2])

    def test_tutor_lessons_cap_confidence_and_quiz_allows_solid(self):
        sid = self.new_session("--mode", "tutor", "--topic", "architecture")
        item = self.session(sid)["queue"][0]["id"]
        taught = ["log", sid, item, "--question", "Q", "--answer", "lesson", "--confidence", "2"]
        self.cli(sessions.main, *taught)
        self.assertEqual(tables.load_progress()[item]["confidence"], 1)   # capped at 1
        quiz = ["log", sid, item, "--question", "Q2", "--answer", "right", "--grade", "correct", "--confidence", "2", "--quiz"]
        self.cli(sessions.main, *quiz)
        self.assertEqual(tables.load_progress()[item]["confidence"], 2)
        self.cli(sessions.main, *taught)                                                          # a lesson never lowers it
        self.assertEqual(tables.load_progress()[item]["confidence"], 2)

    def test_leadership_mode_queue_and_resume(self):
        sid = self.new_session("--mode", "leadership")
        self.assertEqual({q["kind"] for q in self.session(sid)["queue"]}, {"leader"})
        out = self.cli(sessions.main, "resume", sid)[1]
        self.assertIn("Next item (leader):", out)


class RemovedTargetTests(SessionCase):
    def remove_card(self, card_id):
        cat = tables.load_catalog()
        tables.replace_catalog({**cat, "cards": [c for c in cat["cards"] if c["id"] != card_id]})
        return cat

    def log(self, sid, item):
        return self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "a")

    def test_answering_a_removed_item_is_refused_and_nothing_is_stored(self):
        sid = self.new_session()
        item = self.session(sid)["queue"][0]["id"]
        cat = self.remove_card(item)
        code, _, err = self.log(sid, item)
        self.assertEqual(code, 1)
        self.assertIn(item, err)
        self.assertEqual(self.session(sid)["log"], [])
        tables.replace_catalog(cat)                                   # the item is back
        self.assertEqual(self.log(sid, item)[0], 0)
        self.assertEqual(len(self.session(sid)["log"]), 1)

    def test_resume_reports_an_unavailable_item_and_shows_the_next(self):
        sid = self.new_session()
        queue = self.session(sid)["queue"]
        self.remove_card(queue[0]["id"])
        code, out, err = self.cli(sessions.main, "resume", sid)
        self.assertEqual(code, 0, err)
        self.assertIn("unavailable", out)
        self.assertIn(queue[1]["id"], out)


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
        sid = self.new_session("--mode", "tutor", "--topic", "architecture")
        item = self.session(sid)["queue"][0]["id"]
        self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "lesson", "--confidence", "1")
        self.assertNotIn(item, readiness.attempts())
        self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "ok", "--grade", "g", "--confidence", "2", "--quiz")
        self.assertEqual(readiness.attempts()[item]["graded2"], {date.today().isoformat()})

    def test_report_sections_and_jd_filter(self):
        code, out, _ = self.cli(readiness.main)
        self.assertEqual(code, 0)
        for text in ("ARCHITECTURE", "LEADERSHIP", "STAR STORIES: none yet", "WORK ON NEXT", "Note: labels come from"):
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
        self.assertEqual(self.cli(arch.main, "track", "add", "product", "--seed", "-", stdin=json.dumps(seed))[0], 0)
        self.cli(arch.main, "init", "--track", "product")
        out = self.cli(readiness.main)[1]
        self.assertRegex(out, r"product: Cases\s+1 items")
        self.assertRegex(out, r"product: Role-plays\s+1 items")
        sid = self.new_session("--kind", "role-play")
        self.assertEqual([i["id"] for i in self.session(sid)["queue"]], ["product-role-push-back"])

    def test_requires_catalog(self):
        drop_catalog()
        code, _, err = self.cli(readiness.main)
        self.assertEqual((code, "run arch init" in err), (1, True))


class RetestTests(SessionCase):
    """The stored retest window, `readiness --due` and `sessions new --due`."""

    def solid(self, card_id, days_ago):
        progress = tables.load_progress()
        progress[card_id] = {"confidence": 2, "notes": "", "links": {},
                             "last_drilled": (date.today() - timedelta(days=days_ago)).isoformat()}
        tables.replace_progress(progress)

    def cards(self, n=3):
        return [c["id"] for c in arch.catalog()["cards"][:n]]

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


class SessionFilterTests(SessionCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.cli(prep.main, "init")[0], 0)
        patcher = mock.patch.object(sessions.qr, "load_or_fail", return_value=(COMPANIES, SKILLS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def jd(self, text="VPC design"):
        path = self.home / "jd.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_unfiltered_jd_session_works(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "jd", "--jd", self.jd())
        self.assertEqual(code, 0, err)

    def test_jd_mode_respects_filters(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "jd", "--jd", self.jd(), "--track", "acmedata")
        self.assertEqual(code, 1, err)
        code, _, err = self.cli(sessions.main, "new", "x", "--jd", self.jd(), "--area", "NO SUCH AREA")
        self.assertEqual(code, 1, err)

    def test_count_must_be_one_or_more(self):
        for bad in ("0", "-3", "x"):
            with self.subTest(count=bad), mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                sessions.build_parser().parse_args(["new", "x", "--count", bad])
            self.assertEqual(raised.exception.code, 2)

    def test_jd_with_a_kind_it_cannot_match_is_refused(self):
        self.assertEqual(self.cli(sessions.main, "new", "x", "--jd", self.jd(), "--kind", "service")[0], 0)
        for kind in ("pair", "scenario", "case", "role-play"):
            with self.subTest(kind=kind):
                code, _, err = self.cli(sessions.main, "new", "x", "--jd", self.jd(), "--kind", kind)
                self.assertEqual(code, 1)
                self.assertIn("service cards only", err)

    def test_jd_alone_means_jd_mode(self):
        code, out, err = self.cli(sessions.main, "new", "implicit", "--jd", self.jd())
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        saved = tables.load_session(sid)
        self.assertEqual((saved["mode"], saved["jd"] is not None), ("jd", True))
        self.assertIn("vpc", [item["id"] for item in saved["queue"]])

    def test_jd_with_another_mode_is_an_error(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "stories", "--jd", self.jd())
        self.assertEqual(code, 1)
        self.assertIn("--jd goes with mode jd", err)


class MixedQueueTests(SessionCase):
    """A jd session takes cards and stories in turn, so `--count` cannot leave one kind out."""

    def start(self, cards, stories, count):
        jd = self.home / "jd.txt"
        jd.write_text("VPC design", encoding="utf-8")
        with mock.patch.object(sessions, "card_queue", return_value=cards), \
                mock.patch.object(sessions, "story_queue", return_value=stories):
            code, out, err = self.cli(sessions.main, "new", "Mixed", "--jd", str(jd), "--count", str(count))
        self.assertEqual(code, 0, err)
        return out, self.session(out.split("Started session ")[1].split(" ")[0])["queue"]

    def items(self, kind, n):
        if kind == "card":
            return [{"id": c["id"], "kind": "card"} for c in arch.catalog()["cards"][:n]]
        blank = dict.fromkeys(("situation", "task", "action", "result", "metric", "lessons", "notes"))
        tables.replace_stories({"stories": [
            {"id": f"acme-s{i}", "company": "acme", "company_name": "Acme", "theme": f"s{i}", "headline": "h",
             "metrics_on_resume": [], "anchor_bullets": [], "follow_ups": [], "status": "empty", **blank}
            for i in range(n)]})
        return [{"id": f"acme-s{i}", "kind": "story"} for i in range(n)]

    def test_take_turns_keeps_each_order_and_fills_from_the_longer(self):
        cards, stories = self.items("card", 3), self.items("story", 1)
        self.assertEqual(sessions.take_turns(cards, stories), [cards[0], stories[0], cards[1], cards[2]])
        self.assertEqual(sessions.take_turns([], stories), stories)

    def test_count_keeps_both_kinds_and_says_what_was_left_out(self):
        out, queue = self.start(self.items("card", 3), self.items("story", 3), 4)
        self.assertEqual([q["kind"] for q in queue], ["card", "story", "card", "story"])
        self.assertIn("with 4 items (2 cards, 2 stories; 2 more matched and were left out", out)

    def test_one_kind_running_out_is_filled_by_the_other(self):
        out, queue = self.start(self.items("card", 3), self.items("story", 1), 4)
        self.assertEqual([q["kind"] for q in queue], ["card", "story", "card", "card"])
        self.assertIn("with 4 items (3 cards, 1 story).", out)


class JdThemeTests(unittest.TestCase):
    def test_a_story_counts_for_a_jd_through_its_other_themes(self):
        jd = "Led a move to Kubernetes and mentored engineers."
        stories = [{"id": "a", "theme": "ownership", "also_themes": ["mentoring"]},
                   {"id": "b", "theme": "ownership", "also_themes": []},
                   {"id": "c", "theme": "topic-b", "also_themes": []}]
        with mock.patch.object(readiness.qr, "analyze", return_value=argparse.Namespace(themes={"mentoring", "topic-b"})):
            self.assertEqual([s["id"] for s in readiness.in_jd_themes(stories, jd)], ["a", "c"])


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


class LessonDateTests(SessionCase):
    def test_lesson_without_quiz_keeps_the_drill_date(self):
        cards = dict(sessions.arch.progress()["cards"])
        entry = cards.setdefault("vpc", sessions.arch.blank_progress())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        tables.replace_progress(cards)
        sessions.record_confidence("card", "vpc", 1, True)
        self.assertEqual(sessions.arch.progress()["cards"]["vpc"]["last_drilled"], "2000-01-01")

    def test_passed_quiz_refreshes_the_date_of_an_aging_solid_card(self):
        cards = dict(sessions.arch.progress()["cards"])
        entry = cards.setdefault("vpc", sessions.arch.blank_progress())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        tables.replace_progress(cards)
        sid = self.new_session("--mode", "tutor", "--topic", "architecture")
        code, _, err = self.cli(sessions.main, "log", sid, "vpc", "--question", "Q", "--answer", "a", "--grade", "g",
                                "--confidence", "2", "--quiz")
        self.assertEqual(code, 0, err)
        self.assertEqual(sessions.arch.progress()["cards"]["vpc"]["last_drilled"], date.today().isoformat())


class QueueTests(SessionCase):
    """L14: default queues include finished and strong material, after the unfinished and weak."""

    def args(self, *extra: str):
        return sessions.build_parser().parse_args(["new", "t", *extra])

    def set_card(self, card_id: str, confidence: int, drilled: str | None) -> None:
        cards = dict(sessions.arch.progress()["cards"])
        entry = cards.setdefault(card_id, sessions.arch.blank_progress())
        entry["confidence"], entry["last_drilled"] = confidence, drilled
        tables.replace_progress(cards)

    def ids(self, queue) -> list[str]:
        return [item["id"] for item in queue]

    def test_aging_solid_card_is_queued_after_weak_ones_and_keeps_its_confidence(self):
        self.set_card("vpc", 2, "2000-01-01")
        queue = self.ids(sessions.card_queue(self.args()))
        self.assertIn("vpc", queue)
        self.assertEqual(queue[-1], "vpc")
        self.assertEqual(sessions.arch.progress()["cards"]["vpc"]["confidence"], 2)

    def test_old_solid_card_comes_before_a_freshly_solid_one(self):
        cards = [c["id"] for c in sessions.arch.catalog()["cards"]][:2]
        self.set_card(cards[0], 2, date.today().isoformat())
        self.set_card(cards[1], 2, "2000-01-01")
        queue = self.ids(sessions.card_queue(self.args()))
        self.assertLess(queue.index(cards[1]), queue.index(cards[0]))

    def test_only_open_leaves_solid_cards_out(self):
        self.set_card("vpc", 2, "2000-01-01")
        self.assertNotIn("vpc", self.ids(sessions.card_queue(self.args("--only-open"))))

    def stories(self):
        return [{"id": "done-one", "status": "done", "company": "acme", "engagement": "e"},
                {"id": "draft-one", "status": "draft", "company": "acme", "engagement": "e"}]

    def test_finished_story_is_queued_after_unfinished_ones(self):
        with mock.patch.object(sessions.prep, "stories", return_value=self.stories()):
            self.assertEqual(self.ids(sessions.story_queue(self.args())), ["draft-one", "done-one"])

    def test_only_open_leaves_finished_stories_out(self):
        with mock.patch.object(sessions.prep, "stories", return_value=self.stories()):
            self.assertEqual(self.ids(sessions.story_queue(self.args("--only-open"))), ["draft-one"])

    def test_solid_leadership_question_is_queued_last_unless_only_open(self):
        first = lead.cards()[0]["id"]
        questions = dict(lead.prog()["questions"])
        entry = questions.setdefault(first, lead.blank())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        tables.replace_lead_progress(questions)
        everything = self.ids(sessions.build_queue(self.args("--mode", "leadership"))[0])
        only_open = self.ids(sessions.build_queue(self.args("--mode", "leadership", "--only-open"))[0])
        self.assertIn(first, everything)
        self.assertEqual(everything[-1], first)
        self.assertNotIn(first, only_open)


class SessionOptionTests(SessionCase):
    def init_stories(self):
        self.assertEqual(self.cli(prep.main, "init")[0], 0)

    def test_filters_shape_the_queue(self):
        cards = {c["id"]: c for c in tables.load_catalog()["cards"]}
        sid = self.new_session("--kind", "service", "--tier", "2", "--order", "random", "--track", "aws")
        queue = self.session(sid)["queue"]
        self.assertTrue(queue)
        for item in queue:
            self.assertEqual(cards[item["id"]]["kind"], "service")
            self.assertLessEqual(cards[item["id"]]["tier"], 2)         # --tier N means tier N or lower

    def test_area_filter(self):
        cards = tables.load_catalog()["cards"]
        area = cards[0]["area"]
        sid = self.new_session("--area", area)
        by_id = {c["id"]: c for c in cards}
        self.assertTrue(all(by_id[i["id"]]["area"] == area for i in self.session(sid)["queue"]))

    def test_leadership_category(self):
        category = tables.load_questions()[0]["category"]
        sid = self.new_session("--mode", "leadership", "--category", category)
        self.assertTrue(self.session(sid)["queue"])
        self.assertEqual({i["kind"] for i in self.session(sid)["queue"]}, {"leader"})

    def test_jd_mode_records_the_file(self):
        self.init_stories()
        patcher = mock.patch.object(sessions.qr, "load_or_fail", return_value=({"acme": {"id": "acme", "name": "Acme Corp", "bullets": [], "roles": [{"start": "2021-01", "end": None, "titles": ["T"]}]}}, {"groups": {}}))
        patcher.start()
        self.addCleanup(patcher.stop)
        jd = self.tmp / "jd.txt"
        jd.write_text("We need VPC experience.", encoding="utf-8")
        code, out, err = self.cli(sessions.main, "new", "For JD", "--mode", "jd", "--jd", str(jd))
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual(self.session(sid)["jd"], str(jd))
        self.assertIn("vpc", [i["id"] for i in self.session(sid)["queue"]])

    def test_company_filter_for_stories(self):
        def story(company):
            return {"id": f"{company}-topic-a", "company": company, "company_name": company.title(),
                    "theme": "topic-a", "headline": "h", "metrics_on_resume": [], "anchor_bullets": [],
                    "situation": None, "task": None, "action": None, "result": None, "metric": None, "lessons": None,
                    "notes": None, "follow_ups": [], "status": "empty"}
        tables.replace_stories({"stories": [story("acme"), story("globex")]})
        code, out, err = self.cli(sessions.main, "new", "Stories", "--mode", "stories", "--company", "acme")
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual([i["id"] for i in self.session(sid)["queue"]], ["acme-topic-a"])


class ReadinessOptionTests(SessionCase):
    def test_days_sets_when_a_solid_answer_ages(self):
        self.cli(arch.main, "set", "vpc", "confidence", "2")
        card = tables.load_progress()["vpc"]
        card["last_drilled"] = "2000-01-01"
        tables.replace_progress({**tables.load_progress(), "vpc": card})
        def aging(days):
            return self.cli(readiness.main, "--days", str(days))[1].count("aging")

        self.assertGreater(aging(30), 0)
        self.assertEqual(aging(100000), 0)


if __name__ == "__main__":
    unittest.main()
