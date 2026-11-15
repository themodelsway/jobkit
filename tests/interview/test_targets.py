"""Tests for researched target companies: save checks, state, matching and the `target` command.
All data is fictional. Run: uv run python -m unittest discover -s tests -t ."""
import contextlib
import io
import json
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

from jk.common import ToolError
from jk.interview import target, targets
from jk.interview import target_tables as tt
from jk.user import profile
from tests.support import HomeCase

TODAY = date(2026, 11, 14)


def fact(fid="v1", **fields):
    """A valid fictional fact; `fields` override."""
    base = {"id": fid, "kind": "value", "name": "Ownership", "wording": "Owns outcomes end to end.",
            "quote": "We act on behalf of the entire company.", "link": "https://example.com/careers/values",
            "label": "company-references", "pulled": TODAY.isoformat(), "vetted": True,
            "themes": ["team-leadership"], "hints": ["deadline"]}
    base.update(fields)
    return base


def save(*facts, name="Company X", **extra):
    """A save holding the given facts."""
    return {"name": name, "facts": list(facts), **extra}


class FactCheckTests(unittest.TestCase):
    def refused(self, data, text):
        with self.assertRaises(ToolError) as caught:
            targets.merge_save(None, data, TODAY)
        self.assertIn(text, str(caught.exception))
        self.assertIn("Nothing was saved", str(caught.exception))

    def test_a_valid_fact_is_accepted(self):
        company = targets.merge_save(None, save(fact()), TODAY)
        self.assertEqual((company["key"], company["outcome"], len(company["facts"])), ("company x", "found", 1))

    def test_every_fact_needs_a_link_quote_label_date_and_vetting(self):
        self.refused(save(fact(link="")), "every fact needs a link")
        self.refused(save(fact(link="ftp://example.com/x")), "not an http or https")
        self.refused(save(fact(quote="")), "has no quote")
        self.refused(save(fact(quote=" ".join(["word"] * 41))), "41 words")
        self.refused(save(fact(label="official")), "company-references or othersite-references")
        self.refused(save(fact(pulled=(TODAY + timedelta(days=1)).isoformat())), "not in the future")
        self.refused(save(fact(vetted=False)), "is not vetted")
        self.refused(save(fact(kind="opinion")), "has kind")
        self.refused(save(fact(name="")), "value with no name")
        self.refused(save(fact(), fact()), "used twice")

    def test_wrong_shapes_are_refused_without_a_traceback(self):
        self.refused(save(fact(id=[])), "has no id")
        self.refused(save(fact(), fact("q1", kind="question", value=["v1"])), "not the id of a value")
        self.refused(save(fact(name=5)), "value with no name")
        self.refused(save(fact(link="https://[bad")), "not an http or https")
        self.refused(save(fact(), suggested_style={"style": "star", "basis": "stated", "facts": [["v1"]]}),
                     "'suggested_style' must list")
        with self.assertRaises(ToolError):
            targets.read_save(json.dumps({"name": 5, "facts": []}))

    def test_quote_of_forty_words_is_accepted(self):
        targets.merge_save(None, save(fact(quote=" ".join(["word"] * 40))), TODAY)

    def test_user_written_content_is_refused_and_editorial_articles_are_not(self):
        for link in ("https://www.reddit.com/r/jobs/comments/1", "https://stackoverflow.com/questions/1",
                     "https://www.glassdoor.com/Reviews/CompanyX-Reviews-E1.htm",
                     "https://www.glassdoor.com/Interview/CompanyX-Interview-Questions-E1.htm",
                     "https://www.indeed.com/cmp/CompanyX/reviews", "https://www.linkedin.com/posts/someone_1"):
            self.refused(save(fact(link=link)), "user-written content")
        company = targets.merge_save(None, save(fact(link="https://www.glassdoor.com/blog/how-company-x-hires/",
                                                     label="othersite-references")), TODAY)
        self.assertEqual(company["facts"][0]["label"], "othersite-references")

    def test_one_bad_fact_refuses_the_whole_save_and_names_it(self):
        facts = [fact(f"v{n}") for n in range(9)] + [fact("v9", link="")]
        self.refused(save(*facts), "fact 'v9'")

    def test_a_question_must_name_a_value_of_the_company(self):
        question = fact("q1", kind="question", value="v9", name=None)
        self.refused(save(fact(), question), "name a value this company does not have")

    def test_saving_again_replaces_by_id_and_keeps_the_others(self):
        first = targets.merge_save(None, save(fact("v1"), fact("v2", name="Pace")), TODAY)
        second = targets.merge_save(first, save(fact("v1", wording="New wording.")), TODAY)
        self.assertEqual([(f["id"], f["wording"]) for f in second["facts"]],
                         [("v1", "New wording."), ("v2", "Owns outcomes end to end.")])

    def test_suggested_style_needs_a_style_basis_and_stored_facts(self):
        grading = fact("g1", kind="grading", name=None, wording="Answers are scored as STAR.")
        ok = targets.merge_save(None, save(grading, suggested_style={"style": "star", "basis": "stated",
                                                                      "facts": ["g1"]}), TODAY)
        self.assertEqual((ok["style"], ok["style_basis"], ok["style_facts"]), ("star", "stated", ["g1"]))
        self.refused(save(grading, suggested_style={"style": "best", "basis": "stated", "facts": ["g1"]}), "suggested_style")
        self.refused(save(grading, suggested_style={"style": "carl", "basis": "inferred", "facts": ["zz"]}), "ids")

    def test_a_save_that_is_not_json_or_has_no_facts(self):
        with self.assertRaises(ToolError):
            targets.read_save("not json")
        with self.assertRaises(ToolError):
            targets.merge_save(None, save(), TODAY)


