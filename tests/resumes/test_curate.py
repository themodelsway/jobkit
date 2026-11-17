"""Tests for `process-resumes curate` (plugins/jobkit/src/jk/resumes/curate.py): every kind applies on rebuild and can be removed."""
import contextlib
import io
import unittest

from jk.resumes import curate, tables
from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from tests.resumes.support import EXTRA_BULLET, RebuildCase, as_txt
from tests.support import call


class CurateCase(RebuildCase):
    def setUp(self):
        super().setUp()
        self.write("one.txt", as_txt().replace("WORK EXPERIENCE", f"WORK EXPERIENCE\nAcme 3      01/2010 - 12/2014\nEngineer\n• {EXTRA_BULLET}"))
        self.rebuild()

    def curate(self, *argv):
        """Run `process-resumes curate`; (status, stdout, stderr)."""
        return call(proc.main, "curate", *argv)

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

    def test_usage_error_names_the_kind(self):
        code, _, err = self.curate("add", "flagged-number", "40%", "35%")
        self.assertEqual(code, 1)
        self.assertIn("usage: curate add flagged-number NUMBER", err)

    def test_adding_twice_does_not_duplicate(self):
        self.curate("add", "skill-drop", "teamwork")
        self.curate("add", "skill-drop", "teamwork")
        self.assertEqual(tables.load_curation("curated")["skill_drop"], ["teamwork"])


class FlaggedNumberMatchTests(unittest.TestCase):
    def flagged(self, numbers, *texts):
        bullets = [{"id": str(i), "text": text, "metrics": [], "needs_review": False} for i, text in enumerate(texts)]
        data = {"companies": {"acme": {"bullets": bullets}}}
        proc.flag_review(data, numbers)
        return [b["text"] for b in bullets if b["needs_review"]]

    def test_a_plain_count_is_flagged_as_a_whole_number(self):
        self.assertEqual(self.flagged(["12"], "Managed a team of 12 engineers.", "Led a team of 120 people.",
                                      "Grew output 1.25 times.", "Cut lead time by 12%."),
                         ["Managed a team of 12 engineers.", "Cut lead time by 12%."])

    def test_a_number_with_a_unit_is_not_found_inside_a_longer_one(self):
        self.assertEqual(self.flagged(["40%"], "Cut cost by 40%.", "Grew revenue by 140%."), ["Cut cost by 40%."])
        self.assertEqual(self.flagged(["$2.4M"], "Saved $2.4m a year."), ["Saved $2.4m a year."])
        self.assertEqual(self.flagged(["200"], "Served 1,200 users.", "Served 200 users."), ["Served 200 users."])


class AppliesOnRebuildTests(CurateCase):
    def test_flagged_number_flags_then_stops_after_removal(self):
        self.assertFalse(self.bullet().get("needs_review"))
        self.curate("add", "flagged-number", "40%")
        self.force()
        self.assertTrue(self.bullet()["needs_review"])
        self.curate("rm", "flagged-number", "40%")
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

    def test_correcting_one_degree_keeps_the_others_when_the_whole_list_is_saved(self):
        parsed = ["BSc Example, First University", "MSc Example, Second University"]
        self.curate("add", "education", "BSc Example, Correct University")
        self.curate("add", "education", "MSc Example, Second University")
        data = {"companies": {}, "skills": {"groups": {}}, "profile": {**rd.empty_profile(), "education": list(parsed)}}
        proc.apply_curated(data)
        self.assertEqual(data["profile"]["education"], ["BSc Example, Correct University", "MSc Example, Second University"])

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

    def test_summary_positioning(self):
        data = {"companies": {}, "skills": {"groups": {}}, "profile": {**rd.empty_profile(),
                "summaries": [{"id": "sum-1", "text": "Summary.", "angles": []}]}}
        self.curate("add", "positioning-word", "focus-a")
        self.curate("add", "positioning-word", "focus-b")
        self.curate("add", "summary-positioning", "sum-1", "focus-a", "focus-b")
        proc.apply_themes(data)
        self.assertEqual(data["profile"]["summaries"][0]["angles"], ["focus-a", "focus-b"])
        self.curate("rm", "summary-positioning", "sum-1")
        proc.apply_themes(data)
        self.assertEqual(data["profile"]["summaries"][0]["angles"], ["focus-a", "focus-b"])      # kept: nothing overrides it


