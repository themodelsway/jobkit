"""Tests for the layout handling of resume parsing (columns, dates, headings, work_layout): date styles, section headings,
header shapes, page columns, Word text boxes, tables and style bullets. All data is fictional."""
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from xml.sax.saxutils import escape

from jk.resumes import columns, dates, extract, headings
from jk.resumes import parse_resume as pr
from jk.resumes.build_resume import fmt_date
from jk.resumes.query_resume import month_number
from jk.resumes.work_layout import split_header
from tests.resumes.support import para, table, write_docx

BULLETS = ["Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.",
           "Designed an event-driven order pipeline handling 2 million messages a day."]


def parse(text: str) -> pr.Resume:
    """Discover the employers in the text, register them, and parse it, as process-resumes does."""
    saved = (dict(pr.COMPANIES), dict(pr.COMPANY_RES))
    found = pr.discover_companies(text)
    pr.set_companies({k: (v, pr.re.escape(v) + rf"(?:{pr.SEP}(?P<t>.+))?") for k, v in found.items()})
    try:
        result = pr.parse_resume(text, text)
    finally:
        pr.set_companies(saved[0])
    assert result["is_resume"] is True, result
    return result


def jobs(result: pr.Resume) -> list[tuple[str, str, str | None, str | None, int]]:
    """(employer id, title, start, end, bullet count) of every entry."""
    return [(e["company_id"], e["title"], e["start"], e["end"], len(e["bullets"])) for e in result["work"]]


class DateTests(unittest.TestCase):
    def test_every_common_style_is_found_and_read(self):
        cases = {"09/2021 - Present": ("2021-09", None), "Sep 2021 – Present": ("2021-09", None),
                 "September 2021 to Aug 2023": ("2021-09", "2023-08"), "Sept. 2021 — Now": ("2021-09", None),
                 "2012 – 2017": ("2012", "2017"), "2021-09 - 2022-03": ("2021-09", "2022-03"),
                 "03/21 - 05/22": ("2021-03", "2022-05"), "6/2019 – current": ("2019-06", None)}
        for text, (start, end) in cases.items():
            found = dates.find_date_range(text)
            self.assertIsNotNone(found, text)
            assert found is not None
            self.assertEqual((dates.parse_date(found.start), dates.parse_date(found.end)), (start, end), text)

    def test_text_around_the_range_is_returned(self):
        found = dates.find_date_range("Acme Corp | Engineer | Sep 2021 – Present")
        assert found is not None
        self.assertEqual((found.before, found.after), ("Acme Corp | Engineer", ""))
        found = dates.find_date_range("Acme Corp (2019–2022)")
        assert found is not None
        self.assertEqual(found.before, "Acme Corp")

    def test_numbers_that_are_not_dates_are_ignored(self):
        for text in ("1000 - 2000 users", "Led 12 teams", "Cut cost 30% - 40%", "see 10/12/2019 - 5"):
            self.assertIsNone(dates.find_date_range(text), text)

    def test_date_line_is_only_a_range(self):
        self.assertTrue(dates.is_date_line("2012 – 2017"))
        self.assertFalse(dates.is_date_line("Acme  2012 – 2017"))

    def test_year_only_dates_work_where_months_are_used(self):
        self.assertEqual(fmt_date("2012"), "2012")
        self.assertEqual(fmt_date("2012-03"), "03/2012")
        self.assertEqual(month_number("2012"), 2012 * 12 + 6)
        self.assertEqual(month_number("2012-03"), 2012 * 12 + 3)


class HeadingTests(unittest.TestCase):
    def test_synonyms_and_spellings(self):
        cases = {"PROFESSIONAL EXPERIENCE": "work", "Experience": "work", "Employment History": "work",
                 "Skills:": "skills", "Core Competencies": "skills", "Career Highlights": "profile",
                 "Key Achievements": "profile", "Awards": "other", "Volunteer Experience": "other",
                 "Education & Certifications": "education_certs", "W O R K  H I S T O R Y": "work"}
        for text, key in cases.items():
            self.assertEqual(headings.heading_key(text), key, text)

    def test_ordinary_lines_are_not_headings(self):
        for text in ("Product strategy and planning", "Led the experience team.", "• Skills", "Python, Java", ""):
            self.assertIsNone(headings.heading_key(text), text)

    def test_inline_heading_keeps_languages_as_a_label(self):
        self.assertEqual(headings.inline_heading("Skills: Python, Java"), ("skills", "Python, Java"))
        self.assertIsNone(headings.inline_heading("Languages: Python, Java"))

    def test_an_unknown_section_ends_the_work_history_and_is_reported(self):
        text = ("Work Experience\nAcme 4   09/2021 - Present\nLead Designer\n"
                f"• {BULLETS[0]}\nPUBLICATIONS AND TALKS\n• A talk about caches.\n")
        sections = pr.split_sections(text.splitlines())
        self.assertEqual(sections["_unknown"], ["PUBLICATIONS AND TALKS"])
        result = parse(text)
        self.assertEqual(jobs(result), [("acme-4", "Lead Designer", "2021-09", None, 1)])
        self.assertIn('unknown heading "PUBLICATIONS AND TALKS" ended the work history', result["problems"])

    def test_an_all_caps_employer_is_not_an_unknown_heading(self):
        text = "Work Experience\nAcme Research\n01/2015 - 02/2021\n• Built things.\nACME INDUSTRIES\nSenior Strategist\n03/2021 - Present\n• More.\n"
        self.assertEqual([e[0] for e in jobs(parse(text))], ["acme-research", "acme-industries"])


