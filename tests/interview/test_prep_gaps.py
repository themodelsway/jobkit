"""Command-line coverage for prep commands and options no other test calls. Temp folders only."""
import unittest
from unittest import mock

from jobkit.interview import tables
from jobkit.interview import prep
from tests.interview.test_prep import PrepCase, run


class EngagementCommandTests(PrepCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move",
                             "--period", "2022", "--summary", "Moved jobs to a new scheduler")[0], 0)

    def eng(self):
        return tables.load_engagements()["engagements"][0]

    def test_add_keeps_period_and_summary(self):
        self.assertEqual((self.eng()["period"], self.eng()["summary"]), ("2022", "Moved jobs to a new scheduler"))

    def test_list_show_set(self):
        self.assertIn("acme-project", run("engagement", "list")[1])
        self.assertIn("Office move", run("engagement", "show", "acme-project")[1])
        self.assertEqual(run("engagement", "set", "acme-project", "my_role", "Lead")[0], 0)
        self.assertEqual(self.eng()["my_role"], "Lead")
        self.assertEqual(run("engagement", "set", "acme-project", "colour", "x")[0], 1)

    def test_fact_options(self):
        run("fact", "add", "acme-project", "12 engineers", "--basis", "stated", "--note", "from the kickoff deck")
        fact = self.eng()["facts"][0]
        self.assertEqual(fact["note"], "from the kickoff deck")
        code, _ = run("fact", "set", "acme-project", fact["id"], "--text", "14 engineers", "--source", "https://example.com/a",
                      "--note", "corrected")
        self.assertEqual(code, 0)
        fact = self.eng()["facts"][0]
        self.assertEqual((fact["text"], fact["source"], fact["note"]), ("14 engineers", "https://example.com/a", "corrected"))

    def test_decision_tradeoffs_then_remove(self):
        run("decision", "add", "acme-project", "--what", "Chose a queue", "--tradeoffs", "less control", "--ownership", "mine")
        decision = self.eng()["decisions"][0]
        self.assertEqual(decision["tradeoffs"], "less control")
        self.assertEqual(run("decision", "rm", "acme-project", decision["id"])[0], 0)
        self.assertEqual(self.eng()["decisions"], [])
        self.assertEqual(run("decision", "rm", "acme-project", "d99")[0], 1)

    def test_person_add(self):
        self.assertEqual(run("person", "add", "acme-project", "--role", "Product owner", "--note", "weekly sync")[0], 0)
        self.assertEqual(self.eng()["people"], [{"role": "Product owner", "note": "weekly sync"}])


class StoryOptionTests(PrepCase):
    def test_new_with_headline_and_next_by_company(self):
        self.assertEqual(run("new", "acme-extra", "--company", "acme", "--theme", "cost", "--headline", "Cut cost")[0], 0)
        self.assertEqual(self.story("acme-extra")["headline"], "Cut cost")
        code, out = run("next", "--company", "acme")
        self.assertEqual(code, 0)
        self.assertIn("acme", out)

    def test_metric_note(self):
        run("metric", "add", "acme-topic-a", "--name", "cost", "--value", "-20%", "--basis", "stated", "--note", "finance")
        self.assertEqual(self.story()["metrics"][0]["note"], "finance")

    def test_for_jd_top(self):
        prep.qr.load = lambda: ({"acme": {"id": "acme", "name": "Acme Corp", "bullets": [], "roles": [{"start": "2021-01", "end": None, "titles": ["T"]}]}}, {"groups": {}})     # restored by tearDown
        patcher = mock.patch.object(prep.qr, "load_or_fail", return_value=({"acme": {"id": "acme", "name": "Acme Corp", "bullets": [], "roles": [{"start": "2021-01", "end": None, "titles": ["T"]}]}}, {"groups": {}}))
        patcher.start()
        self.addCleanup(patcher.stop)
        for story_id in ("acme-first", "acme-second"):
            run("new", story_id, "--company", "acme", "--theme", "mentoring")
        jd = self.home / "jd.txt"
        jd.write_text("Mentor engineers and review their designs.")
        _, both = run("for-jd", str(jd))
        code, one = run("for-jd", str(jd), "--top", "1")
        self.assertEqual(code, 0, one)
        def ranked(text):
            return [ln for ln in text.splitlines() if ln.startswith("acme-")]

        self.assertEqual((len(ranked(both)), len(ranked(one))), (2, 1))

    def test_export_engagement_to_file(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        target = self.home / "eng.json"
        code, out = run("export", "--engagement", "acme-project", "-o", str(target))
        self.assertEqual(code, 0, out)
        self.assertIn("acme-project", target.read_text())
        md = self.home / "story.md"
        self.assertEqual(run("export", "--story", "acme-topic-a", "--format", "md", "--output", str(md))[0], 0)
        self.assertIn("topic-a", md.read_text())

    def test_evidence_without_and_with_practice(self):
        self.assertIn("no practice answer", run("evidence", "acme-topic-a")[1])
        self.assertEqual(run("evidence", "nosuch")[0], 1)
        log = {"at": "2026-11-01T10:00:00", "item": "acme-topic-a", "kind": "story", "question": "q",
               "answer": "a full answer", "confidence_after": 2}
        tables.save_session({
            "id": "s1", "title": "t", "mode": "stories", "status": "open", "created": "x", "updated": "x",
            "queue": [], "log": [log]})
        self.assertIn("2026-11-01", run("evidence", "acme-topic-a")[1])


if __name__ == "__main__":
    unittest.main()
