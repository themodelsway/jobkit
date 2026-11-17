"""Shared helpers for the interview tests: a session-ready home folder, fictional researched companies and stories,
and an in-process `prep` runner. All data is fictional."""
import contextlib
import io
from datetime import date
from unittest import mock

from jk import common, store
from jk.interview import cards, lead, prep, sessions, tables, targets
from jk.interview import story_model as sm
from jk.interview import target_tables as tt
from tests.support import HomeCase, call


def drop_catalog() -> None:
    """Remove the card catalog (and with it every card's progress), as before `cards init`."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM meta WHERE key='cards.catalog'")
        conn.execute("DELETE FROM card")


# The resume data the session tests read: one company and one skill.
COMPANIES = {"acme": {"id": "acme", "name": "Acme", "bullets": [], "roles": [{"start": "2021-01", "end": None, "titles": ["T"]}]}}
SKILLS = {"groups": {"Cloud": [{"name": "VPC", "aliases": []}]}}


class SessionCase(HomeCase):
    """A home folder with the card and leadership catalogs set up, ready for practice sessions."""

    def setUp(self):
        super().setUp()
        self.tmp = self.home
        for obj, name, value in ((cards.qr, "load", (COMPANIES, SKILLS)), (lead.qr, "load", (COMPANIES, SKILLS))):
            patcher = mock.patch.object(obj, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cards.up, "key_topics", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cli(cards.main, "init", "--track", "aws")
        self.cli(lead.main, "init")

    def cli(self, main, *argv, stdin=None):
        """Run a command's `main`; (status, stdout, stderr)."""
        return call(main, *argv, stdin=stdin)

    def new_session(self, *extra):
        code, out, err = self.cli(sessions.main, "new", "Warm up", "--count", "3", *extra)
        self.assertEqual(code, 0, err)
        return out.split("Started session ")[1].split(" ")[0]

    def session(self, sid):
        return tables.load_session(sid)


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


def store_company(*facts, name="Company X", **extra):
    """Save a fictional researched company, dated today; return it as stored."""
    today = date.today().isoformat()
    dated = [{**f, "pulled": today} for f in facts]
    tt.save_company(targets.merge_save(None, save(*dated, name=name, **extra), date.today()))
    return tt.load_company(name)


def story(sid, theme="other", status="draft", action=""):
    """A fictional story with the fields the queue and the matching read."""
    return {"id": sid, "company": "acme", "company_name": "Acme", "theme": theme, "headline": sid,
            "metrics_on_resume": [], "anchor_bullets": [], "situation": None, "task": None, "action": action or None,
            "result": None, "metric": None, "lessons": None, "notes": None, "follow_ups": [], "status": status,
            "also_themes": []}


class TargetCase(SessionCase):
    """A session-ready home folder with five fictional stories and one researched company, Company X."""

    def setUp(self):
        super().setUp()
        tables.replace_stories({"stories": [
            story("s1"), story("s2", theme="mentoring"), story("s3", action="We met a hard deadline."),
            story("s4", theme="delivery"), story("s5")]})
        self.company = store_company(
            fact("v1", name="Growth", themes=["mentoring", "delivery"], hints=[]),
            fact("v2", name="Pace", themes=["delivery"], hints=["deadline"]),
            fact("v3", name="Judgment", themes=[], hints=[]),
            fact("q3", kind="question", value="v3", wording="Tell me about a hard call."),
            fact("g1", kind="grading", wording="Interviewers score ownership of the result."))

    def started(self, *extra):
        code, out, err = self.cli(sessions.main, "new", "Company prep", "--mode", "stories", *extra)
        self.assertEqual(code, 0, err)
        return out.split("Started session ")[1].split(" ")[0], out

    def queue(self, sid):
        return [q["id"] for q in self.session(sid)["queue"]]

    def log(self, sid, item, *extra):
        return self.cli(sessions.main, "log", sid, item, "--question", "Q", "--answer", "An answer.", *extra)


def run_prep(*argv):
    """Run one `prep` command in a transaction; (exit status, stdout with any error message)."""
    out = io.StringIO()
    code = 0
    a = prep.build_parser().parse_args(list(argv))
    with contextlib.redirect_stdout(out):
        try:
            with store.transaction():
                code = a.fn(a) or 0
        except common.ToolError as e:
            code = 1
            out.write(str(e))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                out.write(e.code)
    return code, out.getvalue()


class PrepCase(HomeCase):
    """A home folder holding one empty story, `acme-topic-a`, for the `prep` commands."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(prep.qr, "load", return_value=({"acme": {"id": "acme", "name": "Acme Corp"}}, None))
        patcher.start()
        self.addCleanup(patcher.stop)
        seeded = {"stories": [{"id": "acme-topic-a", "company": "acme", "company_name": "Acme Corp", "theme": "topic-a",
                           "headline": "Led topic A", "metrics_on_resume": [], "anchor_bullets": ["b1"],
                           "situation": None, "task": None, "action": None, "result": None, "metric": None, "lessons": None,
                           "notes": None, "follow_ups": ["Batch size?"], "status": "empty"}]}
        tables.replace_stories(seeded)

    def story(self, sid="acme-topic-a"):
        return next(s for s in prep.stories() if s["id"] == sid)

    def fill_star(self, sid="acme-topic-a"):
        for f in sm.STAR:
            self.assertEqual(run_prep("set", sid, f, f"I did the {f}.")[0], 0)