class WorkShapeTests(unittest.TestCase):
    def work(self, *lines: str) -> pr.Resume:
        return parse("\n".join(["Work Experience", *lines]) + "\n")

    def test_pipe_header_with_a_month_name_date(self):
        result = self.work("Acme 4 | Lead Designer | Sep 2021 – Present", f"• {BULLETS[0]}")
        self.assertEqual(jobs(result), [("acme-4", "Lead Designer", "2021-09", None, 1)])

    def test_title_first_does_not_make_the_title_an_employer(self):
        result = self.work("Lead Designer   09/2021 - Present", "Acme 4", "Seattle, WA", f"• {BULLETS[0]}",
                           "Product Manager   06/2012 - 02/2017", "Acme 5", f"• {BULLETS[1]}")
        self.assertEqual(jobs(result), [("acme-4", "Lead Designer", "2021-09", None, 1),
                                        ("acme-5", "Product Manager", "2012-06", "2017-02", 1)])

    def test_title_comma_company_and_title_at_company(self):
        result = self.work("Lead Designer, Acme 4 (2019–2022)", f"• {BULLETS[0]}",
                           "Product Manager at Acme 5   2012 - 2017", f"• {BULLETS[1]}")
        self.assertEqual(jobs(result), [("acme-4", "Lead Designer", "2019", "2022", 1),
                                        ("acme-5", "Product Manager", "2012", "2017", 1)])

    def test_several_roles_at_one_employer(self):
        result = self.work("Acme 4   06/2012 - Present", "Lead Designer   09/2021 - Present",
                           f"• {BULLETS[0]}", "Senior Product Designer   06/2012 - 08/2021", f"• {BULLETS[1]}")
        self.assertEqual(jobs(result), [("acme-4", "Lead Designer", "2021-09", None, 1),
                                        ("acme-4", "Senior Product Designer", "2012-06", "2021-08", 1)])

    def test_location_lines_are_dropped_but_bullets_keep_their_text(self):
        result = self.work("Acme 4   09/2021 - Present", "Lead Designer", "Remote",
                           f"• {BULLETS[0]}", "• Opened an office in Austin, TX and hired 6 people.")
        self.assertEqual(result["problems"], [])
        self.assertEqual(len(result["work"][0]["bullets"]), 2)

    def test_a_bullet_that_ends_in_dates_is_not_split(self):
        result = self.work("Acme 4   09/2021 - Present", "Lead Designer",
                           "• Ran the platform team during Jan 2022 - Mar 2023", "  and kept the budget.")
        self.assertEqual(len(result["work"][0]["bullets"]), 1)

    def test_bullets_without_marks_are_found_by_their_line_breaks(self):
        result = self.work("Acme 4   09/2021 - Present", "Lead Designer", BULLETS[0], BULLETS[1])
        self.assertEqual(result["work"][0]["bullets"], BULLETS)
        self.assertTrue(any("inferred from line breaks" in p for p in result["problems"]))

    def test_marked_bullets_still_wrap(self):
        result = self.work("Acme 4   09/2021 - Present", "Lead Designer",
                           "• Led the migration of forty services", "  to Kubernetes in a year.")
        self.assertEqual(result["work"][0]["bullets"], ["Led the migration of forty services to Kubernetes in a year."])

    def test_highlights_after_the_work_history_are_not_bullets_of_the_last_job(self):
        text = ("Work Experience\nAcme 4   09/2021 - Present\nLead Designer\n"
                f"• {BULLETS[0]}\nCareer Highlights\n• Saved $4M a year.\n• Spoke at two conferences.\nAwards\n• Award 2020.\n")
        result = parse(text)
        self.assertEqual(len(result["work"][0]["bullets"]), 1)
        self.assertEqual(result["profile_points"], ["Saved $4M a year.", "Spoke at two conferences."])


