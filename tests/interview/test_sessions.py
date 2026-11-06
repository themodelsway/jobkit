"""Tests for sessions.py and readiness.py in a temp folder (the real prep/ is never touched).
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import sys
import unittest
from datetime import date, timedelta
from unittest import mock


from jobkit import store
from jobkit.interview import tables
from tests.support import HomeCase, drop_catalog
from jobkit.interview import arch, lead, readiness, sessions

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
        ev2 = {"graded2": {"2025-01-01", "2025-01-02"}, "answered": set()}
        ev1 = {"graded2": {"2025-01-01"}, "answered": set()}
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

    def test_requires_catalog(self):
        drop_catalog()
        code, _, err = self.cli(readiness.main)
        self.assertEqual((code, "run arch init" in err), (1, True))


if __name__ == "__main__":
    unittest.main()
