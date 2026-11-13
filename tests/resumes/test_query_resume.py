"""Tests for query-resume."""
import contextlib
import io
import unittest
from typing import Any
from unittest import mock

from jk.resumes import parse_resume as pr, query_resume as qr, tables
from tests.resumes.match_fixtures import jd_from_bullets, line, role
from tests.resumes.test_resume_pipeline import PipelineCase
from tests.support import HomeCase


class ShortSkillNameTests(unittest.TestCase):
    """L2: short names are recognised as whole words, and only where they are the skill."""

    TERMS = pr.skill_terms({"Languages": [{"name": "R", "aliases": []}, {"name": "Go", "aliases": []},
                                          {"name": "HR", "aliases": []}, {"name": "SQL", "aliases": []},
                                          {"name": "AWS", "aliases": []}, {"name": "API", "aliases": []}]})

    def test_stored_short_names_are_kept(self):
        self.assertTrue({"R", "Go", "HR"} <= set(self.TERMS))

    def test_r_go_and_hr_are_found(self):
        self.assertEqual(pr.tag_skills("Experience with R and Go, plus HR systems.", self.TERMS), ["Go", "HR", "R"])

    def test_lower_case_long_names_are_found(self):
        self.assertEqual(pr.tag_skills("aws, sql and api work", self.TERMS), ["API", "AWS", "SQL"])

    def test_letters_inside_other_words_are_not_found(self):
        for text in ("Go-to-market strategy for retail", "R&D budget", "Brought a trust fund to Gotham", "go to the shop",
                     "r is a letter"):
            with self.subTest(text):
                self.assertEqual(pr.tag_skills(text, self.TERMS), [])

    def test_jd_skills_counts_short_names(self):
        counts = qr.jd_skills("We use R. Candidates know R and aws.", self.TERMS)
        self.assertEqual((counts["R"], counts["AWS"]), (2, 1))


class AmbiguousNameTests(unittest.TestCase):
    """Names that are also ordinary words (Go, Make, Rust ...) count only when they read as the skill."""

    TERMS = pr.skill_terms({"Tools": [{"name": n, "aliases": []} for n in ("Go", "Make", "Rust", "Ruby", "Python")]})

    def found(self, text: str) -> list[str]:
        return pr.tag_skills(text, self.TERMS)

    def test_skill_uses_are_found(self):
        self.assertEqual(self.found("Experience with Go and Python."), ["Go", "Python"])
        self.assertEqual(self.found("We write Rust and Ruby services."), ["Ruby", "Rust"])
        self.assertEqual(self.found("Tools: Make, Docker"), ["Make"])
        self.assertEqual(self.found("Skills\n- Go\n- Python"), ["Go", "Python"])
        self.assertEqual(self.found("Wrote Go services for billing"), ["Go"])

    def test_ordinary_words_are_not_skills(self):
        for text in ("Go to market strategy for retail.", "Make sure the plan is sound.", "Rust never sleeps.",
                     "The rust on the car", "make it work", "Make-or-buy analysis", "Go-to-market plan"):
            with self.subTest(text):
                self.assertEqual(self.found(text), [])

    def test_sentence_start_use_is_listed_as_possible_with_its_sentence(self):
        found = pr.possible_matches("Go to market strategy for retail. We use Go and Python.", self.TERMS)
        self.assertEqual(found, [])        # Go is already found properly in the second sentence
        found = pr.possible_matches("Go to market strategy for retail. Make sure it ships.", self.TERMS)
        self.assertEqual([(n, q.split()[0]) for n, q in found], [("Go", "Go"), ("Make", "Make")])
        self.assertIn("Go to market strategy", found[0][1])

    def test_lower_case_words_are_never_possible_matches(self):
        self.assertEqual(pr.possible_matches("go to the shop and make tea", self.TERMS), [])

    def test_jd_analysis_lists_possible_matches(self):
        companies = {"a": {"id": "a", "name": "A", "aliases": [], "roles": [role("2020-01", None, "T")], "bullets": []}}
        with mock.patch.object(qr, "load_or_fail",
                               return_value=(companies, {"groups": {"Tools": [{"name": "Go", "aliases": []}]}})), \
             mock.patch.object(qr.rd, "load_profile", return_value=qr.rd.empty_profile()), \
             mock.patch.object(qr, "recency_scores", return_value={}):
            result = qr.analyze("Go to market strategy for retail.")
        self.assertEqual(dict(result.need), {})
        self.assertEqual([n for n, _ in result.possible], ["Go"])


