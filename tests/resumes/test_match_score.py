"""The match-score command end to end on a made-up resume stored in a temporary database."""
import contextlib
import copy
import io
import json
import unittest
from unittest import mock

from jobkit import records, store
from jobkit.resumes import match_bands as mb
from jobkit.resumes import match_engine as me
from jobkit.resumes import match_facts as mf
from jobkit.resumes import match_score as ms
from jobkit.resumes import match_tables
from jobkit.resumes import tables
from tests.resumes.match_fixtures import facts, request
from tests.support import HomeCase

POSTING = """Senior Engineer

Qualifications:
- Bachelor's degree in Computer Science.
- 5+ years of experience.

Responsibilities:
- Lead a team of 10 engineers.
- Strong AWS experience.
"""


def seed(company_edit=None):
    """Store the made-up resume in the current database."""
    data = facts()
    companies = copy.deepcopy(dict(data.companies))
    if company_edit:
        company_edit(companies)
    tables.save_companies(companies)
    tables.save_skills(dict(data.skills))
    tables.save_profile({"summaries": [], "education": list(data.education),
                         "certifications": list(data.certifications), "profile_points": [], "projects": []})


class MatchCase(HomeCase):
    def setUp(self):
        super().setUp()
        seed()
        self.posting = self.home / "posting.txt"
        self.posting.write_text(POSTING, encoding="utf-8")
        self.requests = self.home / "requests.json"
        self.write_request(request())

    def write_request(self, data):
        self.requests.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with (contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
              mock.patch("sys.stdin", io.StringIO(stdin))):
            code = ms.main([str(a) for a in argv])
        store.close()
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *extra):
        code, out, err = self.cli("run", self.requests, "--jd", self.posting, "--json", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)


