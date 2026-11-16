"""Tests for plugins/jobkit/src/jk/interview/sessions.py: practice sessions, their queues, filters and the answer log."""
import argparse
import unittest
from datetime import date
from unittest import mock

from jk.interview import arch, lead, prep, readiness, sessions, tables
from tests.interview.support import COMPANIES, SKILLS, SessionCase


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
