"""Role-question provenance, local prompts, sessions and readiness."""
import json
from datetime import date, timedelta
from unittest import mock

from jk.interview import question_tables as qt
from jk.interview import prep, questions, readiness, sessions, tables, targets
from jk.resumes import tables as rt
from jk.user import profile
from tests.support import HomeCase, call, jobkit

ROLE = "Product Designer"
GENERAL = {"id": "task", "source": "general", "question": "How would you validate an interaction?"}


class QuestionTests(HomeCase):
    def save(self, role, *rows):
        """Save questions through the normal stdin command."""
        return call(questions.main, "save", role, "--seed", "-", stdin=json.dumps({"questions": rows}))

    def one(self, role=ROLE):
        """Read the first persisted question of a role."""
        return qt.load_roles(role)[0]["questions"][0]

    def start(self, *args):
        """Start a session and return its stored ID."""
        code, out, err = call(sessions.main, "new", "Practice", *args)
        self.assertEqual(code, 0, err)
        self.assertIn("Next item (question)", out)
        return out.split("Started session ")[1].split()[0]

    def test_ids_are_isolated_case_insensitive_and_updatable(self):
        self.assertEqual(self.save(ROLE, GENERAL)[0], 0)
        self.assertEqual(self.save("People Partner", GENERAL)[0], 0)
        original = self.one()["id"]
        self.assertNotEqual(original, self.one("People Partner")["id"])
        updated = {**GENERAL, "id": original, "question": "How would you test an interaction?"}
        self.assertEqual(self.save("  product   designer ", updated)[0], 0)
        self.assertEqual(self.one()["question"], updated["question"])
        self.assertEqual(len(qt.load_roles(ROLE)[0]["questions"]), 1)

    def test_reference_validation_is_atomic(self):
        self.assertEqual(self.save(ROLE, GENERAL)[0], 0)
        cited = {"source": "research", "question": "How do you plan a usability study?", "vetted": True,
                 "quote": "Describe your plan for a usability study.", "pulled": date.today().isoformat(),
                 "link": "https://handbook.example.org/interview"}
        for change in ({"quote": "word " * 41}, {"pulled": "invalid"}, {"vetted": False},
                       {"label": "general-knowledge"}, {"link": f"https://{sorted(targets.USER_HOSTS)[0]}/thread"}):
            with self.subTest(change=change):
                code, _, err = self.save(ROLE, {**GENERAL, "question": "Changed wording?"}, {**cited, **change})
                self.assertEqual(code, 1, err)
                self.assertIn("Nothing was saved", err)
                self.assertEqual(self.one()["question"], GENERAL["question"])
        self.assertEqual(self.save(ROLE, cited)[0], 0)
        self.assertEqual(qt.load_roles(ROLE)[0]["outcome"], qt.FOUND)

    def test_a_legacy_story_id_cannot_be_reused_as_a_question(self):
        item = questions.question_id(ROLE, GENERAL)
        tables.replace_stories({"stories": [{"id": item, "company": "acme", "company_name": "Acme",
                                            "theme": "t", "status": "draft"}]})
        code, _, err = self.save(ROLE, GENERAL)
        self.assertEqual(code, 1, err)
        self.assertIn("already used", err)
        self.assertEqual(qt.load_roles(), [])
        code, _, err = call(prep.main, "new", item + "-other", "--company", "acme", "--theme", "t")
        self.assertEqual(code, 1, err)
        self.assertIn("reserved for role questions", err)

    def test_unsuccessful_research_coexists_with_general_questions_and_ages(self):
        today = date.today()
        with mock.patch.object(questions, "date") as clock:
            clock.today.return_value = today - timedelta(days=31)
            self.assertEqual(call(questions.main, "none-found", ROLE)[0], 0)
        self.assertEqual(self.save(ROLE, GENERAL)[0], 0)
        self.assertIn("no qualifying sources", call(questions.main, "stale", ROLE)[1])
        self.assertIn("general-knowledge", call(questions.main, "list", ROLE)[1])
        self.assertEqual(qt.load_roles(ROLE)[0]["outcome"], qt.NONE_FOUND)

    def test_personal_questions_ground_claims_and_use_all_wordings_for_gaps(self):
        bullet = {"id": "line-a", "text": "Led a review of 12 interface changes.", "role_start": "2023",
                  "variants": ["Led an accessibility review of 12 interface changes."], "sources": [], "themes": [],
                  "skills": [], "metrics": ["12 interface changes"]}
        rt.replace_companies({"acme": {"id": "acme", "name": "Acme", "aliases": [],
                                        "roles": [{"start": "2023", "end": None, "titles": [ROLE], "sources": []}],
                                        "bullets": [bullet]}})
        rt.replace_skills({"groups": {}})
        args = ("personal", ROLE, "--jd", "-", "--requirement", "accessibility review", "--requirement", "survey design")
        code, _, err = call(questions.main, *args, stdin="Accessibility review and survey design.")
        self.assertEqual(code, 0, err)
        saved = qt.load_roles(ROLE)[0]["questions"]
        self.assertEqual([q["requirement"] for q in saved if "requirement" in q], ["survey design"])
        self.assertEqual([q["bullet"] for q in saved if "bullet" in q], ["line-a", "line-a"])
        self.assertTrue(all(q["source"] == "personal" and q["link"] is None for q in saved))

    def test_session_progress_readiness_and_removal(self):
        self.assertEqual(self.save(ROLE, GENERAL, {**GENERAL, "id": "next", "question": "What would you measure?"})[0], 0)
        self.assertEqual(self.save("People Partner", GENERAL)[0], 0)
        item, following = [q["id"] for q in qt.load_roles(ROLE)[0]["questions"]]
        sid = self.start("--mode", "questions", "--role", ROLE)
        result = call(sessions.main, "log", sid, item, "--question", GENERAL["question"],
                      "--answer", "I would observe participants.", "--confidence", "2")
        self.assertEqual(result[0], 0, result[2])
        code, out, err = call(readiness.main, "--role", ROLE)
        self.assertEqual(code, 0, err)
        self.assertIn("solid-once 1", out)
        self.assertNotIn("People Partner", out)
        self.assertEqual(call(questions.main, "remove", item)[0], 0)
        self.assertEqual(call(questions.main, "remove", following)[0], 0)
        code, out, err = call(sessions.main, "resume", sid)
        self.assertEqual(code, 0, err)
        self.assertIn("Skipping " + following, out)
        self.assertEqual(tables.load_session(sid)["log"][0]["answer"], "I would observe participants.")
        self.assertEqual(qt.load_progress(), {})

    def test_tutor_quiz_and_retest_and_exports(self):
        self.assertEqual(self.save(ROLE, GENERAL)[0], 0)
        item = self.one()["id"]
        sid = self.start("--mode", "tutor", "--topic", "questions", "--role", ROLE)
        answer = ("log", sid, item, "--question", GENERAL["question"], "--answer", "I would test it.", "--confidence", "2")
        self.assertEqual(call(sessions.main, *answer)[0], 0)
        self.assertEqual(qt.load_progress()[item]["confidence"], 1)
        self.assertEqual(call(sessions.main, *answer, "--grade", "Solid", "--quiz")[0], 0)
        self.assertEqual(qt.load_progress()[item]["confidence"], 2)
        qt.set_progress(item, qt.Progress(confidence=2, last_drilled=(date.today() - timedelta(days=40)).isoformat()))
        code, out, err = call(readiness.main, "--due", "--role", ROLE, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual([row["id"] for row in json.loads(out)], [item])
        sid = self.start("--due")
        self.assertEqual(tables.load_session(sid)["queue"], [{"id": item, "kind": "question"}])
        for kind in ("role-questions", "question-progress"):
            code, out, err = jobkit("export", "--only", kind)
            self.assertEqual(code, 0, err)
            self.assertIn(item, out)

    def test_profile_research_choice_can_be_remembered_and_cleared(self):
        profile.save({"resume_root": str(self.home)})
        self.assertIn("not asked yet", call(profile.main, "status")[1])
        self.assertEqual(call(profile.main, "set", "question_research", "no")[0], 0)
        self.assertEqual(profile.question_research(), "no")
        self.assertIn("question research: no", call(profile.main, "status")[1])
        self.assertEqual(call(profile.main, "set", "question_research", "maybe")[0], 1)
        self.assertEqual(profile.question_research(), "no")
        self.assertEqual(call(profile.main, "set", "question_research", "unset")[0], 0)
        self.assertIsNone(profile.question_research())
