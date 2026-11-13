"""The manual pages must name every command, subcommand and option the parsers define (and nothing is left undocumented)."""
import argparse
import importlib
import sqlite3
import unittest
from collections.abc import Iterator
from pathlib import Path

from jk import records, store
from tests.test_cli_contract import TOOLS

DOCS = Path(__file__).resolve().parents[1] / "docs"
COMMANDS = {"jobkit": "jk.admin", "profile": "jk.user.profile", "process-resumes": "jk.resumes.process_resumes",
            "query-resume": "jk.resumes.query_resume", "build-resume": "jk.resumes.build_resume", "resume-lines": "jk.resumes.lines", "match-score": "jk.resumes.match_score",
            "arch": "jk.interview.arch", "lead": "jk.interview.lead", "prep": "jk.interview.prep",
            "sessions": "jk.interview.sessions", "readiness": "jk.interview.readiness"}


def walk(parser: argparse.ArgumentParser, path: list[str]) -> Iterator[tuple[list[str], list[str]]]:
    """(command path, long options) for every parser and subparser."""
    subs = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    opts = [o for a in parser._actions for o in a.option_strings if o.startswith("--") and o != "--help"]
    yield path, opts
    if subs:
        for name, sub in subs.choices.items():
            yield from walk(sub, [*path, name])


class ManualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manual = "\n".join((DOCS / name).read_text(encoding="utf-8")
                               for name in ("manual.md", "guides/interview-prep.md", "guides/tutor.md", "guides/resume-workflows.md"))

    def test_commands_match_the_tool_list(self):
        self.assertEqual(sorted(m for m in COMMANDS.values()), sorted(TOOLS))

    def test_every_command_and_option_is_documented(self):
        missing = []
        for tool, module in COMMANDS.items():
            parser = importlib.import_module(module).build_parser()
            for path, opts in walk(parser, [tool]):
                if " ".join(path) not in self.manual:
                    missing.append(" ".join(path))
                missing += [f"{' '.join(path)} {o}" for o in opts if o not in self.manual]
        self.assertEqual(missing, [], "add these to the manual pages in docs/")


class SchemaDocTests(unittest.TestCase):
    def test_every_export_kind_is_described(self):
        """Every kind that `jobkit export` handles is named, in backticks, in docs/references/data-structures.md."""
        text = (DOCS / "references" / "data-structures.md").read_text(encoding="utf-8")
        missing = [k.name for k in records.KINDS if f"`{k.name}`" not in text]
        self.assertEqual(missing, [], "export kinds missing from docs/references/data-structures.md")

    def test_every_table_is_described(self):
        """Every table the migrations create is named, in backticks, in docs/references/data-structures.md."""
        text = (DOCS / "references" / "data-structures.md").read_text(encoding="utf-8")
        conn = sqlite3.connect(":memory:")
        for step in store.MIGRATIONS:
            step(conn)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                             "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        conn.close()
        missing = [t for t in tables if f"`{t}`" not in text]
        self.assertEqual(missing, [], "tables missing from docs/references/data-structures.md")


if __name__ == "__main__":
    unittest.main()