class SectionContentTests(unittest.TestCase):
    def test_skills_without_bullets_in_any_separator_style(self):
        skills, problems = pr.parse_skills({"skills": ["Languages: Python, Java", "Cloud: AWS | GCP", "Terraform",
                                                       "Kubernetes   Docker"]})
        names = {g: [i["name"] for i in items] for g, items in skills.items()}
        self.assertEqual(names["Languages"], ["Python", "Java"])
        self.assertEqual(names["Cloud"], ["AWS", "GCP"])
        self.assertEqual(names["Unsorted"], ["Terraform", "Kubernetes", "Docker"])
        self.assertEqual(problems, [])

    def test_a_sentence_is_not_a_skill(self):
        skills, problems = pr.parse_skills({"skills": ["• Python", "• " + "Led a team of engineers through a long migration " * 2]})
        self.assertEqual([i["name"] for i in skills["Unsorted"]], ["Python"])
        self.assertTrue(any("looks like a sentence" in p for p in problems))

    def test_education_items_are_separate_degrees(self):
        self.assertEqual(pr.list_items(["• BS Computer Science, State University", "• MS Data Science"], True),
                         ["BS Computer Science, State University", "MS Data Science"])
        self.assertEqual(pr.list_items(["BS Computer Science", "State University", "", "MS Data Science"], True),
                         ["BS Computer Science State University", "MS Data Science"])
        self.assertEqual(pr.list_items(["Bachelor of Arts", "Some University", "", "Example Country"], True),
                         ["Bachelor of Arts Some University Example Country"])       # blank lines mean nothing in PDF text
        self.assertEqual(pr.list_items(["State University", "BS Computer Science"], True),
                         ["State University BS Computer Science"])                       # school first: one item

    def test_combined_education_and_certifications_are_routed(self):
        sections = pr.route_combined(pr.split_sections(["Education & Certifications", "• BS Computer Science",
                                                       "• Example Certified Coach Professional"]))
        self.assertEqual(sections["education"], ["• BS Computer Science"])
        self.assertEqual(sections["certifications"], ["• Example Certified Coach Professional"])

    def test_diagnostics_name_a_heading_inside_a_bullet(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nLead Designer\n"
                       "• Did the work and kept it running AWARDS for 2020\n")
        self.assertTrue(any('contains the heading "awards"' in p for p in result["problems"]))


def page(left: list[str], right: list[str], width: int = 34, top: list[str] | None = None) -> str:
    """A layout-text page: `left` lines beside `right` lines, the right column starting at `width`."""
    rows = max(len(left), len(right))
    body = [f"{(left[i] if i < len(left) else ''):<{width}}{right[i] if i < len(right) else ''}".rstrip() for i in range(rows)]
    return "\n".join([*(top or []), *body]) + "\n"


SIDE = ["SKILLS", "Python", "Java", "AWS", "Kubernetes", "", "EDUCATION", "BS Computer Science", "State University", "English, French",
        "CERTIFICATIONS", "Example Certification"]
MAIN = ["SUMMARY", "Strategist with 15 years of experience.", "", "WORK EXPERIENCE", "Acme 4      09/2021 - Present",
        "Lead Designer", "• Moved 40 accounts to a new pricing model.", "  Cut cost by 30%.",
        "• Designed an order pipeline for 2 million messages.", "", "Acme 5      06/2012 - 02/2017", "Product Manager",
        "• Built the billing engine used by 3 teams.", "• Reduced build times by 40% with a shared cache.", "",
        "EDUCATION NOTES", "Dean's list in 1998 and 1999."]


class ColumnTests(unittest.TestCase):
    def test_left_side_bar_is_read_before_the_main_column(self):
        text = columns.split_columns(page(SIDE, MAIN, top=["Alex Example", ""]))
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        self.assertEqual(lines[0], "Alex Example")
        self.assertLess(lines.index("SKILLS"), lines.index("SUMMARY"))
        self.assertLess(lines.index("CERTIFICATIONS"), lines.index("SUMMARY"))
        self.assertEqual(lines[lines.index("WORK EXPERIENCE") + 1], "Acme 4      09/2021 - Present")

    def test_right_side_bar_is_read_before_the_main_column(self):
        text = columns.split_columns(page(MAIN, SIDE, width=56))
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        self.assertLess(lines.index("SKILLS"), lines.index("SUMMARY"))
        self.assertEqual(lines[lines.index("WORK EXPERIENCE") + 1], "Acme 4      09/2021 - Present")

    def test_a_single_column_page_with_right_aligned_dates_is_unchanged(self):
        rows = []
        for i in range(8):
            rows += [f"{'Employer ' + str(i):<50}{f'03/20{i:02d} - 04/20{i + 1:02d}'}", "Senior Strategist", "• Built things that last a long time."]
        text = "\n".join(rows) + "\n"
        self.assertEqual(columns.split_columns(text), text)

    def test_aligned_titles_without_a_column_are_unchanged(self):
        rows = []
        for i in range(8):
            rows += [f"{'Employer ' + str(i):<30}{'Principal Engineer ' + str(i):<30}", "• Built things that last a long time."]
        text = "\n".join(rows) + "\n"
        self.assertEqual(columns.split_columns(text), text)

    def test_a_short_column_block_in_the_middle_of_a_page_ends_at_the_full_width_text(self):
        block = [f"{(f'Left item {i}') if i < 6 else '':<30}Right item {i}" for i in range(10)]
        text = "\n".join(["Summary", "A full width line of text that is long enough.", "", *block, "", "Work History",
                          "Acme 4", "09/2021 - Present",
                          "• A full width bullet that runs across the whole page, well past the gutter column."]) + "\n"
        lines = columns.split_columns(text).splitlines()
        self.assertLess(lines.index("Left item 5"), lines.index("Right item 0"))
        self.assertLess(lines.index("Right item 9"), lines.index("Work History"))