class StateTests(unittest.TestCase):
    def company(self, *ages, outcome="found", researched_age=0):
        facts = [fact(f"v{n}", pulled=(TODAY - timedelta(days=age)).isoformat()) for n, age in enumerate(ages)]
        return {"name": "Company X", "outcome": outcome, "facts": facts,
                "researched": (TODAY - timedelta(days=researched_age)).isoformat()}

    def test_fresh_stale_none_found_and_not_researched(self):
        self.assertEqual(targets.state(self.company(10), 30, TODAY), "fresh")
        stale = self.company(10, 31)
        self.assertEqual(targets.state(stale, 30, TODAY), "stale")
        self.assertEqual(targets.stale_facts(stale, 30, TODAY), ["v1"])
        self.assertEqual(targets.state(None, 30, TODAY), "not researched")
        self.assertEqual(targets.state(self.company(outcome="none found", researched_age=5), 30, TODAY), "none found")
        self.assertEqual(targets.state(self.company(outcome="none found", researched_age=40), 30, TODAY), "stale")

    def test_a_wider_window_keeps_an_older_fact_fresh(self):
        self.assertEqual(targets.state(self.company(45), 60, TODAY), "fresh")


class MatchTests(unittest.TestCase):
    def story(self, sid, theme="other", text="", status="draft"):
        return targets.story_item({"id": sid, "theme": theme, "also_themes": [], "action": text, "status": status})

    def test_theme_and_whole_word_matching(self):
        value = fact()
        self.assertEqual(targets.how(value, self.story("a", theme="team-leadership")), "theme")
        self.assertEqual(targets.how(value, self.story("b", text="We met the Deadline.")), "word")
        self.assertIsNone(targets.how(fact(hints=["lead"]), self.story("c", text="That was misleading.")))

    def test_the_four_value_states(self):
        covered = [self.story("a", theme="team-leadership")]
        self.assertEqual(targets.value_state(fact(), covered), "covered")
        self.assertEqual(targets.value_state(fact(), [self.story("b", text="a deadline")]), "possible")
        self.assertEqual(targets.value_state(fact(), [self.story("c")]), "no story")
        self.assertEqual(targets.value_state(fact(), [self.story("d", theme="team-leadership", status="empty")]),
                         "no story")
        self.assertEqual(targets.value_state(fact(themes=[], hints=[]), covered), "needs your judgment")

    def test_group_orders_theme_then_word_then_rest_and_more_values_first(self):
        company = {"facts": [fact("v1"), fact("v2", themes=["team-leadership"], hints=[])]}
        two = targets.group(company, self.story("a", theme="team-leadership"))
        word = targets.group(company, self.story("b", text="deadline"))
        rest = targets.group(company, self.story("c"))
        self.assertEqual(sorted([rest, word, two]), [two, word, rest])
        self.assertEqual(two, (0, -2))


