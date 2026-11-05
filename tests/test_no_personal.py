"""Committed (or committable) files must contain nothing personal.

Checks every file git would commit (tracked + untracked, minus .gitignore) for:
  * generic leaks: home-directory paths, email addresses, phone numbers
  * anything in the git-ignored profile/: your name, resume folder and employer names

Without a profile/ only the generic checks run.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HOME_PATH = re.compile("/" + "Users/|/" + "home/[a-z]|C:" + r"\\Users", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@(?!example\.)[\w-]+\.(?:com|net|org|io|dev)\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,2}[ -])?\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?!\d)")
SKIP_SUFFIX = {".png", ".jpg", ".pdf", ".pyc"}


def committable():
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
    return [ROOT / f for f in out.splitlines() if (ROOT / f).is_file() and (ROOT / f).suffix not in SKIP_SUFFIX
            and f != "tests/test_no_personal.py"]


def personal_terms():
    terms = set()
    prof = ROOT / "profile"
    if (prof / "profile.json").exists():
        p = json.loads((prof / "profile.json").read_text())
        for k in ("name", "resume_root"):
            if p.get(k):
                terms.add(str(p[k]).strip())
        header = prof / "header.md"
        if header.exists():
            first = header.read_text().splitlines()[:1]
            terms |= {re.sub(r"^#\s*", "", ln).strip() for ln in first}
    if (prof / "companies.json").exists():
        for c in json.loads((prof / "companies.json").read_text()).values():
            terms.add(c["name"])
    return {t for t in terms if len(t) >= 3 and t.lower() != "your name"}


class TestNoPersonalData(unittest.TestCase):
    def test_generic_leaks(self):
        bad = []
        for f in committable():
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if HOME_PATH.search(line) or EMAIL.search(line) or PHONE.search(line):
                    bad.append(f"{f.relative_to(ROOT)}:{n}")
        self.assertEqual(bad, [], "home path, email or phone number in committable files")

    def test_profile_terms(self):
        terms = personal_terms()
        if not terms:
            self.skipTest("no profile/ terms (name, resume folder, employers): only the generic checks ran")
        bad = []
        for f in committable():
            low = f.read_text(errors="ignore").lower()
            bad += [f"{f.relative_to(ROOT)}: {t}" for t in terms if t.lower() in low]
        self.assertEqual(bad, [], "values from profile/ found in committable files")


if __name__ == "__main__":
    unittest.main()