class ReviewRegressionTests(unittest.TestCase):
    """One test per finding of the layout review (RLP-xx); each failed before the fix."""

    def test_rlp01_capital_job_title_stays_in_the_work_history(self):
        for title in ("SENIOR PRODUCT MANAGER", "LEAD DESIGNER"):
            result = parse(f"Work Experience\nAcme 4   09/2021 - Present\n{title}\n• Built a cache.\n• Cut latency.\n")
            self.assertEqual(jobs(result), [("acme-4", title, "2021-09", None, 2)], title)

    def test_rlp02_promotion_without_an_overall_date_range(self):
        text = ("Work Experience\nAcme 4\nSenior Strategist\n09/2021 - Present\n• Built a cache.\n"
                "Product Manager\n01/2018 - 08/2021\n• Built a queue.\n")
        self.assertEqual(jobs(parse(text)), [("acme-4", "Senior Strategist", "2021-09", None, 1),
                                             ("acme-4", "Product Manager", "2018-01", "2021-08", 1)])

    def test_rlp05_inline_headings_end_the_work_history(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                       "Skills: Python, Java\nEducation: BS Computer Science\n")
        self.assertEqual(result["work"][0]["bullets"], ["Built a cache."])
        self.assertEqual([s["name"] for g in result["skills"].values() for s in g], ["Python", "Java"])
        self.assertEqual(result["education"], ["BS Computer Science"])

    def test_rlp05_job_labels_stay_in_the_bullet(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache with\n"
                       "Technologies: Redis, Go\n")
        self.assertEqual(result["skills"], {})
        self.assertIn("Redis", result["work"][0]["bullets"][0])

    def test_rlp07_title_word_in_an_employer_name(self):
        for name in ("Principal Labs", "Staff Labs", "Partner Labs"):
            result = parse(f"Work Experience\n{name}   09/2021 - Present\nSenior Strategist\n• Built a cache.\n")
            self.assertEqual(jobs(result)[0][:2], (pr.re.sub(r"[^a-z0-9]+", "-", name.lower()), "Senior Strategist"), name)

    def test_rlp07_pipe_header_with_a_title_word_in_the_employer(self):
        parts = split_header("Principal Labs | Senior Strategist")
        self.assertEqual((parts.company, parts.title), ("Principal Labs", "Senior Strategist"))

    def test_rlp08_pipe_header_with_dates_on_the_next_line(self):
        for header in ("Acme 4 | Senior Strategist", "Acme 4 · Senior Strategist"):
            result = parse(f"Work Experience\n{header}\n09/2021 - Present\n• Built a cache.\n")
            self.assertEqual(jobs(result), [("acme-4", "Senior Strategist", "2021-09", None, 1)], header)

    def test_rlp09_skills_keep_their_boundaries(self):
        def names(lines: list[str]) -> list[str]:
            return [s["name"] for g in pr.parse_skills({"skills": lines})[0].values() for s in g]
        self.assertEqual(names(["Python", "pytest", "nginx", "JavaScript"]), ["Python", "pytest", "nginx", "JavaScript"])
        self.assertEqual(names(["• Python   Java   Go"]), ["Python", "Java", "Go"])
        self.assertEqual(names(["Python  Java  Go"]), ["Python", "Java", "Go"])
        self.assertEqual(names(["Kafka, Redis,", "microservices"]), ["Kafka", "Redis", "microservices"])

    def test_rlp13_open_ended_dates(self):
        for text in ("09/2021 - To date", "09/2021 - Till date", "09/2021 to date", "09/2021 until date"):
            found = dates.find_date_range(text)
            assert found is not None, text
            self.assertEqual((found.before, found.after, dates.parse_date(found.end)), ("", "", None), text)

    def test_rlp03_short_pdf_columns_with_headings_on_both_sides_are_split(self):
        side = ["Skills", "Python", "Java", "Kubernetes", "Terraform", "Education", "BS Computer Science",
                "State University", "Certifications", "Example Certification"]
        main = ["Summary", "Strategist with experience.", "Work Experience", "Acme 4   09/2021 - Present",
                "Lead Designer", "• Built a cache.", "• Cut latency by 30%.", "Acme 5   01/2018 - 08/2021",
                "Product Manager", "• Built a queue."]
        text = "\n".join(f"{left:<30}{right}" for left, right in zip(side, main, strict=True)) + "\n"
        split = columns.split_columns(text)
        self.assertNotEqual(split, text)
        result = parse(split)
        self.assertEqual([(j[0], j[4]) for j in jobs(result)], [("acme-4", 2), ("acme-5", 1)])
        self.assertEqual(result["certifications"], ["Example Certification"])

    def test_rlp03_aligned_fields_without_headings_stay_unsplit(self):
        rows = [f"{'Employer ' + str(i):<30}{'Principal Engineer ' + str(i)}" for i in range(10)]
        text = "\n".join(rows) + "\n"
        self.assertEqual(columns.split_columns(text), text)

    def test_rlp03_work_is_read_from_plain_text_when_the_layout_text_has_no_job(self):
        plain = "Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
        broken = "Work Experience\n• Built a cache.\n"
        saved = dict(pr.COMPANIES)
        found = pr.discover_companies(plain)
        pr.set_companies({k: (v, pr.re.escape(v) + rf"(?:{pr.SEP}(?P<t>.+))?") for k, v in found.items()})
        try:
            result = pr.parse_resume(plain, broken)
        finally:
            pr.set_companies(saved)
        assert result["is_resume"] is True
        self.assertEqual(jobs(result), [("acme-4", "Senior Strategist", "2021-09", None, 1)])
        self.assertIn("work history read from the reading-order text", result["problems"])

    def test_rlp04_heading_row_does_not_turn_a_timeline_table_into_columns(self):
        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body = table([[["Work Experience"]], [["09/2021 - Present"], ["Acme 4 - Senior Strategist", "- Built a cache."]],
                      [["01/2018 - 08/2021"], ["Acme 5 - Product Manager", "- Built a queue."]]])
        body = body.replace("<w:tc>", f"<w:tc><w:tcPr><w:gridSpan w:val='2' xmlns:w='{w}'/></w:tcPr>", 1)
        with tempfile.TemporaryDirectory() as tmp:
            text = extract.extract(write_docx(Path(tmp) / "t.docx", body)).text
        self.assertEqual([line for line in text.splitlines() if line.strip()][:3],
                         ["Work Experience", "Acme 4 - Senior Strategist   09/2021 - Present", "• Built a cache."])
        self.assertEqual([j[:2] for j in jobs(parse(text))], [("acme-4", "Senior Strategist"), ("acme-5", "Product Manager")])

    def test_rlp04_banner_rows_split_a_table_into_parts(self):
        rows = [[["Skills"]], [["Python"], ["Java"]], [["Work Experience"]], [["09/2021 - Present"], ["Acme 4"]]]
        self.assertEqual(extract.table_lines(rows), ["Skills", "Python   Java", "Work Experience",
                                                     "Acme 4   09/2021 - Present"])

    def test_rlp06_work_continues_after_a_right_hand_sidebar(self):
        body = (table([[["Work Experience", "Acme 4   09/2021 - Present", "Senior Strategist", "• Built a cache."],
                        ["Skills", "Python", "Education", "BS Computer Science"]]])
                + para("Acme 5   01/2018 - 08/2021") + para("Product Manager") + para("• Built a queue."))
        with tempfile.TemporaryDirectory() as tmp:
            text = extract.extract(write_docx(Path(tmp) / "t.docx", body)).text
        result = parse(text)
        self.assertEqual([j[0] for j in jobs(result)], ["acme-4", "acme-5"])
        self.assertEqual(result["education"], ["BS Computer Science"])

    def test_rlp06_columns_without_a_work_heading_keep_their_order(self):
        rows = [[["Leadership Skills", "Mentoring"], ["Technical Skills", "Python"]]]
        self.assertEqual(extract.table_lines(rows), ["Leadership Skills", "Mentoring", "Technical Skills", "Python"])

    def test_summary_without_a_heading_directly_after_the_name(self):
        text = ("Alex Example\nStrategist with fifteen years of experience building growth plans for large teams.\n\n"
                "Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n")
        self.assertEqual(parse(text)["summary"], "Strategist with fifteen years of experience building growth plans for large teams.")

    def test_a_contact_or_title_line_after_the_name_is_still_skipped(self):
        for second in ("alex@example.com | linkedin.com/in/alex-example | Seattle, WA | github.com/alex-example",
                       "Seattle, WA • alex@example.com • linkedin.com/in/alex-example • github.com/alex-example",
                       "Lead Designer"):
            text = (f"Alex Example\n{second}\n\nWork Experience\nAcme 4   09/2021 - Present\n"
                    "Senior Strategist\n• Built a cache.\n")
            self.assertEqual(parse(text)["summary"], "", second)


