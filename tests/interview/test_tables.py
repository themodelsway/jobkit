"""Tests for src/jobkit/interview/tables.py: round trips, integrity rules and the append-only answer log."""
import copy
import unittest

from jobkit import common, store
from jobkit.interview import tables
from tests.support import HomeCase

CARD = {"id": "vpc", "track": "aws", "kind": "service", "area": "Network", "name": "VPC", "tier": 1, "aliases": [],
        "members": [], "lifecycle": {"status": "active"}, "recent_changes": [], "verified_on": None}
PROGRESS = {"confidence": 1, "notes": "", "last_drilled": "2026-11-01", "links": {"acme": ["b1"]}}
ENGAGEMENT = {"id": "acme-platform", "company": "acme", "title": "Platform", "my_role": "Lead", "period": "2022",
              "summary": "s", "notes": None, "updated": "2026-11-01T10:00:00", "counters": {"f": 2, "d": 1},
              "facts": [{"id": "f1", "text": "12 engineers", "basis": "stated", "source": None, "note": None, "added": "d"},
                        {"id": "f2", "text": "x", "basis": "unsure", "source": None, "note": None, "added": "d"}],
              "decisions": [{"id": "d1", "what": "ECS", "why": "w", "alternatives": ["EKS"], "tradeoffs": "t",
                             "ownership": "mine"}],
              "people": [{"role": "Owner", "note": "n"}]}
STORY = {"id": "acme-platform-story", "company": "acme", "company_name": "Acme", "theme": "platform", "headline": "h",
         "status": "draft", "engagement": "acme-platform", "uses_facts": ["f1"], "updated": "2026-11-01T10:00:00",
         "metrics": [], "resolved": [{"q": "q", "answer": "a", "at": "t"}], "spoken": {"60s": None, "2min": None}}
ENTRY = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "question": "q", "answer": "a full answer",
         "grade": "solid", "confidence_after": 2, "tutor": False, "quiz": False}


def session(log=(), sid="s1"):
    return {"id": sid, "title": "t", "mode": "architecture", "status": "open", "created": "2026-11-01T09:00:00",
            "updated": "2026-11-01T09:00:00", "jd": None, "queue": [{"id": "vpc", "kind": "card"}], "log": list(log)}


class RoundTripTests(HomeCase):
    def test_catalog_and_progress(self):
        cat = {"dimensions": ["scale"], "scenarios_note": "n", "tracks": ["aws"], "cards": [CARD]}
        tables.save_catalog(cat)
        tables.save_progress({"vpc": PROGRESS})
        self.assertEqual(tables.load_catalog(), cat)
        self.assertEqual(tables.load_progress(), {"vpc": PROGRESS})

    def test_saving_the_catalog_again_keeps_progress(self):
        cat = {"cards": [CARD]}
        tables.save_catalog(cat)
        tables.save_progress({"vpc": PROGRESS})
        tables.save_catalog({"cards": [CARD, {**CARD, "id": "s3", "name": "S3"}]})
        self.assertEqual(tables.load_progress(), {"vpc": PROGRESS})

    def test_engagements_with_children_and_stories(self):
        tables.save_engagements({"schema_version": 2, "engagements": [ENGAGEMENT]})
        tables.save_stories({"schema_version": 2, "stories": [STORY]})
        self.assertEqual(tables.load_engagements(), {"schema_version": 2, "engagements": [ENGAGEMENT]})
        self.assertEqual(tables.load_stories(), {"schema_version": 2, "stories": [STORY]})

    def test_removing_a_fact_is_stored(self):
        tables.save_engagements({"engagements": [ENGAGEMENT]})
        smaller = copy.deepcopy(ENGAGEMENT)
        smaller["facts"].pop()
        tables.save_engagements({"engagements": [smaller]})
        self.assertEqual([f["id"] for f in tables.load_engagements()["engagements"][0]["facts"]], ["f1"])

    def test_themes_tracks_questions_and_scope(self):
        tables.save_themes({"topic-a": {"stories": ["a"], "questions": []}})
        tables.save_track("acmedata", {"name": "acmedata"})
        questions = [{"id": "q1", "category": "Scope", "question": "?", "themes": []}]
        tables.save_questions(questions)
        tables.save_lead_progress({"q1": {"confidence": 0, "principle": "", "notes": "", "last_drilled": None, "examples": {}}})
        tables.save_company_facts({"acme": {"title": "Lead"}})
        self.assertEqual(tables.load_themes(), {"topic-a": {"stories": ["a"], "questions": []}})
        self.assertEqual(tables.track_names(), ["acmedata"])
        self.assertEqual(tables.load_questions(), questions)
        self.assertEqual(tables.load_company_facts(), {"acme": {"title": "Lead"}})

    def test_nothing_stored_reads_as_empty(self):
        self.assertIsNone(tables.load_catalog())
        self.assertIsNone(tables.load_stories())
        self.assertFalse(tables.has_questions())
        self.assertEqual(tables.load_engagements()["engagements"], [])