class ExtractTests(MatchCase):
    def test_code_items_and_no_cache_at_first(self):
        code, out, err = self.cli("extract", "--jd", self.posting)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        ids = {i["id"] for i in data["code_items"]}
        self.assertFalse(data["cached"])
        self.assertTrue({"code:skill:aws", "code:degree:1", "code:years"} <= ids, ids)

    def test_stored_result_ends_the_flow(self):
        self.run_json()
        data = json.loads(self.cli("extract", "--jd", self.posting)[1])
        self.assertTrue(data["cached"])
        self.assertIn("not any employer's applicant tracking system score", data["report"])

    def test_crlf_and_lf_postings_share_a_key(self):
        first = json.loads(self.cli("extract", "--jd", self.posting)[1])["key"]
        self.posting.write_bytes(POSTING.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(json.loads(self.cli("extract", "--jd", self.posting)[1])["key"], first)

    def test_missing_jd_and_double_stdin(self):
        self.assertEqual(self.cli("extract")[0], 1)
        code, _, err = self.cli("run", "-", "--jd", "-")
        self.assertEqual(code, 1)
        self.assertIn("standard input", err)


class CheckTests(MatchCase):
    def test_check_reports_flags_and_code_items(self):
        data = request()
        data["requirements"][1]["flag"] = {"kind": "level", "readings": ["partial", "substantial"]}
        self.write_request(data)
        code, out, err = self.cli("check", self.requests, "--jd", self.posting)
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual([f["id"] for f in result["flags"]], ["r2"])
        self.assertIn("code:years", result["code_items_not_in_request"])
        self.assertEqual(len(result["assumptions"]), 1)

    def test_invalid_request_exits_1_and_changes_nothing(self):
        data = request()
        data["requirements"][0]["evidence"] = ["bullet:nope"]
        data["requirements"][1]["category"] = "hobbies"
        self.write_request(data)
        code, _, err = self.cli("run", self.requests, "--jd", self.posting)
        self.assertEqual(code, 1)
        self.assertIn("requirements[0] (r1).evidence[0]", err)
        self.assertIn("requirements[1] (r2).category", err)
        self.assertEqual(match_tables.list_results(), [])

    def test_empty_request_says_nothing_to_score(self):
        self.write_request(request(requirements=[]))
        code, _, err = self.cli("run", self.requests, "--jd", self.posting)
        self.assertEqual(code, 1)
        self.assertIn("nothing to score", err)

    def test_shared_line_id_asks_for_the_company_form(self):
        data = request()
        data["requirements"][0]["evidence"] = ["bullet:dup"]
        self.write_request(data)
        self.assertIn("bullet:COMPANY_ID:dup", self.cli("check", self.requests, "--jd", self.posting)[2])


class RunTests(MatchCase):
    def test_report_has_gaps_before_scores_and_the_caveat(self):
        code, out, err = self.cli("run", self.requests, "--jd", self.posting)
        self.assertEqual(code, 0, err)
        self.assertLess(out.index("Must-haves that are not fully shown"), out.index("How well your profile matches"))
        for text in ("not shown in your profile yet", "Related experience, not counted: ran a platform",
                     "Level of the role: manager", "not any employer's applicant tracking system score"):
            self.assertIn(text, out)
        self.assertTrue(out.rstrip().endswith("may still change."))
        self.assertNotIn("ATS", out)
        self.assertNotIn("not demonstrated", out)

    def test_flag_widens_the_range_and_is_explained(self):
        data = request()
        data["requirements"][1]["flag"] = {"kind": "level", "readings": ["partial", "substantial"]}
        self.write_request(data)
        body = self.run_json()
        self.assertGreater(body["score"]["upper"], body["score"]["lower"])
        self.assertIn('"Lead a team of 10"', body["assumptions"][0])
        self.assertEqual([r["source"] for r in body["requirements"]], ["claude", "fallback", "claude"])

    def test_code_rated_item_uses_the_codes_level(self):
        data = request()
        data["requirements"][0].update(id="code:skill:aws", level="partial", evidence=["bullet:b1"])
        self.write_request(data)
        body = self.run_json()
        self.assertEqual((body["requirements"][0]["level"], body["requirements"][0]["source"]), ("full", "code"))
        self.assertIn("code pass says full", body["code_pass_notes"][0])

    def test_same_inputs_give_the_same_stored_result(self):
        first = self.run_json()
        second = self.run_json()
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(len(match_tables.list_results()), 1)

    def test_confidence_changes_no_number(self):
        before = self.run_json()["score"]
        data = request()
        data["requirements"][0]["confidence"] = 0.1
        data["requirements"][1]["confidence"] = 0.2
        self.write_request(data)
        self.assertEqual(self.run_json()["score"], before)

    def test_a_changed_resume_line_gives_a_new_key(self):
        first = self.run_json()["key"]
        seed(lambda c: c["acme"]["bullets"].append({"id": "n1", "text": "A new line", "skills": [], "themes": [],
                                                    "metrics": [], "sources": []}))
        second = self.run_json()["key"]
        self.assertNotEqual(first, second)

    def test_a_rebuild_that_changes_no_text_keeps_the_resume_fingerprint(self):
        before = mf.resume_fingerprint(mf.load_facts())
        store.close()
        seed(lambda c: c["acme"]["bullets"][0].update(id="renamed-id"))
        self.assertEqual(mf.resume_fingerprint(mf.load_facts()), before)

    def test_old_entries_are_pruned_when_a_run_finishes(self):
        self.run_json()
        with store.transaction() as conn:
            conn.execute("UPDATE match_result SET last_used='2020-01-01T00:00:00'")
        data = request(label="another")
        self.write_request(data)
        self.posting.write_text(POSTING + "\nMore text.", encoding="utf-8")
        self.run_json()
        self.assertEqual([r["label"] for r in match_tables.list_results()], ["another"])

    def test_list_and_show(self):
        key = self.run_json()["key"]
        out = self.cli("list")[1]
        self.assertIn(key, out)
        self.assertIn("1 stored result(s)", out)
        self.assertIn("How well your profile matches", self.cli("show", key[:6])[1])
        self.assertEqual(self.cli("show", "zzzz")[0], 1)

    def test_output_file(self):
        target = self.home / "report.txt"
        code, out, _ = self.cli("run", self.requests, "--jd", self.posting, "-o", target)
        self.assertEqual(code, 0)
        self.assertIn("Wrote", out)
        self.assertIn("How well your profile matches", target.read_text(encoding="utf-8"))

    def test_band_option_overrides_the_request(self):
        self.assertEqual(self.run_json("--band", "executive")["band"], "executive")
        self.assertEqual(self.cli("run", self.requests, "--jd", self.posting, "--band", "nope")[0], 1)

    def test_stdin_for_the_request(self):
        code, out, err = self.cli("run", "-", "--jd", self.posting, stdin=self.requests.read_text(encoding="utf-8"))
        self.assertEqual(code, 0, err)
        self.assertIn("How well", out)


class BandsFileTests(MatchCase):
    def test_user_band_is_available_and_changes_the_key(self):
        first = json.loads(self.cli("extract", "--jd", self.posting)[1])["key"]
        weights = {c: 0 for c in me.CATEGORIES} | {"core_skills": 0.6, "impact": 0.4}
        (self.home / "profile").mkdir(exist_ok=True)
        mb.bands_file().write_text(json.dumps({"sales": weights}), encoding="utf-8")
        self.assertEqual(self.run_json("--band", "sales")["band"], "sales")
        self.assertNotEqual(json.loads(self.cli("extract", "--jd", self.posting)[1])["key"], first)

    def test_bad_bands_file_is_reported_with_its_name(self):
        (self.home / "profile").mkdir(exist_ok=True)
        mb.bands_file().write_text(json.dumps({"x": {"core_skills": 1}}), encoding="utf-8")
        code, _, err = self.cli("extract", "--jd", self.posting)
        self.assertEqual(code, 1)
        self.assertIn("match-bands.json", err)
        mb.bands_file().write_text("{not json", encoding="utf-8")
        self.assertIn("match-bands.json", self.cli("extract", "--jd", self.posting)[2])


class ExportTests(MatchCase):
    def test_results_are_exported_and_counted(self):
        self.run_json()
        data = records.kind("match-results").export()
        entry = next(iter(data.values()))
        self.assertEqual(entry["body"]["rubric_version"], me.RUBRIC_VERSION)
        self.assertEqual(entry["body"]["weights_version"], me.WEIGHTS_VERSION)
        self.assertEqual(records.counts()["match-results"], 1)

    def test_no_resume_data_is_a_clear_error(self):
        with store.transaction() as conn:
            conn.execute("DELETE FROM meta WHERE key='resume.skills'")
        code, _, err = self.cli("run", self.requests, "--jd", self.posting)
        self.assertEqual(code, 1)
        self.assertIn("process-resumes", err)


if __name__ == "__main__":
    unittest.main()
