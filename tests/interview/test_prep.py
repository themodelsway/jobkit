"""Tests for story_model.py and the prep.py story/engagement commands. Run: .venv/bin/python -m unittest discover -s tests -t .
Everything happens in a temp directory; the real prep/ folder is never touched."""
import contextlib
import io
import json
import unittest
from unittest import mock

from jobkit import common, store
from jobkit.interview import prep, story_model as sm, tables
from tests.support import HomeCase


def run(*argv):
    """Run one prep command; return (exit_code, stdout)."""
    out = io.StringIO()
    code = 0
    a = prep.build_parser().parse_args(list(argv))
    with contextlib.redirect_stdout(out):
        try:
            with store.transaction():
                code = a.fn(a) or 0
        except common.ToolError as e:
            code = 1
            out.write(str(e))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                out.write(e.code)
    return code, out.getvalue()


class PrepCase(HomeCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(prep.qr, "load", return_value=({"acme": {"id": "acme", "name": "Acme Corp"}}, None))
        patcher.start()
        self.addCleanup(patcher.stop)
        seeded = {"stories": [{"id": "acme-topic-a", "company": "acme", "company_name": "Acme Corp", "theme": "topic-a",
                           "headline": "Led topic A", "metrics_on_resume": [], "anchor_bullets": ["b1"],
                           "situation": None, "task": None, "action": None, "result": None, "metric": None, "lessons": None,
                           "notes": None, "follow_ups": ["Batch size?"], "status": "empty"}]}
        tables.replace_stories(seeded)

    def story(self, sid="acme-topic-a"):
        return next(s for s in prep.stories() if s["id"] == sid)

    def fill_star(self, sid="acme-topic-a"):
        for f in sm.STAR:
            self.assertEqual(run("set", sid, f, f"I did the {f}.")[0], 0)


class TestStoryBasics(PrepCase):
    def test_old_fields_still_set_and_status_moves_to_draft(self):
        run("set", "acme-topic-a", "situation", "x")
        self.assertEqual(self.story()["status"], "draft")

    def test_show_prints_old_header(self):
        _, out = run("show", "acme-topic-a")
        self.assertIn("[acme-topic-a] Acme Corp | topic-a | status: empty", out)


class TestDoneGate(PrepCase):
    def test_done_needs_star(self):
        code, out = run("set", "acme-topic-a", "status", "done")
        self.assertEqual(code, 1)
        self.assertIn("still empty", out)
        self.assertEqual(self.story()["status"], "empty")

    def test_done_ok_when_star_filled(self):
        self.fill_star()
        self.assertEqual(run("set", "acme-topic-a", "status", "done")[0], 0)
        self.assertEqual(self.story()["status"], "done")

    def test_done_blocked_by_unsure_fact(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "Used a stream", "--basis", "unsure")
        run("link", "acme-topic-a", "acme-project", "--facts", "f1")
        self.fill_star()
        code, out = run("set", "acme-topic-a", "status", "done")
        self.assertEqual(code, 1)
        self.assertIn("cannot back a story", out)
        run("fact", "set", "acme-project", "f1", "--basis", "stated")
        self.assertEqual(run("set", "acme-topic-a", "status", "done")[0], 0)

    def test_done_blocked_by_proposed_fact(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "Use signed upload links", "--basis", "proposed")
        run("link", "acme-topic-a", "acme-project", "--facts", "f1")
        self.fill_star()
        self.assertEqual(run("set", "acme-topic-a", "status", "done")[0], 1)


class TestFacts(PrepCase):
    def setUp(self):
        super().setUp()
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move", "--role", "team lead")

    def test_basis_is_required_and_checked(self):
        with self.assertRaises(SystemExit):
            prep.build_parser().parse_args(["fact", "add", "acme-project", "text"])      # --basis missing
        with self.assertRaises(SystemExit):
            prep.build_parser().parse_args(["fact", "add", "acme-project", "text", "--basis", "guess"])

    def test_verified_doc_needs_url(self):
        self.assertEqual(run("fact", "add", "acme-project", "t", "--basis", "verified-doc")[0], 1)
        self.assertEqual(run("fact", "add", "acme-project", "t", "--basis", "verified-doc", "--source", "https://docs.aws.amazon.com/x")[0], 0)

    def test_ids_never_reused_after_remove(self):
        run("fact", "add", "acme-project", "one", "--basis", "stated")
        run("fact", "add", "acme-project", "two", "--basis", "stated")
        run("fact", "rm", "acme-project", "f2")
        run("fact", "add", "acme-project", "three", "--basis", "stated")
        ids = [f["id"] for f in prep.engagements()[0]["facts"]]
        self.assertEqual(ids, ["f1", "f3"])

    def test_cannot_remove_fact_in_use(self):
        run("fact", "add", "acme-project", "one", "--basis", "stated")
        run("link", "acme-topic-a", "acme-project", "--facts", "f1")
        code, out = run("fact", "rm", "acme-project", "f1")
        self.assertEqual(code, 1)
        self.assertIn("used by acme-topic-a", out)

    def test_link_unknown_fact_fails_and_saves_nothing(self):
        self.assertEqual(run("link", "acme-topic-a", "acme-project", "--facts", "f9")[0], 1)
        self.assertEqual(self.story()["engagement"], None)

    def test_unlink(self):
        run("fact", "add", "acme-project", "one", "--basis", "stated")
        run("link", "acme-topic-a", "acme-project", "--facts", "f1")
        run("unlink", "acme-topic-a", "--facts", "f1")
        self.assertEqual(self.story()["uses_facts"], [])
        self.assertEqual(self.story()["engagement"], "acme-project")
        run("unlink", "acme-topic-a")
        self.assertEqual(self.story()["engagement"], None)

    def test_decision_ownership_checked(self):
        with self.assertRaises(SystemExit):
            prep.build_parser().parse_args(["decision", "add", "acme-project", "--what", "x", "--ownership", "boss"])
        self.assertEqual(run("decision", "add", "acme-project", "--what", "Queue", "--why", "fewer moving parts",
                             "--alternatives", "Cron | Webhooks", "--ownership", "mine")[0], 0)
        d = prep.engagements()[0]["decisions"][0]
        self.assertEqual(d["alternatives"], ["Cron", "Webhooks"])


class TestMetricsAndWarnings(PrepCase):
    def test_metric_replace_and_remove(self):
        run("metric", "add", "acme-topic-a", "--name", "Orders", "--value", "700+", "--basis", "stated")
        run("metric", "add", "acme-topic-a", "--name", "Orders", "--value", "720", "--basis", "stated")
        self.assertEqual([m["value"] for m in self.story()["metrics"]], ["720"])
        self.assertEqual(run("metric", "rm", "acme-topic-a", "Nope")[0], 1)
        self.assertEqual(run("metric", "rm", "acme-topic-a", "Orders")[0], 0)
        self.assertEqual(self.story()["metrics"], [])

    def test_number_without_metric_warns(self):
        run("set", "acme-topic-a", "result", "Cut cost by 40% overall.")
        _, out = run("validate", "acme-topic-a")
        self.assertIn("40%", out)
        self.assertIn("no metric or fact behind it", out)

    def test_estimate_must_be_hedged(self):
        run("metric", "add", "acme-topic-a", "--name", "saving", "--value", "40%", "--basis", "estimated")
        run("set", "acme-topic-a", "result", "Cut cost by 40%.")
        _, out = run("validate", "acme-topic-a")
        self.assertIn("is an estimate", out)
        run("set", "acme-topic-a", "result", "Estimated cost cut of 40%.")
        _, out = run("validate", "acme-topic-a")
        self.assertNotIn("is an estimate", out)

    def test_never_say_is_an_error(self):
        run("set", "acme-topic-a", "never_say", "measured saving | guaranteed")
        run("set", "acme-topic-a", "result", "We had a measured saving of a lot.")
        code, out = run("validate", "acme-topic-a")
        self.assertEqual(code, 1)
        self.assertIn("never_say", out)

    def test_we_heavy_action_warns(self):
        run("set", "acme-topic-a", "action", "We built it and our team shipped it. I reviewed.")
        _, out = run("validate", "acme-topic-a")
        self.assertIn("make your own part clear", out)

    def test_spoken_length_warns(self):
        run("set", "acme-topic-a", "spoken.60s", " ".join(["word"] * 200))
        _, out = run("validate", "acme-topic-a")
        self.assertIn("spoken 60s is 200 words", out)

    def test_bad_spoken_key(self):
        self.assertEqual(run("set", "acme-topic-a", "spoken.5min", "x")[0], 1)


class TestFollowupsSearchExport(PrepCase):
    def test_followup_resolve_by_text_and_index(self):
        run("followup", "add", "acme-topic-a", "How were uploads checked?")
        code, _ = run("followup", "resolve", "acme-topic-a", "batch", "--answer", "two teams, one shared queue")
        self.assertEqual(code, 0)
        s = self.story()
        self.assertEqual(s["follow_ups"], ["How were uploads checked?"])
        self.assertEqual(s["resolved"][0]["answer"], "two teams, one shared queue")
        self.assertEqual(run("followup", "resolve", "acme-topic-a", "1")[0], 1)       # --answer required
        self.assertEqual(run("followup", "resolve", "acme-topic-a", "5", "--answer", "x")[0], 1)

    def test_search_finds_story_and_engagement(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "Ledger was the store", "--basis", "stated")
        _, out = run("search", "ledger")
        self.assertIn("engagement acme-project", out)
        self.assertIn("1 match", out)
        _, out = run("search", "batch size")
        self.assertIn("story acme-topic-a", out)

    def test_export_json_and_md(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "Used a stream", "--basis", "unsure")
        run("decision", "add", "acme-project", "--what", "Queue", "--why", "fewer moving parts", "--ownership", "mine")
        run("link", "acme-topic-a", "acme-project")
        _, out = run("export", "--story", "acme-topic-a")
        data = json.loads(out)
        self.assertEqual(data["stories"][0]["id"], "acme-topic-a")
        self.assertEqual(data["engagements"][0]["id"], "acme-project")
        _, md = run("export", "--story", "acme-topic-a", "--format", "md")
        self.assertIn("## Unsure (say 'I believe' or leave out)", md)
        self.assertIn("Used a stream", md)
        self.assertIn("Queue", md)
        self.assertEqual(run("export", "--format", "md")[0], 1)
        path = self.home / "out.json"
        run("export", "-o", str(path))
        self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["stories"]), 1)

    def test_new_story_checks_company_and_id(self):
        self.assertEqual(run("new", "acme-x", "--company", "nope", "--theme", "budget-financial")[0], 1)
        self.assertEqual(run("new", "acme-x", "--company", "acme", "--theme", "budget-financial")[0], 0)
        self.assertEqual(run("new", "acme-x", "--company", "acme", "--theme", "budget-financial")[0], 1)
        self.assertEqual(run("new", "acme-y", "--company", "acme", "--theme", "t", "--engagement", "missing")[0], 1)

    def test_no_engagement_warning_only_for_started_stories(self):
        _, out = run("validate", "acme-topic-a")
        self.assertNotIn("no engagement linked", out)
        run("set", "acme-topic-a", "situation", "x")
        _, out = run("validate", "acme-topic-a")
        self.assertIn("no engagement linked", out)

    def test_validate_exit_code_and_unknown_id(self):
        self.assertEqual(run("validate")[0], 0)
        self.assertEqual(run("validate", "nope")[0], 1)

    def test_status_counts_unsure(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "x", "--basis", "unsure")
        _, out = run("status")
        self.assertIn("1 unsure", out)


