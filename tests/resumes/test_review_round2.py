"""Regression tests for the second review: one job with two end dates (DM-1, ME-1), hyphenated employers (PA-1),
curation removal on a normal rebuild (DM-2) and everything a deleted resume contributed (DM-3).
Run: .venv/bin/python -m unittest discover -s tests -t ."""
from types import SimpleNamespace

from jobkit.resumes import extract
from jobkit.resumes import match_facts as mf
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables
from tests.resumes.test_curate import CurateCase
from tests.resumes.test_extract import as_txt
from tests.resumes.test_integrity import RebuildCase

PRESENT = "03/2021 - Present"
ENDED = "03/2021 - 06/2022"
EXTRAS = ("\nEDUCATION\nBSc Physics, Example University\nCERTIFICATIONS\n• Example Certified Practitioner\n"
          "PROJECTS\nBuilt a hobby compiler in Rust\n")


def acme_roles() -> list[dict]:
    return rd.load_companies()["acme-corp"]["roles"]


def second_resume() -> str:
    """A tailored resume with its own headline, education, certification, project and a different Globex title."""
    text = as_txt().replace("Senior Software Engineer\n", "Senior Software Engineer\nWeb performance specialist\n")
    return text.replace("Senior Engineer", "Staff Engineer") + EXTRAS


class OneJobTwoEndDatesTests(RebuildCase):
    def test_present_and_a_real_end_date_are_one_role_with_the_end_date(self):
        self.write("2024.txt", as_txt())
        self.write("2025.txt", as_txt().replace(PRESENT, ENDED))
        self.rebuild()
        roles = acme_roles()
        self.assertEqual([(r["start"], r["end"]) for r in roles], [("2021-03", "2022-06")])

    def test_end_date_goes_back_to_present_when_its_file_goes(self):
        self.write("2024.txt", as_txt())
        self.write("2025.txt", as_txt().replace(PRESENT, ENDED))
        self.rebuild()
        (self.resumes / "2025.txt").unlink()
        self.rebuild()
        self.assertEqual([(r["start"], r["end"]) for r in acme_roles()], [("2021-03", None)])

    def test_order_of_files_does_not_matter(self):
        self.write("a.txt", as_txt().replace(PRESENT, ENDED))
        self.write("b.txt", as_txt())
        self.rebuild()
        self.assertEqual([r["end"] for r in acme_roles()], ["2022-06"])

    def test_different_real_end_dates_stay_separate_roles(self):
        self.write("a.txt", as_txt().replace(PRESENT, ENDED))
        self.write("b.txt", as_txt().replace(PRESENT, "03/2021 - 09/2022"))
        self.rebuild()
        self.assertEqual(sorted(r["end"] for r in acme_roles()), ["2022-06", "2022-09"])

    def test_fingerprint_sorts_roles_with_and_without_an_end_date(self):
        role = {"start": "2021-03", "titles": ["Engineer"]}
        company = {"name": "Acme", "bullets": [], "roles": [{**role, "end": None}, {**role, "end": "2022-06"}]}
        facts = SimpleNamespace(skills={}, companies={"acme": company}, education=[], certifications=[])
        self.assertEqual(len(mf.resume_fingerprint(facts)), 64)  # type: ignore[arg-type]


class HyphenatedEmployerTests(RebuildCase):
    def discover(self, header: str) -> dict[str, str]:
        text = f"WORK EXPERIENCE\n{header}\n01/2010 - 12/2014\n• Did things.\n"
        return pr.discover_companies(text)

    def test_hyphen_inside_a_name_is_kept(self):
        self.assertEqual(self.discover("Acme-Labs"), {"acme-labs": "Acme-Labs"})
        self.assertEqual(self.discover("X-Acme"), {"x-acme": "X-Acme"})

    def test_a_spaced_hyphen_or_a_dash_still_splits_name_and_title(self):
        self.assertEqual(self.discover("Acme-Works – Principal Engineer"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works - Principal Engineer"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works — Principal Engineer"), {"acme-works": "Acme-Works"})

    def test_a_resume_with_no_known_employer_is_reported(self):
        parsed = pr.parse_resume(as_txt(), company_res={})
        self.assertTrue(any("no known employer" in p for p in parsed["problems"]))


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


