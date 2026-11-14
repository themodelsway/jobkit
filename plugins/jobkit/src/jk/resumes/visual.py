"""Visual reading of a PDF the parser cannot read (no text layer, or not readable as a PDF).

  process-resumes visual list           # PDFs that need it: the file to look at and where to save the typed-out text
  process-resumes visual confirm FILE   # after the user has checked the typed-out text of that PDF

The parser never reads images. When it cannot read a PDF it reports the file; the agent then asks the user, and only
after a yes reads the pages as images and saves the text it saw as a transcript under `output/visual/` in the home
folder. A transcript is used in place of the PDF text only after `confirm`, which ties it to the checksum of the PDF
as it is then: a transcript edit never changes which PDF it belongs to, and a replaced PDF never reuses an old
transcript. The ledger records the transcript checksum and state, so a newly confirmed transcript is read even when its
text is unchanged. The resume folder is never written. Library module apart from the `cmd_` functions.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from jk import common
from jk.resumes import extract
from jk.resumes import resume_data as rd

VISUAL_DIR: Final[Path] = rd.TEXT_DIR / "visual"


def transcript_sha(transcript: Path) -> str | None:
    """Checksum of a non-empty transcript, or None when there is none."""
    if not transcript.is_file():
        return None
    raw = transcript.read_bytes()
    return sha256(raw).hexdigest() if raw.strip() else None


def source_sha(pdf: Path) -> str:
    """Checksum of the PDF file."""
    return sha256(pdf.read_bytes()).hexdigest()


def _bound_to(transcript: Path) -> Path:
    """The small file that records which PDF (by checksum) the user confirmed a transcript for."""
    return transcript.with_name(transcript.name + ".source")


def state(pdf: Path, transcript: Path) -> str:
    """'none' (no usable transcript), 'unconfirmed' (saved, but not yet confirmed for any PDF), 'stale' (confirmed for
    a different version of this PDF) or 'fresh' (confirmed for this PDF). Editing a transcript never changes which
    PDF it is confirmed for; only `confirm` does, after the user has checked the reading of that PDF."""
    if transcript_sha(transcript) is None:
        return "none"
    bound = _bound_to(transcript)
    if not bound.is_file():
        return "unconfirmed"
    return "fresh" if bound.read_text(encoding="utf-8").strip() == source_sha(pdf) else "stale"


def fingerprint(pdf: Path, transcript: Path) -> str | None:
    """What the ledger records about a transcript: its checksum and its state, so a transcript that becomes confirmed
    for the current PDF is processed again even when its text did not change. None without a transcript."""
    sha = transcript_sha(transcript)
    return None if sha is None else f"{sha}:{state(pdf, transcript)}"


def confirm(pdf: Path, transcript: Path) -> None:
    """Record that the transcript is the confirmed reading of this PDF as it is now."""
    if transcript_sha(transcript) is None:
        raise common.ToolError(f"No transcript is saved at {transcript}. Save the typed-out text there first.")
    _bound_to(transcript).write_text(source_sha(pdf), encoding="utf-8")


NOT_READY: Final[dict[str, str]] = {
    "unconfirmed": "the saved transcript has not been confirmed yet (after the user has checked it, run "
                   "`process-resumes visual confirm FILE`)",
    "stale": "the saved transcript was confirmed for an earlier version of this PDF"}


def read_document(path: Path, transcript: Path) -> extract.ExtractedDocument:
    """The document of a file; for a PDF that needs a visual reading, the transcript confirmed for this PDF.
    Raises NeedsVisualRead when there is none, saying so when the transcript is unconfirmed or for an earlier PDF."""
    try:
        return extract.extract(path)
    except extract.NeedsVisualRead as error:
        found = state(path, transcript)
        if found == "none":
            raise
        if found != "fresh":
            raise extract.NeedsVisualRead(f"{path.name}: {NOT_READY[found]}. {extract.VISUAL_HINT}") from error
        text = transcript.read_text(encoding="utf-8")
        return extract.ExtractedDocument(text, text, "visual")


def pending(files: list[Path], names: dict[Path, tuple[str, str]]) -> list[dict[str, Any]]:
    """The files that need a visual reading: {file, key, reason, pdf, transcript, state} for each. `names` gives each
    file its (ledger key, transcript file name)."""
    found = []
    for path in files:
        transcript = VISUAL_DIR / names[path][1]
        try:
            extract.extract(path)
        except extract.NeedsVisualRead as error:
            found.append({"file": path.name, "key": names[path][0], "reason": str(error), "pdf": str(path),
                          "transcript": str(transcript), "state": state(path, transcript)})
        except common.ToolError:
            continue
    return found


STATE_TEXT: Final[dict[str, str]] = {
    "none": "no transcript yet (ask the user first)",
    "unconfirmed": "transcript saved, not confirmed yet (after the user has checked it: `visual confirm FILE`)",
    "stale": "the confirmed transcript is for an earlier version of this PDF (ask the user again, save a new "
             "transcript, then confirm it)",
    "fresh": "transcript confirmed"}


def cmd_list(entries: list[dict[str, Any]]) -> None:
    """Print each file that needs a visual reading, and what to do with it."""
    if not entries:
        print("No PDF needs a visual reading.")
        return
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    for item in entries:
        print(f"{item['key']}: {STATE_TEXT[item['state']]}\n  reason: {item['reason']}\n  pdf: {item['pdf']}\n"
              f"  save the transcript as: {item['transcript']}")


def cmd_confirm(entries: list[dict[str, Any]], name: str) -> None:
    """Confirm the saved transcript of the one listed file whose key (or file name) is `name`."""
    found = [item for item in entries if name in (item["key"], item["file"])]
    if len(found) != 1:
        raise common.ToolError(f"{name!r} matches {len(found)} PDFs that need a visual reading; use the full path "
                               "shown by `process-resumes visual list`.")
    confirm(Path(found[0]["pdf"]), Path(found[0]["transcript"]))
    print(f"Confirmed the transcript for {found[0]['key']}. Run process-resumes to read it.")


def add_parser(sub: Any, run: Any) -> None:
    """Register `visual list` and `visual confirm FILE` on a subparsers action; `run(args)` does the work."""
    visual = sub.add_parser("visual", help="PDFs the parser cannot read, for a visual reading the user agreed to")
    actions = visual.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    actions.add_parser("confirm").add_argument("file", help="the PDF, as shown by `visual list`")
    visual.set_defaults(fn=run)