class ThemeListTests(CurateCase):
    def test_the_built_in_themes_match_the_tables_that_use_them(self):
        from jk.interview import lead, prep
        from jk.resumes import query_resume as qr
        used = set(qr.THEME_HINTS) | set(prep.QUESTIONS) | {t for s in lead.SEED for t in s.themes}
        self.assertEqual(set(rd.BUILTIN_THEMES), used)

    def test_themes_verb_lists_built_in_and_own_words(self):
        code, out, _ = self.curate("themes")
        self.assertEqual(code, 0)
        self.assertIn("team-leadership", out)
        self.assertIn("Summary positioning: none yet", out)
        self.curate("add", "theme-word", "topic-a")
        self.curate("add", "positioning-word", "focus-a")
        out = self.curate("themes")[1]
        self.assertIn("topic-a", out)
        self.assertIn("Summary positioning: focus-a", out)

    def test_unknown_theme_is_kept_with_a_warning(self):
        bullet = self.bullet()["id"]
        code, out, _ = self.curate("add", "theme", bullet, "topic-a", "mentoring")
        self.assertEqual(code, 0)
        self.assertIn("topic-a is not a theme the tools use", out)
        self.assertIn("curate add theme-word", out)
        self.assertNotIn("mentoring is not", out)
        self.curate("add", "theme-word", "topic-a")
        self.assertEqual(self.curate("add", "theme", bullet, "topic-a")[1].count("Note:"), 0)

    def test_summary_positioning_needs_an_own_positioning_word(self):
        code, _, err = self.curate("add", "summary-positioning", "sum-1", "focus-a")
        self.assertEqual(code, 1)
        self.assertIn("No positioning words yet", err)
        self.curate("add", "positioning-word", "focus-b")
        code, _, err = self.curate("add", "summary-positioning", "sum-1", "focus-a")
        self.assertEqual(code, 1)
        self.assertIn("Unknown summary positioning focus-a. Use only: focus-b", err)

    def test_vocabulary_is_used_at_once_and_other_curation_after_a_rebuild(self):
        self.assertIn("It is used from now on.", self.curate("add", "theme-question", "topic-a", "Question?")[1])
        self.assertIn("It is used from now on.", self.curate("add", "theme-word", "topic-a")[1])
        self.assertIn("Run `process-resumes` to apply it.", self.curate("add", "skill-drop", "teamwork")[1])

    def test_a_vocabulary_word_must_be_lowercase_words_joined_by_hyphens(self):
        for bad in ("Topic A", "topic_a", "topic--a"):
            code, _, err = self.curate("add", "theme-word", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("is not a word", err)


class OwnVocabularyMatchingTests(CurateCase):
    def test_an_own_theme_is_found_in_a_job_description_by_its_hints_or_its_own_spelling(self):
        from jk.resumes import query_resume as qr
        self.curate("add", "theme-word", "topic-a", "first phrase", "Second Phrase")
        self.curate("add", "theme-word", "topic-b")
        self.assertIn("topic-a", qr.infer_themes("needs a second phrase here", []))
        self.assertIn("topic-b", qr.infer_themes("experience with topic b", []))
        self.assertNotIn("topic-a", qr.infer_themes("topic a", []))

    def test_positioning_words_count_their_hints_in_a_job_description(self):
        from jk.resumes import query_resume as qr
        self.curate("add", "positioning-word", "focus-a", "phrase one", "phrase two")
        self.assertEqual(qr.jd_angles("phrase one and phrase two, phrase one again"), {"focus-a": 3})
        self.assertEqual(qr.jd_angles("nothing relevant"), {})

    def test_theme_questions_are_kept_per_theme(self):
        self.curate("add", "theme-question", "topic-a", "First question?", "Second question?")
        self.assertEqual(rd.theme_questions(), {"topic-a": ["First question?", "Second question?"]})
        self.curate("rm", "theme-question", "topic-a")
        self.assertEqual(rd.theme_questions(), {})


class BatchTests(CurateCase):
    def batch(self, kind, text):
        """Run `process-resumes curate add KIND -` with the text on standard input."""
        return call(proc.main, "curate", "add", kind, "-", stdin=text)

    def test_many_themes_in_one_call(self):
        bullet = self.bullet()["id"]
        code, out, err = self.batch("theme", f"# tags\n{bullet} mentoring budget-financial\nother-id mentoring leadership\n")
        self.assertEqual(code, 0, err)
        self.assertIn("Added 2 theme entries.", out)
        self.assertEqual(out.count("Note:"), 1)
        self.assertIn("leadership is not a theme", out)
        themes = tables.load_curation("themes")["themes"]
        self.assertEqual(themes[bullet], ["mentoring", "budget-financial"])
        self.assertEqual(themes["other-id"], ["mentoring", "leadership"])

    def test_an_unclosed_quote_is_a_command_error_naming_the_line(self):
        bullet = self.bullet()["id"]
        code, _, err = self.batch("theme", f"{bullet} mentoring\n{bullet} \"unterminated\n")
        self.assertEqual(code, 1)
        self.assertIn("Line 2", err)
        self.assertNotIn("Traceback", err)

    def test_one_bad_line_saves_nothing(self):
        bullet = self.bullet()["id"]
        self.curate("add", "positioning-word", "focus-a")
        code, _, err = self.batch("summary-positioning", f"{bullet} focus-a\n{bullet} nonsense\n")
        self.assertNotEqual(code, 0)
        self.assertIn("Unknown summary positioning nonsense", err)
        self.assertNotIn(bullet, (tables.load_curation("themes") or {}).get("summary_angles", {}))

    def test_quotes_group_words_and_empty_input_is_refused(self):
        self.assertEqual(self.batch("education", '"BSc Example Degree"\n"MSc Other Degree"\n')[0], 0)
        self.assertEqual(tables.load_curation("curated")["education"], ["BSc Example Degree", "MSc Other Degree"])
        self.assertNotEqual(self.batch("theme", "\n  \n")[0], 0)


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
        self.write("one.txt", as_txt().replace("WORK EXPERIENCE", "WORK EXPERIENCE\nAcme 3      01/2010 - 12/2014\nEngineer\n"
                                                                  "• Reduced build times by 45% with a shared cache."))
        out = self.rebuild()
        self.assertIn("WARNING: 1 entr", out)
        self.assertEqual(tables.load_curation("themes")["themes"], {bid: ["zzz-theme"]})
        self.assertIn(f"theme {bid}", rd.orphan_curation(rd.load_companies(), rd.load_profile(), rd.load_themes_file()))


class CurationRemovalTests(CurateCase):
    def test_removed_curation_is_undone_without_force(self):
        self.curate("add", "flagged-number", "40%")
        self.curate("add", "extra-skill", "Tools", "Terraform")
        self.curate("add", "theme", self.bullet()["id"], "cache-theme")
        self.rebuild()
        self.assertTrue(self.bullet()["needs_review"])
        self.assertIn("Terraform", self.skill_names())
        self.assertEqual(self.bullet()["themes"], ["cache-theme"])
        for kind, *values in (("flagged-number", "40%"), ("extra-skill", "Tools", "Terraform"),
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
        self.curate("add", "flagged-number", "40%")
        self.assertIn("curation changed", self.rebuild())
        out = self.rebuild()
        self.assertNotIn("curation changed", out)
        self.assertIn("0 new/changed", out)
