"""Command-line coverage for commands and options no other test calls: lead, arch filters, sessions new filters.
Temp folders only; the real prep/ is never touched."""
import unittest
from unittest import mock

from jobkit.interview import tables
from jobkit.interview import arch, lead, prep, readiness, sessions
from tests.interview.test_sessions import SessionCase


class LeadCommandTests(SessionCase):
    def first_id(self):
        return self.cli(lead.main, "list")[1].split()[0]

    def test_status_list_next_show(self):
        code, out, _ = self.cli(lead.main, "status")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())
        code, out, _ = self.cli(lead.main, "list")
        self.assertEqual(code, 0)
        qid = out.split()[0]
        self.assertEqual(self.cli(lead.main, "show", qid)[0], 0)
        self.assertEqual(self.cli(lead.main, "next")[0], 0)

    def test_category_filter_and_order(self):
        questions = tables.load_questions()
        category = questions[0]["category"]
        code, out, _ = self.cli(lead.main, "list", "--category", category)
        self.assertEqual(code, 0)
        listed = [q["id"] for q in questions if q["category"] == category]
        other = next(q["id"] for q in questions if q["category"] != category)
        self.assertIn(listed[0], out)
        self.assertNotIn(other + " ", out + " ")
        self.assertEqual(self.cli(lead.main, "next", "--category", category, "--order", "random")[0], 0)

    def test_set_fields_and_rejects_bad_ones(self):
        qid = self.first_id()
        self.assertEqual(self.cli(lead.main, "set", qid, "principle", "Ask, then decide")[0], 0)
        self.assertEqual(self.cli(lead.main, "set", qid, "confidence", "2")[0], 0)
        saved = tables.load_lead_progress()[qid]
        self.assertEqual((saved["principle"], saved["confidence"]), ("Ask, then decide", 2))
        self.assertEqual(self.cli(lead.main, "set", qid, "confidence", "9")[0], 1)
        with self.assertRaises(SystemExit):
            self.cli(lead.main, "set", qid, "colour", "x")

    def test_example_and_profile(self):
        qid = self.first_id()
        code, _, err = self.cli(lead.main, "example", qid, "acme", "situation", "We had a deadline")
        self.assertEqual(code, 0, err)
        saved = tables.load_lead_progress()[qid]["examples"]
        self.assertEqual(saved["acme"]["situation"], "We had a deadline")
        self.assertEqual(self.cli(lead.main, "example", qid, "acme", "colour", "x")[0], 1)
        self.assertEqual(self.cli(lead.main, "profile", "set", "acme", "direct_reports", "4")[0], 0)
        code, out, _ = self.cli(lead.main, "profile", "show")
        self.assertEqual(code, 0)
        self.assertIn("4", out)
        self.assertEqual(self.cli(lead.main, "profile", "set", "acme", "colour", "x")[0], 1)


class ArchOptionTests(SessionCase):
    def test_next_and_list_filters(self):
        cards = tables.load_catalog()["cards"]
        tier = cards[0]["tier"]
        out = self.cli(arch.main, "list", "--tier", str(tier))[1]
        self.assertIn(cards[0]["id"], out)
        for kind in ("service", "pair", "scenario"):
            code, out, _ = self.cli(arch.main, "next", "--kind", kind, "--order", "random")
            self.assertEqual(code, 0)
            self.assertTrue(out.strip())
        self.assertEqual(self.cli(arch.main, "next", "--track", "aws", "--tier", str(tier))[0], 0)

    def test_unknown_track_filter_finds_nothing(self):
        _, out, _ = self.cli(arch.main, "list", "--track", "nosuch")
        self.assertNotIn("vpc", out)

    def test_stale_months(self):
        self.assertEqual(self.cli(arch.main, "stale", "--months", "1")[0], 0)

    def test_refresh_note(self):
        url = "https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html"
        code, _, err = self.cli(arch.main, "refresh", "vpc", "--status", "active", "--source", url, "--note", "checked")
        self.assertEqual(code, 0, err)
        card = next(c for c in tables.load_catalog()["cards"] if c["id"] == "vpc")
        self.assertEqual(card["lifecycle"]["note"], "checked")


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
        jd.write_text("We need VPC experience.")
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
        tables.save_stories({"stories": [story("acme"), story("globex")]})
        code, out, err = self.cli(sessions.main, "new", "Stories", "--mode", "stories", "--company", "acme")
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        self.assertEqual([i["id"] for i in self.session(sid)["queue"]], ["acme-topic-a"])


class ReadinessOptionTests(SessionCase):
    def test_days_sets_when_a_solid_answer_ages(self):
        self.cli(arch.main, "set", "vpc", "confidence", "2")
        card = tables.load_progress()["vpc"]
        card["last_drilled"] = "2000-01-01"
        tables.save_progress({**tables.load_progress(), "vpc": card})
        def aging(days):
            return self.cli(readiness.main, "--days", str(days))[1].count("aging")

        self.assertGreater(aging(30), 0)
        self.assertEqual(aging(100000), 0)


if __name__ == "__main__":
    unittest.main()
