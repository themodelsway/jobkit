"""Tests for the `lead` command."""
from jk.interview import lead, readiness, tables
from tests.interview.test_sessions import SessionCase


class LeadershipTests(SessionCase):
    def test_partial_profile_still_reports_missing_scope(self):
        self.cli(lead.main, "profile", "set", "acme", "title", "Lead")
        _, out, _ = self.cli(lead.main, "status")
        self.assertIn("acme (direct_reports, indirect_team, budget)", out)
        for field in ("direct_reports", "indirect_team", "budget"):
            self.cli(lead.main, "profile", "set", "acme", field, "0")
        _, out, _ = self.cli(lead.main, "status")
        self.assertIn("Scope facts missing for: none", out)

    def test_blank_example_does_not_count_and_any_employer_is_allowed(self):
        qid = lead.cards()[0]["id"]
        self.cli(lead.main, "example", qid, "acme", "situation", "   ")
        self.assertIn("0/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.cli(lead.main, "example", qid, "acme", "situation", "We moved the office.")
        self.assertIn("1/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        code, _, err = self.cli(lead.main, "example", qid, "nobody", "situation", "x")
        self.assertEqual(code, 1)
        self.assertIn("COMPANY must be one of acme", err)


class SkipExampleTests(SessionCase):
    def test_not_applicable_counts_as_covered_but_is_shown(self):
        qid = lead.cards()[0]["id"]
        code, out, err = self.cli(lead.main, "skip", qid, "acme", "never managed managers")
        self.assertEqual(code, 0, err)
        self.assertIn("0/1 examples, 1 not applicable", self.cli(lead.main, "list")[1].splitlines()[0])
        self.assertNotIn(qid, "".join(row for row in self.cli(readiness.main)[1].splitlines() if "leadership:" in row))
        self.cli(lead.main, "example", qid, "acme", "situation", "A real one.")
        self.assertIn("1/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.assertNotIn("not applicable", self.cli(lead.main, "list")[1].splitlines()[0])

    def test_unskip_and_refusal_when_an_example_exists(self):
        qid = lead.cards()[0]["id"]
        self.cli(lead.main, "skip", qid, "acme")
        self.cli(lead.main, "unskip", qid, "acme")
        self.assertIn("0/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.cli(lead.main, "example", qid, "acme", "situation", "A real one.")
        self.assertEqual(self.cli(lead.main, "skip", qid, "acme")[0], 1)


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
