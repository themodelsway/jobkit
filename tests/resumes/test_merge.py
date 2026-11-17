"""Tests for merging parsed resumes into the stored data (plugins/jobkit/src/jk/resumes/process_resumes.py): bullets,
figures, roles with two end dates, skill tags, and bullet ids that stay put through rebuilds."""
import contextlib
import copy
import io
import unittest
from types import SimpleNamespace

from jk.resumes import match_facts as mf
from jk.resumes import parse_resume as pr
from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from jk.resumes import tables
from tests.resumes.support import DATA_REGISTRY, RebuildCase, as_txt, line, parse_sample

BULLET = "Reduced time to hire by 30 percent across twelve teams using structured interviews and scorecards."
VARIANT = "Reduced the time to hire by 30 percent across twelve teams using structured interviews and scorecards."
CHANGED = "Reduced time to hire by 45 percent across twelve teams using structured interviews and scorecards."


def resume(*bullets: str) -> str:
    """A minimal synthetic resume with one employer."""
    lines = ["WORK EXPERIENCE", "Acme Corp      03/2021 - Present", "Lead Designer"]
    return "\n".join(lines + [f"• {b}" for b in bullets]) + "\n"


class IdCarryTests(RebuildCase):
    def full_rebuild(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            proc.build(proc.list_resumes([self.resumes]), self.resumes, force=True)

    def stored(self) -> list[dict]:
        return [b for c in rd.load_companies().values() for b in c["bullets"]]

    def curate_first(self) -> str:
        bid = self.stored()[0]["id"]
        tables.save_curation("themes", {"themes": {bid: ["cost"]}, "ignore": [], "summary_angles": {}})
        return bid

    def test_resume_that_sorts_earlier_does_not_change_the_id(self):
        self.write("b.txt", resume(BULLET))
        self.rebuild()
        bid = self.curate_first()
        self.write("a.txt", resume(VARIANT))
        self.full_rebuild()
        (bullet,) = self.stored()
        self.assertEqual((bullet["id"], bullet["themes"]), (bid, ["cost"]))

    def test_deleting_the_first_file_does_not_change_the_id(self):
        self.write("a.txt", resume(BULLET))
        self.write("b.txt", resume(VARIANT))
        self.rebuild()
        bid = self.curate_first()
        (self.resumes / "a.txt").unlink()
        self.full_rebuild()
        (bullet,) = self.stored()
        self.assertEqual((bullet["id"], bullet["themes"]), (bid, ["cost"]))

    def test_a_changed_claim_is_a_new_bullet(self):
        path = self.write("a.txt", resume(BULLET))
        self.rebuild()
        bid = self.curate_first()
        path.write_text(resume(CHANGED), encoding="utf-8")
        self.full_rebuild()
        (bullet,) = self.stored()
        self.assertNotEqual(bullet["id"], bid)
        self.assertIn(f"theme {bid}", rd.orphan_curation(rd.load_companies(), rd.load_profile(), rd.load_themes_file()))


class CarryIdsUnitTests(unittest.TestCase):
    @staticmethod
    def company(*bullets: tuple[str, str]) -> dict:
        return {"acme-corp": {"id": "acme-corp", "bullets": [
            {"id": i, "text": t, "variants": [], "wordings": {"f": [t]}} for i, t in bullets]}}

    def test_curated_stored_bullet_wins_over_lower_id(self):
        stored = self.company(("s1", BULLET), ("s2", VARIANT))
        data = {"companies": self.company(("n1", "Reduced time to hire by 30 percent across twelve teams "
                                                  "using structured interviews and scorecards!")),
                "skills": {}, "profile": {}}
        data["companies"]["acme-corp"]["bullets"][0]["wordings"] = {"g": ["unrelated 30"]}
        proc.carry_ids(data, stored, {"s2"})
        self.assertEqual(data["companies"]["acme-corp"]["bullets"][0]["id"], "s2")

    def test_lowest_id_wins_without_curation_and_ids_stay_unique(self):
        stored = self.company(("s2", BULLET), ("s1", VARIANT))
        new = self.company(("n1", BULLET + ""), ("n2", VARIANT))
        data = {"companies": new, "skills": {}, "profile": {}}
        proc.carry_ids(data, stored, set())
        ids = [b["id"] for b in data["companies"]["acme-corp"]["bullets"]]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(sorted(ids), ["s1", "s2"])


def empty_data():
    return {"companies": {}, "skills": {"groups": {}},
            "profile": {"summaries": [], "profile_points": [], "education": [], "certifications": [], "projects": []}}


class MergeTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(pr.COMPANIES)
        pr.set_companies(DATA_REGISTRY)
        self.addCleanup(lambda: pr.set_companies(self._saved))

    def merged(self, *sources):
        data = empty_data()
        for src, name, layout in sources:
            proc.merge_resume(data, src, parse_sample(name, layout))
        return data

    def test_merge_is_idempotent(self):
        once = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        twice = copy.deepcopy(once)
        proc.merge_resume(twice, "a.pdf", parse_sample("layout_a", "layout_a.layout"))
        self.assertEqual(once, twice)

    def test_second_source_accumulates_sources_and_roles(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"), ("b.pdf", "layout_b", None))
        acme = data["companies"]["acme-corp"]
        self.assertEqual(len(acme["roles"]), 1)           # same (start, end) -> one role
        self.assertEqual(sorted(acme["roles"][0]["sources"]), ["a.pdf", "b.pdf"])
        self.assertEqual(sorted(acme["roles"][0]["titles"]), ["Lead Designer", "People Director"])
        self.assertEqual(len(data["companies"]["acme-3"]["roles"]), 1)
        self.assertEqual(data["companies"]["acme-3"]["roles"][0]["clients"], ["Acme 6"])

    def test_near_duplicate_becomes_variant(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        first = data["companies"]["acme-corp"]["bullets"][0]
        r = parse_sample("layout_a", "layout_a.layout")
        r["work"][0]["bullets"] = [first["text"].rstrip(".") + " today."]
        proc.merge_resume(data, "c.pdf", r)
        self.assertEqual(len(data["companies"]["acme-corp"]["bullets"]), 2)
        self.assertEqual(first["variants"], [first["text"].rstrip(".") + " today."])
        self.assertIn("c.pdf", first["sources"])

    def test_skills_and_summary_merge(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        names = {g: [s["name"] for s in v] for g, v in data["skills"]["groups"].items()}
        self.assertIn("UX", names["Design"])
        ux = next(s for s in data["skills"]["groups"]["Design"] if s["name"] == "UX")
        self.assertEqual(ux["aliases"], ["User Experience"])
        self.assertEqual(len(data["profile"]["summaries"]), 1)
        self.assertEqual(data["profile"]["headlines"], ["Senior Product Designer"])


class FigureMergeTests(unittest.TestCase):
    def merged(self, first: str, second: str) -> dict:
        company = {"id": "acme", "bullets": [], "roles": []}
        proc.merge_bullet(company, first, "2020-01", "a.txt")
        proc.merge_bullet(company, second, "2020-01", "b.txt")
        return company

    def test_different_figures_are_separate_bullets(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 90% through route consolidation.")
        self.assertEqual(len(company["bullets"]), 2)
        self.assertEqual([b["sources"] for b in company["bullets"]], [["a.txt"], ["b.txt"]])

    def test_same_figures_still_merge(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 40% through route consolidation work.")
        self.assertEqual(len(company["bullets"]), 1)


class RetagTests(unittest.TestCase):
    """L2: a rebuild tags older bullets with short names and loses no existing tag."""

    def test_retag_adds_short_names_and_keeps_the_rest(self):
        bullets = [line("Built Python models in R for forecasting", skills=["Python"]),
                   line("Wrote Go services with SQL storage", skills=["SQL"], skills_manual=["Kafka"]),
                   line("Planned the R&D budget", skills=[])]
        data = {"companies": {"a": {"bullets": bullets}},
                "skills": {"groups": {"Languages": [{"name": n, "aliases": []} for n in ("Python", "R", "Go", "SQL")]}}}
        before = {b["id"]: set(b["skills"]) for b in bullets}
        proc.retag(data)       # type: ignore[arg-type]
        after = {b["id"]: set(b["skills"]) for b in bullets}
        for key, old in before.items():
            self.assertLessEqual(old, after[key])
        self.assertEqual(after[bullets[0]["id"]], {"Python", "R"})
        self.assertEqual(after[bullets[1]["id"]], {"Go", "SQL", "Kafka"})
        self.assertEqual(after[bullets[2]["id"]], set())


def acme_roles() -> list[dict]:
    return rd.load_companies()["acme-corp"]["roles"]


ENDED = "03/2021 - 06/2022"


PRESENT = "03/2021 - Present"


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