class FollowUpRegressionTests(unittest.TestCase):
    """Findings of the follow-up review that remained after the first fixes."""

    def test_rlp04_unmerged_heading_cell_above_timeline_rows(self):
        rows = [[["Work Experience"], []],
                [["09/2021 - Present"], ["Acme 4 - Senior Strategist", "- Built a cache."]],
                [["01/2018 - 08/2020"], ["Acme 5 - Engineer", "- Built a queue."]]]
        lines = extract.table_lines(rows)
        self.assertEqual(lines[0], "Work Experience")
        self.assertEqual([j[:2] for j in jobs(parse("\n".join(lines)))],
                         [("acme-4", "Senior Strategist"), ("acme-5", "Engineer")])

    def test_rlp04_pipe_table_heading_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.md"
            path.write_text("| Work Experience | |\n|---|---|\n| 09/2021 - Present | Acme 4 - Senior Strategist |\n"
                            "| 01/2018 - 08/2020 | Acme 5 - Engineer |\n", encoding="utf-8")
            text = extract.extract(path).text
        self.assertEqual([line for line in text.splitlines() if line.strip()][0], "Work Experience")
        self.assertEqual([j[0] for j in jobs(parse(text + "\n• Built it.\n"))][:1], ["acme-4"])

    def test_rlp04_a_sidebar_heading_cell_is_still_a_column(self):
        rows = [[["Skills", "Python"], ["Work Experience", "Acme 4   09/2021 - Present"]]]
        self.assertEqual(extract.table_lines(rows)[0], "Skills")

    def test_rlp05_technical_and_leadership_skill_sections_end_the_work_history(self):
        for heading, item in (("Technical Skills", "Python"), ("Leadership Skills", "Mentoring")):
            result = parse(f"Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                           f"{heading}: {item}, Coaching\n")
            self.assertEqual(result["work"][0]["bullets"], ["Built a cache."], heading)
            self.assertIn(item, [s["name"] for g in result["skills"].values() for s in g], heading)

    def test_rlp05_tech_stack_labels_stay_in_the_job(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                       "Tech stack: Redis, Go\n")
        self.assertEqual(result["skills"], {})

    def test_rlp07_title_word_employer_in_every_header_arrangement(self):
        headers = ["Principal Labs | Senior Strategist | 2021 - Present", "Principal Labs | Senior Strategist\n2021 - Present",
                   "Principal Labs\nSenior Strategist\n2021 - Present", "Senior Strategist | Principal Labs | 2021 - Present",
                   "Principal Labs   2021 - Present\nSenior Strategist"]
        for header in headers:
            result = parse(f"Work Experience\n{header}\n• Built a cache.\n")
            self.assertEqual(jobs(result), [("principal-labs", "Senior Strategist", "2021", None, 1)], header)

    def test_rlp16_dash_bullets_in_the_right_column_are_split(self):
        side = ["Skills", "Python", "Java", "Kubernetes", "Terraform", "Education", "BS Computer Science",
                "State University", "Certifications", "Example Certification"]
        main = ["Summary", "Strategist with experience.", "Work Experience", "Acme 4   09/2021 - Present",
                "Lead Designer", "- Built a cache.", "- Cut latency by 30%.", "Acme 5   01/2018 - 08/2021",
                "Product Manager", "- Built a queue."]
        layout = "\n".join(f"{left:<30}{right}" for left, right in zip(side, main, strict=True))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.pdf"
            path.write_bytes(b"%PDF-1.4")
            with unittest.mock.patch.object(extract.PdfExtractor, "_layout", return_value=layout), \
                    unittest.mock.patch.object(extract.PdfExtractor, "_reading_order", return_value=layout):
                document = extract.extract(path)
        self.assertEqual(document.column_pages, (1,))
        self.assertEqual([j[4] for j in jobs(parse(document.layout_text))], [2, 1])


HEAVY_SIDE = ["SKILLS", "Distributed Systems, Cloud Platforms, Service Reliability",
              "Technical Programme Management, Planning and Prioritisation",
              "Software Design, API Design, Data Transformation",
              "Infrastructure Automation, Containers, Continuous Delivery",
              "Observability, Reliability Engineering, Incident Analysis",
              "Data Modelling, Query Optimisation, Systems Integration",
              "Incident Management, Capacity Planning, Disaster Recovery",
              "Continuous Delivery, Test Automation, Release Management"]
SHORT_WORK = ["WORK EXPERIENCE", "Acme 4   2021 - Present", "Senior Strategist", "• Built a shared cache.",
              "• Cut service latency.", "• Added contract tests.", "• Led platform upgrades.", "• Shipped triage tools."]
NEXT_PAGE = "• Built a queue.\nAcme 5   2018 - 2020\nEngineer\n• Built a pipeline.\n"


class SecondReviewTests(unittest.TestCase):
    """Findings RV-09 and RV-10 of the second review (all data fictional)."""

    def test_rv09_a_text_heavy_side_bar_on_either_side_comes_before_the_work_column(self):
        for left, right, width in ((SHORT_WORK, HEAVY_SIDE, 40), (HEAVY_SIDE, SHORT_WORK, 64)):
            first = columns.split_columns(page(left, right, width=width))
            self.assertNotEqual(first, page(left, right, width=width))
            result = parse(first + NEXT_PAGE)
            self.assertEqual(jobs(result), [("acme-4", "Senior Strategist", "2021", None, 6),
                                            ("acme-5", "Engineer", "2018", "2020", 1)], width)
            skills = [s["name"] for g in result["skills"].values() for s in g]
            self.assertFalse([s for s in skills if "Acme 5" in s or "queue" in s], skills)

    def test_rv09_without_a_work_heading_the_heavier_column_is_still_last(self):
        main = ["PROJECTS" if line == "WORK EXPERIENCE" else line for line in MAIN]
        for left, right, width in ((SIDE, main, 34), (main, SIDE, 56)):
            stripped = [line.strip() for line in columns.split_columns(page(left, right, width=width)).splitlines()]
            self.assertLess(stripped.index("SKILLS"), stripped.index("PROJECTS"), width)

    def test_rv10_a_job_label_on_its_own_line_keeps_the_later_employers(self):
        for label in ("Technologies", "Tech Stack", "Accomplishments", "Tools"):
            text = ("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                    f"{label}\nRedis, Go\nAcme 5   01/2018 - 08/2021\nEngineer\n• Built a queue.\n")
            with tempfile.TemporaryDirectory() as tmp:
                md, txt = Path(tmp) / "r.md", Path(tmp) / "r.txt"
                md.write_text(text, encoding="utf-8")
                txt.write_text(text, encoding="utf-8")
                docx = write_docx(Path(tmp) / "r.docx", "".join(para(line) for line in text.splitlines()))
                texts = [extract.extract(path).text for path in (txt, md, docx)]
            inline = parse(text.replace(f"{label}\nRedis", f"{label}: Redis"))
            for extracted in texts:
                result = parse(extracted)
                self.assertEqual([j[0] for j in jobs(result)], ["acme-4", "acme-5"], label)
                self.assertEqual(result["work"], inline["work"], label)
                self.assertEqual((result["skills"], result["profile_points"]), ({}, []), label)

    def test_rv10_bullets_under_a_job_label_stay_in_the_job(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\nAccomplishments\n"
                       "• Built a cache.\n• Cut cost by 20%.\nAcme 5   01/2018 - 08/2021\nEngineer\n• Built a queue.\n")
        self.assertEqual([e["bullets"] for e in result["work"]], [["Built a cache.", "Cut cost by 20%."], ["Built a queue."]])
        self.assertEqual(result["problems"], [])

    def test_rv10_a_label_after_the_last_job_and_clear_exits_still_end_the_work_history(self):
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                       "Technologies\nRedis, Go\n\nEducation\nBS Computer Science   2010 - 2014\n")
        self.assertEqual(result["work"][0]["bullets"], ["Built a cache."])
        self.assertEqual([s["name"] for g in result["skills"].values() for s in g], ["Redis", "Go"])
        result = parse("Work Experience\nAcme 4   09/2021 - Present\nSenior Strategist\n• Built a cache.\n"
                       "Technical Skills\nPython, Go\nAcme 5   01/2018 - 08/2021\n")
        self.assertEqual(len(result["work"]), 1)


class DocxLayoutTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def lines(self, body: str, styles: str | None = None) -> list[str]:
        path = write_docx(self.tmp / "t.docx", body)
        if styles:
            import zipfile  # pylint: disable=import-outside-toplevel
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("word/styles.xml", styles)
        return extract.extract(path).text.splitlines()

    def test_a_text_box_is_its_own_block_and_read_once(self):
        inner = f"<w:txbxContent>{para('Skills')}{para('Python', listed=True)}{para('Java', listed=True)}</w:txbxContent>"
        drawing = (f"<w:p><w:r><mc:AlternateContent xmlns:mc='http://schemas.openxmlformats.org/markup-compatibility/2006'>"
                   f"<mc:Choice Requires='wps'><w:drawing>{inner}</w:drawing></mc:Choice>"
                   f"<mc:Fallback><w:pict>{inner}</w:pict></mc:Fallback></mc:AlternateContent></w:r></w:p>")
        body = para("Jane Example") + drawing + para("Summary") + para("Text.")
        lines = self.lines(body)
        self.assertEqual([line for line in lines if line], ["Jane Example", "Skills", "• Python", "• Java", "Summary", "Text."])
        self.assertEqual(lines[lines.index("Skills") - 1], "")           # set off from the text around it
        self.assertEqual(lines[lines.index("• Java") + 1], "")

    def test_bullets_set_by_the_paragraph_style_are_bullets(self):
        styles = ("<w:styles xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                  "<w:style w:type='paragraph' w:styleId='Dots'><w:pPr><w:numPr><w:numId w:val='3'/></w:numPr></w:pPr></w:style>"
                  "<w:style w:type='paragraph' w:styleId='MoreDots'><w:basedOn w:val='Dots'/></w:style>"
                  "<w:style w:type='paragraph' w:styleId='Plain'/></w:styles>")

        def styled(style: str, text: str) -> str:
            return f"<w:p><w:pPr><w:pStyle w:val='{style}'/></w:pPr><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"
        body = styled("Dots", "one") + styled("MoreDots", "two") + styled("Plain", "three")
        self.assertEqual(self.lines(body, styles), ["• one", "• two", "three"])

    def test_a_derived_style_can_switch_inherited_numbering_off(self):
        w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        styles = (f"<w:styles xmlns:w='{w}'>"
                  "<w:style w:type='paragraph' w:styleId='List'><w:pPr><w:numPr><w:numId w:val='1'/></w:numPr></w:pPr></w:style>"
                  "<w:style w:type='paragraph' w:styleId='Off'><w:basedOn w:val='List'/><w:pPr><w:numPr><w:numId w:val='0'/></w:numPr></w:pPr></w:style>"
                  "<w:style w:type='paragraph' w:styleId='OffAgain'><w:basedOn w:val='Off'/></w:style>"
                  "<w:style w:type='paragraph' w:styleId='Loop'><w:basedOn w:val='Loop'/></w:style></w:styles>")

        def styled(style: str, text: str) -> str:
            return f"<w:p><w:pPr><w:pStyle w:val='{style}'/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"
        body = styled("List", "a") + styled("Off", "Skills") + styled("OffAgain", "Tools") + styled("Loop", "c")
        self.assertEqual(self.lines(body, styles), ["• a", "Skills", "Tools", "c"])

    def test_numbering_zero_switches_a_style_bullet_off(self):
        styles = ("<w:styles xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                  "<w:style w:type='paragraph' w:styleId='Dots'><w:pPr><w:numPr><w:numId w:val='3'/></w:numPr></w:pPr></w:style></w:styles>")
        body = ("<w:p><w:pPr><w:pStyle w:val='Dots'/><w:numPr><w:numId w:val='0'/></w:numPr></w:pPr>"
                "<w:r><w:t>off</w:t></w:r></w:p>")
        self.assertEqual(self.lines(body, styles), ["off"])

    def test_headings_side_by_side_in_a_table_read_column_by_column(self):
        body = table([[["Leadership Skills"], ["Technical Skills"]], [["Team building", "Budgeting"], ["Python", "AWS"]],
                      [["Certifications"], ["Education"]], [["Example Certification"], ["BS Computer Science"]]])
        self.assertEqual(self.lines(body), ["Leadership Skills", "Team building", "Budgeting", "Certifications", "Example Certification",
                                            "Technical Skills", "Python", "AWS", "Education", "BS Computer Science"])

    def test_a_page_laid_out_as_a_table_keeps_every_heading_in_its_column(self):
        side = ["Skills", "Python", "Education", "BS Computer Science"]
        main = ["Summary", "Text.", "Work Experience", "Acme   03/2021 - Present"]
        body = table([[side, main]])
        self.assertEqual(self.lines(body), [*side, *main])

    def test_a_timeline_table_puts_the_date_after_its_entry(self):
        body = table([[["09/2021 - Present"], ["Acme Corp – Lead Designer", "Did things."]],
                      [["03/2017 - 08/2021", "Seattle, WA"], ["Acme 2 – Engineer"]]])
        self.assertEqual(self.lines(body), ["Acme Corp – Lead Designer   09/2021 - Present", "Did things.",
                                            "Acme 2 – Engineer   03/2017 - 08/2021"])

    def test_a_timeline_table_parses_to_the_work_history(self):
        timeline = table([[["09/2021 - Present"], ["Acme Corp – Lead Designer", "• Built it."]]])
        text = "\n".join(self.lines(para("Work Experience") + timeline)) + "\n"
        self.assertEqual(jobs(parse(text)), [("acme-corp", "Lead Designer", "2021-09", None, 1)])
