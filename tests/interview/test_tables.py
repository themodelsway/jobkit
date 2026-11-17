"""Tests for plugins/jobkit/src/jk/interview/tables.py: round trips, integrity rules and the append-only answer log."""
import copy

from jk import common, store
from jk.interview import tables
from tests.seed_data import CARD, ENGAGEMENT, ENTRY, PROGRESS, STORY, session
from tests.support import HomeCase


class RoundTripTests(HomeCase):
    def test_catalog_and_progress(self):
        cat = {"dimensions": ["scale"], "scenarios_note": "n", "tracks": ["aws"], "cards": [CARD]}
        tables.replace_catalog(cat)
        tables.replace_progress({"vpc": PROGRESS})
        self.assertEqual(tables.load_catalog(), cat)
        self.assertEqual(tables.load_progress(), {"vpc": PROGRESS})

    def test_saving_the_catalog_again_keeps_progress(self):
        cat = {"cards": [CARD]}
        tables.replace_catalog(cat)
        tables.replace_progress({"vpc": PROGRESS})
        tables.replace_catalog({"cards": [CARD, {**CARD, "id": "s3", "name": "S3"}]})
        self.assertEqual(tables.load_progress(), {"vpc": PROGRESS})

    def test_engagements_with_children_and_stories(self):
        tables.replace_engagements({"schema_version": 2, "engagements": [ENGAGEMENT]})
        tables.replace_stories({"schema_version": 2, "stories": [STORY]})
        self.assertEqual(tables.load_engagements(), {"schema_version": 2, "engagements": [ENGAGEMENT]})
        self.assertEqual(tables.load_stories(), {"schema_version": 2, "stories": [STORY]})

    def test_removing_a_fact_is_stored(self):
        tables.replace_engagements({"engagements": [ENGAGEMENT]})
        smaller = copy.deepcopy(ENGAGEMENT)
        smaller["facts"].pop()
        tables.replace_engagements({"engagements": [smaller]})
        self.assertEqual([f["id"] for f in tables.load_engagements()["engagements"][0]["facts"]], ["f1"])

    def test_themes_tracks_questions_and_scope(self):
        tables.replace_themes({"topic-a": {"stories": ["a"], "questions": []}})
        tables.save_track("people-ops", {"name": "people-ops"})
        questions = [{"id": "q1", "category": "Scope", "question": "?", "themes": []}]
        tables.replace_questions(questions)
        tables.replace_lead_progress({"q1": {"confidence": 0, "principle": "", "notes": "", "last_drilled": None, "examples": {}}})
        tables.replace_company_facts({"acme": {"title": "Lead"}})
        self.assertEqual(tables.load_themes(), {"topic-a": {"stories": ["a"], "questions": []}})
        self.assertEqual(tables.track_names(), ["people-ops"])
        self.assertEqual(tables.load_questions(), questions)
        self.assertEqual(tables.load_company_facts(), {"acme": {"title": "Lead"}})

    def test_nothing_stored_reads_as_empty(self):
        self.assertIsNone(tables.load_catalog())
        self.assertIsNone(tables.load_stories())
        self.assertFalse(tables.has_questions())
        self.assertEqual(tables.load_engagements()["engagements"], [])


class SessionRuleTests(HomeCase):
    def setUp(self):
        super().setUp()
        tables.replace_catalog({"cards": [CARD]})          # a session may only name items that exist

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

    def test_a_different_creation_time_is_refused_and_nothing_changes(self):
        tables.save_session(session([ENTRY]))
        changed = {**session([ENTRY]), "title": "new", "queue": [], "created": "2026-12-01T09:00:00"}
        with self.assertRaisesRegex(common.ToolError, "creation time"):
            tables.save_session(changed)
        self.assertEqual(tables.load_session("s1"), session([ENTRY]))

    def test_listing_and_detail_agree_on_every_session_field(self):
        tables.save_session({**session([ENTRY]), "title": "changed", "status": "closed", "updated": "2026-11-02T08:00:00"})
        row, detail = tables.session_rows()[0], tables.load_session("s1")
        for field in ("id", "title", "mode", "status", "created", "updated"):
            self.assertEqual(row[field], detail[field], field)

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