class RankingProvenanceTests(HomeCase):
    """L3: role dates drive recency; file dates and repeats are provenance only."""

    def companies(self) -> dict[str, Any]:
        return {"acme": {"id": "acme", "name": "Acme", "aliases": [], "bullets": [
            line("Old work in Python", "2015-01", id="old", skills=["Python"]),
            line("New work in Python", "2023-01", id="new", skills=["Python"])],
            "roles": [role("2015-01", "2018-01", "Analyst"), role("2023-01", None, "Manager")]}}

    def test_recency_follows_the_role_date(self):
        scores = qr.recency_scores(self.companies())
        self.assertEqual((scores["new"], scores["old"]), (1.0, 0.0))

    def test_resaving_a_file_changes_nothing(self):
        companies = self.companies()
        before = qr.recency_scores(companies)
        tables.replace_ledger({"a.docx": {"mtime": 1.0, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}})
        self.assertEqual(qr.recency_scores(companies), before)
        tables.replace_ledger({"a.docx": {"mtime": 9e9, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}})
        self.assertEqual(qr.recency_scores(companies), before)

    def ctx(self) -> qr.JdContext:
        return qr.JdContext(qr.Counter({"Python": 1}), {"python"}, set(), {"one": 0.5, "many": 0.5}, 2.0)

    def test_repeats_add_only_a_small_capped_amount(self):
        once = qr.score_bullet(line("Used Python", id="one", skills=["Python"], sources=["a"]), self.ctx())
        many = qr.score_bullet(line("Used Python", id="many", skills=["Python"], sources=list("abcdefghij")), self.ctx())
        assert once is not None and many is not None
        self.assertGreater(many.score, once.score)
        self.assertLessEqual(many.score - once.score, 0.5)

    def test_more_than_the_cap_of_repeats_adds_nothing(self):
        six = qr.score_bullet(line("Used Python", id="one", skills=["Python"], sources=list("abcdef")), self.ctx())
        fifty = qr.score_bullet(line("Used Python", id="many", skills=["Python"], sources=[str(i) for i in range(50)]),
                                self.ctx())
        assert six is not None and fifty is not None
        self.assertEqual(six.score, fifty.score)

    def test_provenance_label_says_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            qr.show(line("Used Python", id="one", sources=["a", "b"]))
        self.assertIn("in 2 resume file(s)", out.getvalue())


class QueryOptionTests(PipelineCase):
    def jd_file(self):
        jd = self.tmp / "jd-opts.txt"
        jd.write_text(jd_from_bullets(self.data), encoding="utf-8")
        return str(jd)

    def test_for_jd_top_limits_bullets_per_company(self):
        one = self.cli(qr.main, "for-jd", self.jd_file(), "--top", "1")[1]
        three = self.cli(qr.main, "for-jd", self.jd_file(), "--top", "3")[1]
        self.assertLessEqual(len(one), len(three))
        self.assertNotEqual(one, three)

    def test_for_jd_summaries_recency_theme_and_review_flags(self):
        base = self.cli(qr.main, "for-jd", self.jd_file(), "--summaries", "1")
        self.assertEqual(base[0], 0, base[2])
        self.assertLessEqual(base[1].count("sum-"), self.cli(qr.main, "for-jd", self.jd_file())[1].count("sum-"))
        for extra in (("--recency", "0"), ("--theme", "cost-optimization"), ("--include-review",)):
            with self.subTest(extra=extra):
                code, out, err = self.cli(qr.main, "for-jd", self.jd_file(), *extra)
                self.assertEqual(code, 0, err)
                self.assertIn("== Suggested opening summaries", out)

    def test_search_filters_combine(self):
        everything = self.cli(qr.main, "search", "--limit", "500")[1]
        total = int(everything.strip().splitlines()[-1].split()[0])
        self.assertGreater(total, 1)
        limited = self.cli(qr.main, "search", "--limit", "1")[1]
        self.assertIn(f"{total} bullet(s) matched (showing 1)", limited)
        company = next(c for c in self.data["companies"].values() if c["bullets"])
        by_company = self.cli(qr.main, "search", "--company", company["id"], "--limit", "500")[1]
        self.assertIn(f"{len(company['bullets'])} bullet(s) matched", by_company)
        bullet = next(b for b in company["bullets"] if b["skills"])
        by_skill = self.cli(qr.main, "search", "--skill", bullet["skills"][0], "--limit", "500")[1]
        self.assertIn(bullet["text"][:40], by_skill)
        theme = next((t for c in self.data["companies"].values() for b in c["bullets"] for t in b["themes"]), None)
        if theme:
            self.assertNotIn("0 bullet(s) matched", self.cli(qr.main, "search", "--theme", theme)[1])
        self.assertIn("0 bullet(s) matched", self.cli(qr.main, "search", "--theme", "no-such-theme")[1])
        self.assertIn("0 bullet(s) matched", self.cli(qr.main, "search", "--text", "zzz-no-such-text")[1])

    def test_review_names_each_company_once(self):
        companies, skills = qr.load_or_fail()
        first, second = [c for c in qr.newest_first(companies) if len(c["bullets"]) > 1][:2]
        for bullet in first["bullets"][:2]:
            bullet["needs_review"] = True
        with mock.patch.object(qr, "load_or_fail", return_value=(companies, skills)):
            out = self.cli(qr.main, "review")[1]
        self.assertEqual(out.count(f"== {first['name']}\n"), 1)
        self.assertEqual(out.count("[NEEDS REVIEW]"), 2)
        self.assertNotIn(f"== {second['name']}\n", out)

    def test_search_names_each_company_once_and_says_what_is_not_shown(self):
        with_bullets = [c for c in qr.newest_first(self.data["companies"])
                        if any(not b.get("ignored") for b in c["bullets"])]
        self.assertGreater(len(with_bullets), 1)
        everything = self.cli(qr.main, "search", "--limit", "500")[1]
        for company in with_bullets:
            self.assertEqual(everything.count(f"== {company['name']}\n"), 1)
        self.assertNotIn("Not shown", everything)
        limited = self.cli(qr.main, "search", "--limit", "1")[1]
        self.assertEqual(limited.count("\n== ") + limited.startswith("== "), 1)
        footer = limited.strip().splitlines()[-1]
        live = {c["name"]: sum(1 for b in c["bullets"] if not b.get("ignored")) for c in with_bullets}
        first = with_bullets[0]["name"]
        hidden = [f"{name} {n - (name == first)}" for name, n in live.items() if n - (name == first)]
        self.assertTrue(footer.endswith(". Not shown: " + "; ".join(hidden)), footer)
