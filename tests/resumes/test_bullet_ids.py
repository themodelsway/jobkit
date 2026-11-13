"""Bullet ids stay put through full rebuilds while the bullet continues (DM-6)."""
import contextlib
import io

from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from jk.resumes import tables
from tests.resumes.test_integrity import RebuildCase

BULLET = "Reduced page load time by 30 percent across twelve services using caching and query tuning."
VARIANT = "Reduced page loading time by 30 percent across twelve services using caching and query tuning."
CHANGED = "Reduced page load time by 45 percent across twelve services using caching and query tuning."


def resume(*bullets: str) -> str:
    """A minimal synthetic resume with one employer."""
    lines = ["WORK EXPERIENCE", "Acme Corp      03/2021 - Present", "Lead Engineer"]
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


class CarryIdsUnitTests(RebuildCase):
    @staticmethod
    def company(*bullets: tuple[str, str]) -> dict:
        return {"acme-corp": {"id": "acme-corp", "bullets": [
            {"id": i, "text": t, "variants": [], "wordings": {"f": [t]}} for i, t in bullets]}}

    def test_curated_stored_bullet_wins_over_lower_id(self):
        stored = self.company(("s1", BULLET), ("s2", VARIANT))
        data = {"companies": self.company(("n1", "Reduced page load time by 30 percent across twelve services "
                                                  "using caching and query tuning!")),
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
