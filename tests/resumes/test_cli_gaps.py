"""Command-line coverage for resume tool options no other test calls, plus process-resumes --survey/--force and
profile companies. Temp folders only."""
import contextlib
import io
import unittest
from unittest import mock

from jobkit.resumes import build_resume as br
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import process_resumes as proc
from jobkit.resumes import query_resume as qr
from jobkit.resumes import tables
from jobkit.user import profile as up
from tests.resumes.test_resume_pipeline import FIX, REGISTRY, PipelineCase
from tests.support import HomeCase


def jd_from_bullets(data: dict) -> str:
    """A job description made of the bullets' own words, so every bullet scores as relevant."""
    return " ".join(b["text"] for c in data["companies"].values() for b in c["bullets"])


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


class BuildOptionTests(PipelineCase):
    def build(self, *extra):
        jd, out = self.tmp / "jd3.txt", self.tmp / "out" / f"r{len(extra)}.md"
        jd.write_text(jd_from_bullets(self.data), encoding="utf-8")
        with mock.patch.object(br, "header_file", return_value=self.tmp / "header.md"):
            code, _, err = self.cli(br.main, str(jd), "--output", str(out), *extra)
        self.assertEqual(code, 0, err)
        return out.read_text(encoding="utf-8")

    def test_top_limits_bullets_and_title_overrides(self):
        many, few = self.build("--top", "4"), self.build("--top", "1")
        self.assertLess(len(few), len(many))
        text = self.build("--title", "acme-corp=Lead Engineer")
        self.assertIn("Lead Engineer", text)

    def test_recency_and_include_review_are_accepted(self):
        self.assertTrue(self.build("--recency", "0", "--include-review"))


class ProcessResumesTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        self.root = self.tmp / "resumes"
        self.root.mkdir()
        (self.root / "a.txt").write_text((FIX / "layout_b.txt").read_text(encoding="utf-8"))
        saved = dict(pr.COMPANIES)
        self.addCleanup(pr.set_companies, saved)
        pr.set_companies(REGISTRY)
        patcher = mock.patch.object(proc, "TEXT_DIR", self.tmp / "text")
        patcher.start()
        self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(proc, "load_config", return_value=proc.Config(self.root, [self.root])),
                        mock.patch.object(proc, "scan_companies")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = proc.main(list(argv))
        return code, out.getvalue()

    def test_survey_writes_nothing(self):
        code, out = self.run_cli("--survey")
        self.assertEqual(code, 0)
        self.assertIn("a.txt", out)
        self.assertFalse(tables.has_resume_data())
        self.assertEqual(tables.load_companies(), {})

    def test_build_is_incremental_and_force_rebuilds(self):
        self.assertIn("1 new/changed", self.run_cli()[1])
        self.assertIn("0 new/changed, 1 unchanged", self.run_cli()[1])
        self.assertIn("1 new/changed, 0 unchanged", self.run_cli("--force")[1])
        self.assertEqual(list(tables.load_ledger()), ["a.txt"])

    def test_no_resumes_is_a_clear_error(self):
        (self.root / "a.txt").unlink()
        code, _ = self.run_cli()
        self.assertEqual(code, 1)


class ProfileCompaniesTests(HomeCase):
    def test_lists_companies_or_says_to_scan(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(up.main(["companies"]), 0)
            self.assertIn("No scan yet", out.getvalue())
            up.add_companies({"acme": "Acme Corp"})
            out.truncate(0)
            self.assertEqual(up.main(["companies"]), 0)
        self.assertIn("Acme Corp", out.getvalue())


if __name__ == "__main__":
    unittest.main()