class TestHealth(PrepCase):
    def test_health_reports_v2_fields(self):
        run("engagement", "add", "acme-project", "--company", "acme", "--title", "Office move")
        run("fact", "add", "acme-project", "maybe polling", "--basis", "unsure")
        run("link", "acme-topic-a", "acme-project", "--facts", "f1")
        run("set", "acme-topic-a", "spoken.60s", "Short version.")
        h = prep.health(self.story())
        self.assertTrue(h["linked"])
        self.assertEqual(h["weak_facts"], 1)
        self.assertEqual(h["open_followups"], 1)
        self.assertEqual(h["spoken"], ["60s"])
        self.assertTrue(h["errors"])

    def test_health_unlinked(self):
        h = prep.health(self.story())
        self.assertFalse(h["linked"])
        self.assertEqual(h["weak_facts"], 0)


class TestCommands(PrepCase):
    def test_list_shows_every_story_and_filters_by_company(self):
        _, out = run("list")
        self.assertIn("acme-topic-a", out)
        self.assertIn("empty", out)
        self.assertEqual(run("list", "--company", "other")[1], "")

    def test_skeleton_is_an_alias_of_init(self):
        self.assertIs(prep.build_parser().parse_args(["skeleton"]).fn, prep.build_parser().parse_args(["init"]).fn)

    def test_new_story_uses_company_records_keyed_by_id(self):
        code, out = run("new", "acme-extra", "--company", "acme", "--theme", "mentoring")
        self.assertEqual(code, 0)
        self.assertIn("Created story acme-extra (Acme Corp / mentoring)", out)
        self.assertEqual(self.story("acme-extra")["company_name"], "Acme Corp")
        code, out = run("new", "x", "--company", "nope", "--theme", "t")
        self.assertEqual(code, 1)
        self.assertIn("Unknown company nope. Known: acme", out)
        self.assertEqual(run("new", "acme-extra", "--company", "acme", "--theme", "t")[0], 1)     # duplicate id

    def test_validate_returns_status_not_exception(self):
        args = prep.build_parser().parse_args(["validate"])
        self.assertEqual(args.fn(args), 0)

    def test_unknown_story_commands_fail_cleanly(self):
        for argv in (["show", "nope"], ["metric", "rm", "acme-topic-a", "zzz"], ["followup", "resolve", "acme-topic-a", "zzz", "--answer", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 1)


class TestInitFromResumeData(PrepCase):
    def test_init_builds_stories_per_theme_and_keeps_answers(self):
        bullets = [{"id": f"b{i}", "text": f"Built thing {i}", "themes": ["topic-b"], "sources": ["a"], "metrics": ["30%"],
                    "ignored": False, "needs_review": False} for i in range(5)]
        company = {"id": "globex", "name": "Globex", "bullets": bullets,
                   "roles": [{"start": f"{__import__('datetime').date.today().year - 1}-01", "end": None, "titles": ["T"]}]}
        prep.qr.load = lambda: ({"globex": company}, None)
        code, out = run("init")
        self.assertEqual(code, 0)
        self.assertIn("2 stories (1 new)", out)
        self.assertEqual(self.story("globex-topic-b")["metrics_on_resume"], ["30%"])
        run("set", "globex-topic-b", "situation", "kept answer")
        run("init")
        self.assertEqual(self.story("globex-topic-b")["situation"], "kept answer")
        self.assertEqual(self.story("acme-topic-a")["status"], "empty")        # not produced now, but kept
        self.assertEqual(sorted(tables.load_themes()), ["topic-a", "topic-b"])


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
        jd.write_text("Mentor engineers and review their designs.", encoding="utf-8")
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
        self.assertIn("acme-project", target.read_text(encoding="utf-8"))
        md = self.home / "story.md"
        self.assertEqual(run("export", "--story", "acme-topic-a", "--format", "md", "--output", str(md))[0], 0)
        self.assertIn("topic-a", md.read_text(encoding="utf-8"))

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