class SessionRuleTests(HomeCase):
    def test_session_round_trip_with_queue_and_log(self):
        tables.save_session(session([ENTRY]))
        self.assertEqual(tables.load_session("s1"), session([ENTRY]))
        self.assertIsNone(tables.load_session("nope"))

    def test_a_later_drill_adds_an_entry_and_keeps_the_old_ones(self):
        tables.save_session(session([ENTRY]))
        second = {**ENTRY, "at": "2026-11-05T10:00:00", "answer": "better"}
        tables.save_session(session([ENTRY, second]))
        self.assertEqual(tables.load_session("s1")["log"], [ENTRY, second])

    def test_saving_again_does_not_duplicate_entries(self):
        tables.save_session(session([ENTRY]))
        tables.save_session(session([ENTRY]))
        self.assertEqual(len(tables.load_session("s1")["log"]), 1)

    def test_changing_or_removing_an_entry_is_refused(self):
        tables.save_session(session([ENTRY]))
        with self.assertRaisesRegex(common.ToolError, "only be added"):
            tables.save_session(session([{**ENTRY, "answer": "edited"}]))
        with self.assertRaisesRegex(common.ToolError, "only be added"):
            tables.save_session(session([]))
        self.assertEqual(tables.load_session("s1")["log"], [ENTRY])

    def test_the_database_itself_refuses_updates_and_deletes(self):
        tables.save_session(session([ENTRY]))
        for sql in ("UPDATE session_log SET answered=0", "DELETE FROM session_log",
                    "DELETE FROM session WHERE id='s1'"):
            with self.subTest(sql=sql), self.assertRaisesRegex(common.ToolError, "append-only|FOREIGN KEY"):
                with store.transaction() as conn:
                    conn.execute(sql)
        self.assertEqual(len(tables.load_session("s1")["log"]), 1)

    def test_summary_rows_count_distinct_items(self):
        tables.save_session(session([ENTRY, {**ENTRY, "at": "2026-11-02T10:00:00"}]))
        row = tables.session_rows()[0]
        self.assertEqual((row["id"], row["logged"], row["total"]), ("s1", 1, 1))

    def test_evidence_counts_only_real_practice(self):
        lesson = {**ENTRY, "at": "2026-11-02T10:00:00", "tutor": True}
        passed = {**ENTRY, "at": "2026-11-03T10:00:00", "tutor": True, "quiz": True}
        empty = {**ENTRY, "at": "2026-11-04T10:00:00", "answer": "  "}
        tables.save_session(session([ENTRY, lesson, passed, empty]))
        found = tables.evidence()["vpc"]
        self.assertEqual(found["answered"], {"2026-11-01", "2026-11-03"})
        self.assertEqual(found["graded2"], {"2026-11-01", "2026-11-03"})


class ReferenceTests(HomeCase):
    def test_progress_for_an_unknown_card_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "Unknown card"):
            tables.save_progress({"nope": PROGRESS})

    def test_lead_progress_for_an_unknown_question_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "Unknown leadership question"):
            tables.save_lead_progress({"nope": {"confidence": 0}})

    def test_a_story_for_a_missing_engagement_is_refused_at_commit(self):
        with self.assertRaises(common.ToolError):
            tables.save_stories({"stories": [STORY]})
        self.assertIsNone(tables.load_stories())

    def test_story_and_engagement_can_be_saved_in_one_change_in_any_order(self):
        with store.transaction():
            tables.save_stories({"stories": [STORY]})
            tables.save_engagements({"engagements": [ENGAGEMENT]})
        self.assertEqual(len(tables.load_stories()["stories"]), 1)

    def test_two_changes_that_fail_half_way_store_nothing(self):
        with self.assertRaises(common.ToolError), store.transaction():
            tables.save_engagements({"engagements": [ENGAGEMENT]})
            tables.save_stories({"stories": [STORY]})
            tables.save_progress({"nope": PROGRESS})
        self.assertEqual(tables.load_engagements()["engagements"], [])
        self.assertIsNone(tables.load_stories())


if __name__ == "__main__":
    unittest.main()