class TargetCommandTests(HomeCase):
    def cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with mock.patch.object(sys, "stdin", io.StringIO(stdin or "")):
                code = target.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def save(self, data, name="Company X"):
        return self.cli("save", name, "--seed", "-", stdin=json.dumps(data))

    def seed(self):
        return save(fact(pulled=date.today().isoformat()),
                    fact("q1", kind="question", value="v1", name=None, wording="Tell me about owning a failure.",
                         pulled=date.today().isoformat()))

    def test_save_show_and_list(self):
        code, out = self.save(self.seed())
        self.assertEqual(code, 0, out)
        self.assertIn("now has 2", out)
        self.assertIn("match none of your stories", out)
        code, out = self.cli("show", "company x")
        self.assertEqual(code, 0, out)
        self.assertIn("Company X: fresh", out)
        self.assertIn("company-references, example.com", out)
        self.assertIn("Q: q1", out)
        self.assertIn("Company X", self.cli("list")[1])

    def test_a_save_with_one_bad_fact_stores_nothing(self):
        code, out = self.save(save(fact(pulled=date.today().isoformat()), fact("v2", link="")))
        self.assertEqual(code, 1)
        self.assertIn("v2", out)
        self.assertIsNone(tt.load_company("Company X"))

    def test_wrong_shapes_exit_cleanly_and_store_nothing(self):
        today = date.today().isoformat()
        for bad in (save(fact(id=[], pulled=today)),
                    save(fact(pulled=today), fact("q1", kind="question", value=["v1"], pulled=today)),
                    save(fact(pulled=today), suggested_style={"style": "star", "basis": "stated", "facts": [["v1"]]}),
                    save(fact(link="https://[bad", pulled=today))):
            with self.subTest(bad=bad):
                code, out = self.save(bad)
                self.assertEqual(code, 1, out)
                self.assertNotIn("Traceback", out)
                self.assertIsNone(tt.load_company("Company X"))

    def test_a_name_in_another_case_is_the_same_profile(self):
        self.save(self.seed())
        code, out = self.save(save(fact("v2", name="Pace", pulled=date.today().isoformat()), name="company x"),
                              name="company x")
        self.assertEqual(code, 0, out)
        self.assertIn("existing profile Company X", out)
        self.assertEqual(tt.company_names(), ["Company X"])

    def test_unknown_company_lists_the_profiles(self):
        self.save(self.seed())
        code, out = self.cli("show", "Other Co")
        self.assertEqual(code, 1)
        self.assertIn("Company X", out)

    def test_none_found_is_dated_and_shown(self):
        code, out = self.cli("none-found", "Small Co")
        self.assertEqual(code, 0, out)
        self.assertIn("none found", self.cli("show", "Small Co")[1])
        self.assertIn("none found", self.cli("list")[1])

    def test_recheck_dates_a_fact_and_remove_drops_it(self):
        old = (date.today() - timedelta(days=40)).isoformat()
        self.save(save(fact(pulled=old), fact("v2", name="Pace", pulled=old)))
        self.assertIn("facts v1, v2", self.cli("stale")[1])
        self.assertEqual(self.cli("recheck", "Company X", "v1")[0], 0)
        self.assertEqual(tt.load_company("Company X")["facts"][0]["pulled"], date.today().isoformat())
        self.assertEqual(self.cli("recheck", "Company X", "v2", "--remove")[0], 0)
        self.assertEqual([f["id"] for f in tt.load_company("Company X")["facts"]], ["v1"])
        code, out = self.cli("recheck", "Company X", "zz")
        self.assertEqual(code, 1)
        self.assertIn("v1", out)

    def test_removing_the_last_fact_is_refused(self):
        today = date.today().isoformat()
        self.save(save(fact(pulled=today), fact("q1", kind="question", value="v1", name=None, pulled=today)))
        code, out = self.cli("recheck", "Company X", "v1", "--remove")
        self.assertEqual(code, 1)
        self.assertIn("target remove Company X", out)
        self.assertEqual([f["id"] for f in tt.load_company("Company X")["facts"]], ["v1", "q1"])

    def test_remove_says_how_many_sessions_name_it(self):
        self.save(self.seed())
        with mock.patch.object(target.tables, "all_sessions", return_value=[{"target": "company x"}] * 2):
            code, out = self.cli("remove", "Company X")
        self.assertEqual(code, 0, out)
        self.assertIn("2 session(s) name it", out)
        self.assertIsNone(tt.load_company("Company X"))