class DeletedResumeTests(RebuildCase):
    def stored(self) -> dict:
        profile = rd.load_profile()
        return {"headlines": profile.get("headlines", []), "education": profile["education"],
                "certifications": profile["certifications"], "projects": profile["projects"]}

    def titles(self) -> list[str]:
        roles = rd.load_companies()["globex"]["roles"]
        return sorted(t for r in roles for t in r["titles"])

    def test_everything_a_deleted_resume_stated_goes_with_it(self):
        self.write("one.txt", as_txt())
        self.write("two.txt", second_resume())
        self.rebuild()
        stored = self.stored()
        self.assertEqual(stored["headlines"], ["Web performance specialist"])
        self.assertTrue(stored["education"] and stored["certifications"] and stored["projects"])
        self.assertEqual(self.titles(), ["Senior Engineer", "Staff Engineer"])
        (self.resumes / "two.txt").unlink()
        self.rebuild()
        self.assertEqual(self.stored(), {"headlines": [], "education": [], "certifications": [], "projects": []})
        self.assertEqual(self.titles(), ["Senior Engineer"])

    def test_an_item_another_resume_states_stays(self):
        self.write("one.txt", second_resume())
        self.write("two.txt", second_resume())
        self.rebuild()
        (self.resumes / "two.txt").unlink()
        self.rebuild()
        self.assertEqual(self.stored()["headlines"], ["Web performance specialist"])
        self.assertEqual(len(self.stored()["education"]), 1)

    def test_a_changed_resume_loses_what_it_no_longer_says(self):
        path = self.write("one.txt", second_resume())
        self.rebuild()
        path.write_text(as_txt() + EXTRAS.replace("BSc Physics", "MSc Physics"), encoding="utf-8")
        self.rebuild()
        self.assertEqual(self.stored()["headlines"], [])
        self.assertEqual([e for e in self.stored()["education"]], ["MSc Physics, Example University"])

    def test_data_stored_before_source_tracking_is_rebuilt_once(self):
        self.write("one.txt", second_resume())
        self.rebuild()
        profile = rd.load_profile()
        profile.pop("item_sources")
        tables.save_profile(profile)
        self.assertIn("Upgrading the stored data", self.rebuild())
        self.assertNotIn("Upgrading", self.rebuild())


class ContactLineTests(RebuildCase):
    PHONE = "555.010.0100"
    MAIL = "jane@example.com"

    def test_lines_that_are_only_contact_details(self):
        for line in (self.MAIL, self.PHONE, f"{self.PHONE} | {self.MAIL}", f"{self.PHONE} · {self.MAIL} • "
                     "linkedin.com/in/jane"):
            self.assertTrue(extract.is_contact_line(line), line)
        for line in ("Jane | Seattle", f"Reach me at {self.MAIL}", "Cut spend by 30% | saved 12 accounts", "•", ""):
            self.assertFalse(extract.is_contact_line(line), line)

    def test_stray_contact_line_is_not_the_headline(self):
        text = f"Jane Example\nSenior Software Engineer\n{self.PHONE} | {self.MAIL}\nWeb performance specialist\n"
        parsed = pr.parse_resume(text + as_txt().split("\n", 2)[2])
        self.assertEqual(parsed["headline"], "Web performance specialist")
        self.assertNotIn(self.MAIL, parsed["summary"])

    def test_contact_line_in_work_section_is_not_glued_to_a_bullet(self):
        text = as_txt().replace("• Built a search service on PostgreSQL.\n",
                                f"• Built a search service on PostgreSQL.\n{self.PHONE} | {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(text, text)["work"] for b in e["bullets"]]
        self.assertIn("Built a search service on PostgreSQL.", bullets)
        self.assertFalse(any(self.MAIL in b or self.PHONE in b for b in bullets))

    def test_layout_text_of_a_pdf_is_cleaned_too(self):
        layout = as_txt().replace("• Built a search service on PostgreSQL.\n",
                                  f"• Built a search service on PostgreSQL.\n   {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(as_txt(), layout)["work"] for b in e["bullets"]]
        self.assertIn("Built a search service on PostgreSQL.", bullets)
        self.assertFalse(any(self.MAIL in b for b in bullets))
