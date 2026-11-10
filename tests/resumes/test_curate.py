"""Tests for `process-resumes curate` (src/jobkit/resumes/curate.py): every kind applies on rebuild and can be removed."""
import contextlib
import io

from jobkit.resumes import curate, process_resumes as proc, resume_data as rd, tables
from tests.resumes.test_extract import as_txt
from tests.resumes.test_integrity import EXTRA_BULLET, RebuildCase


class CurateCase(RebuildCase):
    def setUp(self):
        super().setUp()
        self.write("one.txt", as_txt().replace("WORK EXPERIENCE", f"WORK EXPERIENCE\nInitech      01/2010 - 12/2014\nEngineer\n• {EXTRA_BULLET}"))
        self.rebuild()

    def curate(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = proc.main(["curate", *argv])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def force(self):
        with contextlib.redirect_stdout(io.StringIO()):
            proc.build(proc.list_resumes([self.resumes]), self.resumes, force=True)

    def bullet(self, text=EXTRA_BULLET):
        return next(b for c in rd.load_companies().values() for b in c["bullets"] if b["text"] == text)

    def skill_names(self):
        return {s["name"] for group in rd.load_skills()["groups"].values() for s in group}


class ListAndErrorTests(CurateCase):
    def test_list_shows_every_kind_and_one_kind(self):
        out = self.curate("list")[1]
        for kind in curate.KINDS:
            self.assertIn(f"{kind}: 0", out)
        self.curate("add", "education", "BSc")
        out = self.curate("list", "education")[1]
        self.assertIn("education: 1", out)
        self.assertIn("BSc", out)
        self.assertNotIn("skill-drop", out)

    def test_bad_arguments_are_clear_errors(self):
        self.assertEqual(self.curate("add", "skill-merge", "only-one")[0], 1)
        self.assertEqual(self.curate("add", "skill-drop", "a", "b")[0], 1)
        self.assertEqual(self.curate("rm", "skill-drop", "never-added")[0], 1)
        self.assertEqual(self.curate("add", "no-such-kind", "x")[0], 2)

    def test_adding_twice_does_not_duplicate(self):
        self.curate("add", "skill-drop", "teamwork")
        self.curate("add", "skill-drop", "teamwork")
        self.assertEqual(tables.load_curation("curated")["skill_drop"], ["teamwork"])


class AppliesOnRebuildTests(CurateCase):
    def test_wrong_metric_flags_then_stops_after_removal(self):
        self.assertFalse(self.bullet().get("needs_review"))
        self.curate("add", "wrong-metric", "40%")
        self.force()
        self.assertTrue(self.bullet()["needs_review"])
        self.curate("rm", "wrong-metric", "40%")
        self.force()
        self.assertFalse(self.bullet().get("needs_review"))

    def test_theme_and_ignore(self):
        bid = self.bullet()["id"]
        self.curate("add", "theme", bid, "zzz-theme", "yyy-theme")
        self.curate("add", "ignore", bid)
        self.force()
        self.assertEqual(self.bullet()["themes"], ["zzz-theme", "yyy-theme"])
        self.assertTrue(self.bullet()["ignored"])
        self.curate("rm", "theme", bid)
        self.curate("rm", "ignore", bid)
        self.force()
        self.assertNotIn("zzz-theme", self.bullet()["themes"])
        self.assertFalse(self.bullet()["ignored"])

    def test_skill_drop(self):
        victim = sorted(self.skill_names())[0]
        self.curate("add", "skill-drop", victim)
        self.force()
        self.assertNotIn(victim, self.skill_names())
        self.curate("rm", "skill-drop", victim)
        self.force()
        self.assertIn(victim, self.skill_names())

    def test_skill_group_moves_a_skill(self):
        victim = sorted(self.skill_names())[0]
        self.curate("add", "skill-group", victim, "My Group")
        self.force()
        self.assertIn(victim, [s["name"] for s in rd.load_skills()["groups"]["My Group"]])
        self.curate("rm", "skill-group", victim)
        self.force()
        self.assertNotIn("My Group", rd.load_skills()["groups"])

    def test_skill_merge_renames_a_spelling(self):
        victim = sorted(self.skill_names())[0]
        self.curate("add", "skill-merge", victim, "Merged Name")
        self.force()
        self.assertIn("Merged Name", self.skill_names())
        self.assertNotIn(victim, self.skill_names())
        self.curate("rm", "skill-merge", victim)
        self.force()
        self.assertIn(victim, self.skill_names())

    def test_extra_skill_add_remove_one_and_group(self):
        self.curate("add", "extra-skill", "Tools", "Terraform", "TF")
        self.curate("add", "extra-skill", "Tools", "Ansible")
        self.force()
        self.assertEqual({s["name"] for s in rd.load_skills()["groups"]["Tools"]}, {"Terraform", "Ansible"})
        self.assertEqual(self.curate("rm", "extra-skill", "Tools", "Ansible")[0], 0)
        self.force()
        self.assertEqual({s["name"] for s in rd.load_skills()["groups"]["Tools"]}, {"Terraform"})
        self.curate("rm", "extra-skill", "Tools", "Terraform")
        self.force()
        self.assertNotIn("Tools", rd.load_skills()["groups"])

    def test_tag_only_is_kept_out_of_skills(self):
        self.curate("add", "tag-only", "Leadership")
        self.force()
        self.assertEqual(rd.load_skills()["tag_only"], ["Leadership"])

    def test_certification_and_education_replace_the_resume_sections(self):
        self.curate("add", "certification", "Cert One", "--issued", "2024-01")
        self.curate("add", "education", "BSc Example")
        self.force()
        profile = rd.load_profile()
        self.assertEqual(profile["certifications"], [{"name": "Cert One", "issued": "2024-01", "expires": None}])
        self.assertEqual(profile["education"], ["BSc Example"])
        self.curate("rm", "certification", "Cert One")
        self.assertEqual(tables.load_curation("curated")["certifications"], [])

    def test_empty_curated_list_leaves_the_parsed_one(self):
        self.curate("add", "education", "BSc Example")
        self.curate("rm", "education", "BSc Example")
        data = {"companies": {}, "skills": {"groups": {}},
                "profile": {**rd.empty_profile(), "education": ["Parsed degree"]}}
        proc.apply_curated(data)
        self.assertEqual(data["profile"]["education"], ["Parsed degree"])

    def test_add_says_the_curated_list_replaces_the_parsed_one(self):
        for argv in (("education", "BSc Example"), ("certification", "Cert One")):
            note = self.curate("add", *argv)[1]
            self.assertIn("replaces the list parsed from your resumes", note)
        self.assertNotIn("replaces the list", self.curate("add", "tag-only", "Leadership")[1])

    def test_summary_angle(self):
        data = {"companies": {}, "skills": {"groups": {}}, "profile": {**rd.empty_profile(),
                "summaries": [{"id": "sum-1", "text": "Engineer.", "angles": []}]}}
        self.curate("add", "summary-angle", "sum-1", "cloud", "data")
        proc.apply_themes(data)
        self.assertEqual(data["profile"]["summaries"][0]["angles"], ["cloud", "data"])
        self.curate("rm", "summary-angle", "sum-1")
        proc.apply_themes(data)
        self.assertEqual(data["profile"]["summaries"][0]["angles"], ["cloud", "data"])      # kept: nothing overrides it


class SurviveAndOrphanTests(CurateCase):
    def test_curation_survives_rebuilds_unchanged(self):
        self.curate("add", "skill-drop", "teamwork")
        self.curate("add", "theme", self.bullet()["id"], "zzz-theme")
        before = {f: tables.load_curation(f) for f in tables.CURATION_FILES}
        self.rebuild()
        self.force()
        self.assertEqual({f: tables.load_curation(f) for f in tables.CURATION_FILES}, before)

    def test_a_changed_bullet_leaves_an_orphan_that_is_reported_not_removed(self):
        bid = self.bullet()["id"]
        self.curate("add", "theme", bid, "zzz-theme")
        self.write("one.txt", as_txt().replace("WORK EXPERIENCE", "WORK EXPERIENCE\nInitech      01/2010 - 12/2014\nEngineer\n"
                                                                  "• Reduced build times by 45% with a shared cache."))
        out = self.rebuild()
        self.assertIn("WARNING: 1 entr", out)
        self.assertEqual(tables.load_curation("themes")["themes"], {bid: ["zzz-theme"]})
        self.assertIn(f"theme {bid}", rd.orphan_curation(rd.load_companies(), rd.load_profile(), rd.load_themes_file()))


class CurationRemovalTests(CurateCase):
    def test_removed_curation_is_undone_without_force(self):
        self.curate("add", "wrong-metric", "40%")
        self.curate("add", "extra-skill", "Tools", "Terraform")
        self.curate("add", "theme", self.bullet()["id"], "cache-theme")
        self.rebuild()
        self.assertTrue(self.bullet()["needs_review"])
        self.assertIn("Terraform", self.skill_names())
        self.assertEqual(self.bullet()["themes"], ["cache-theme"])
        for kind, *values in (("wrong-metric", "40%"), ("extra-skill", "Tools", "Terraform"),
                              ("theme", self.bullet()["id"])):
            self.assertEqual(self.curate("rm", kind, *values)[0], 0)
        self.rebuild()
        self.assertFalse(self.bullet().get("needs_review"))
        self.assertNotIn("Terraform", self.skill_names())
        self.assertEqual(self.bullet()["themes"], [])

    def test_dropped_skill_comes_back_without_force(self):
        victim = sorted(self.skill_names())[0]
        self.curate("add", "skill-drop", victim)
        self.rebuild()
        self.assertNotIn(victim, self.skill_names())
        self.curate("rm", "skill-drop", victim)
        self.rebuild()
        self.assertIn(victim, self.skill_names())

    def test_unchanged_curation_does_not_rebuild(self):
        self.curate("add", "wrong-metric", "40%")
        self.assertIn("curation changed", self.rebuild())
        out = self.rebuild()
        self.assertNotIn("curation changed", out)
        self.assertIn("0 new/changed", out)