class NamedWriteTests(HomeCase):
    def setUp(self):
        super().setUp()
        tables.replace_catalog({"cards": [CARD, {**CARD, "id": "s3", "name": "S3"}]})
        tables.replace_questions([{"id": "q1", "category": "Scope", "question": "?", "themes": []},
                               {"id": "q2", "category": "Scope", "question": "?", "themes": []}])
        tables.replace_progress({"vpc": PROGRESS, "s3": {**PROGRESS, "confidence": 0}})
        tables.replace_lead_progress({"q1": {"confidence": 1}, "q2": {"confidence": 0}})

    def test_set_card_progress_changes_one_card_and_leaves_the_others(self):
        tables.set_card_progress("vpc", {**PROGRESS, "confidence": 2})
        self.assertEqual({k: v["confidence"] for k, v in tables.load_progress().items()}, {"vpc": 2, "s3": 0})

    def test_set_card_progress_for_a_new_card_adds_it(self):
        tables.replace_progress({"vpc": PROGRESS})
        tables.set_card_progress("s3", PROGRESS)
        self.assertEqual(set(tables.load_progress()), {"vpc", "s3"})

    def test_set_lead_progress_changes_one_question_and_leaves_the_others(self):
        tables.set_lead_progress("q2", {"confidence": 2})
        self.assertEqual({k: v["confidence"] for k, v in tables.load_lead_progress().items()}, {"q1": 1, "q2": 2})

    def test_an_unknown_id_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "Unknown card"):
            tables.set_card_progress("nope", PROGRESS)
        with self.assertRaisesRegex(common.ToolError, "Unknown leadership question"):
            tables.set_lead_progress("nope", {"confidence": 0})

    def test_a_confidence_outside_0_to_2_is_refused_and_progress_is_unchanged(self):
        before, lead_before = tables.load_progress(), tables.load_lead_progress()
        for bad in (3, -1, "2", None, True):
            with self.subTest(confidence=bad):
                with self.assertRaisesRegex(common.ToolError, "Confidence"):
                    tables.set_card_progress("vpc", {**PROGRESS, "confidence": bad})
                with self.assertRaisesRegex(common.ToolError, "Confidence"):
                    tables.set_lead_progress("q1", {"confidence": bad})
                with self.assertRaisesRegex(common.ToolError, "Confidence"):
                    tables.replace_progress({"vpc": {**PROGRESS, "confidence": bad}})
                with self.assertRaisesRegex(common.ToolError, "Confidence"):
                    tables.replace_lead_progress({"q1": {"confidence": bad}})
        self.assertEqual((tables.load_progress(), tables.load_lead_progress()), (before, lead_before))


class ReferenceTests(HomeCase):
    def test_progress_for_an_unknown_card_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "Unknown card"):
            tables.replace_progress({"nope": PROGRESS})

    def test_lead_progress_for_an_unknown_question_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "Unknown leadership question"):
            tables.replace_lead_progress({"nope": {"confidence": 0}})

    def test_a_story_for_a_missing_engagement_is_refused_at_commit(self):
        with self.assertRaises(common.ToolError):
            tables.replace_stories({"stories": [STORY]})
        self.assertIsNone(tables.load_stories())

    def test_story_and_engagement_can_be_saved_in_one_change_in_any_order(self):
        with store.transaction():
            tables.replace_stories({"stories": [STORY]})
            tables.replace_engagements({"engagements": [ENGAGEMENT]})
        self.assertEqual(len(tables.load_stories()["stories"]), 1)

    def test_two_changes_that_fail_half_way_store_nothing(self):
        with self.assertRaises(common.ToolError), store.transaction():
            tables.replace_engagements({"engagements": [ENGAGEMENT]})
            tables.replace_stories({"stories": [STORY]})
            tables.replace_progress({"nope": PROGRESS})
        self.assertEqual(tables.load_engagements()["engagements"], [])
        self.assertIsNone(tables.load_stories())


class ItemReferenceTests(HomeCase):
    def setUp(self):
        super().setUp()
        tables.replace_catalog({"cards": [CARD]})

    def test_an_unknown_new_queue_entry_is_refused_and_nothing_is_stored(self):
        bad = {**session([ENTRY]), "queue": [{"id": "vpc", "kind": "card"}, {"id": "nope", "kind": "card"}]}
        with self.assertRaisesRegex(common.ToolError, "nope"):
            tables.save_session(bad)
        self.assertIsNone(tables.load_session("s1"))

    def test_an_unknown_new_log_entry_is_refused(self):
        tables.save_session(session([ENTRY]))
        with self.assertRaisesRegex(common.ToolError, "nope"):
            tables.save_session(session([ENTRY, {**ENTRY, "at": "2026-11-02T10:00:00", "item": "nope"}]))
        self.assertEqual(len(tables.load_session("s1")["log"]), 1)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaisesRegex(common.ToolError, "kind"):
            tables.save_session({**session(), "queue": [{"id": "vpc", "kind": "weird"}]})

    def test_a_removed_item_leaves_the_session_readable_and_savable(self):
        tables.save_session(session([ENTRY]))
        tables.replace_catalog({"cards": []})
        self.assertEqual(tables.load_session("s1"), session([ENTRY]))
        tables.save_session(session([ENTRY]))                       # nothing new, so nothing is re-checked
        self.assertEqual(len(tables.all_sessions()), 1)

    def test_a_removed_item_is_refused_for_a_new_log_entry(self):
        tables.save_session(session([ENTRY]))
        tables.replace_catalog({"cards": []})
        with self.assertRaisesRegex(common.ToolError, "vpc"):
            tables.save_session(session([ENTRY, {**ENTRY, "at": "2026-11-02T10:00:00"}]))

    def test_leader_and_story_kinds_are_checked_in_their_own_tables(self):
        tables.replace_questions([{"id": "q1", "category": "Scope", "question": "?", "themes": []}])
        tables.replace_engagements({"engagements": [ENGAGEMENT]})
        tables.replace_stories({"stories": [STORY]})
        queue = [{"id": "q1", "kind": "leader"}, {"id": STORY["id"], "kind": "story"}]
        tables.save_session({**session(), "queue": queue})
        with self.assertRaises(common.ToolError):
            tables.save_session({**session(sid="s2"), "queue": [{"id": "q1", "kind": "card"}]})