class ProfileSettingTests(HomeCase):
    def setUp(self):
        super().setUp()
        profile.save({"resume_root": str(self.home)})

    def set(self, key, value):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return profile.main(["set", key, value])

    def test_research_window(self):
        self.assertEqual(profile.research_days(), 30)
        self.assertEqual(self.set("research_days", "60"), 0)
        self.assertEqual(profile.research_days(), 60)
        for bad in ("0", "soon"):
            self.assertEqual(self.set("research_days", bad), 1)
        self.assertEqual(profile.research_days(), 60)

    def test_default_target_company(self):
        self.assertEqual(self.set("target_company", "Company X"), 1)
        tt.save_company(targets.merge_save(None, save(fact(pulled=date.today().isoformat())), date.today()))
        self.assertEqual(self.set("target_company", "company x"), 0)
        self.assertEqual(profile.target_company(), "Company X")
        self.assertEqual(targets.find(None, use_default=True)["name"], "Company X")
        self.assertEqual(self.set("target_company", ""), 0)
        self.assertIsNone(profile.target_company())
        with self.assertRaises(ToolError):
            targets.find(None, use_default=True)

    def test_a_none_found_company_cannot_be_the_default(self):
        tt.save_company({"key": "small co", "name": "Small Co", "outcome": targets.NONE_FOUND,
                         "researched": date.today().isoformat(), "style": None, "style_basis": None,
                         "style_facts": [], "facts": []})
        self.assertEqual(self.set("target_company", "Small Co"), 1)
        self.assertIsNone(profile.target_company())

    def test_none_found_is_refused_alike_named_or_default(self):
        tt.save_company({"key": "small co", "name": "Small Co", "outcome": targets.NONE_FOUND,
                         "researched": date.today().isoformat(), "style": None, "style_basis": None,
                         "style_facts": [], "facts": []})
        profile.save({"resume_root": str(self.home), "target_company": "Small Co"})  # set before the research
        for name, default in (("Small Co", False), (None, True)):
            with self.subTest(default=default), self.assertRaises(ToolError) as caught:
                targets.find(name, use_default=default)
            self.assertIn("found no qualifying page for Small Co", str(caught.exception))
        self.assertEqual(targets.find(None, use_default=True, none_found=True)["name"], "Small Co")

    def test_a_removed_default_company_is_reported(self):
        tt.save_company(targets.merge_save(None, save(fact(pulled=date.today().isoformat())), date.today()))
        self.set("target_company", "Company X")
        tt.remove_company("Company X")
        with self.assertRaises(ToolError) as caught:
            targets.find(None, use_default=True)
        self.assertIn("no longer exists", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


def store_company(*facts, name="Company X", **extra):
    """Save a fictional researched company, dated today; return it as stored."""
    today = date.today().isoformat()
    dated = [{**f, "pulled": today} for f in facts]
    tt.save_company(targets.merge_save(None, save(*dated, name=name, **extra), date.today()))
    return tt.load_company(name)
