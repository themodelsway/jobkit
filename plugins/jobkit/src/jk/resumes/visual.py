"""Visual reading of a PDF the parser cannot read (no text layer, or not readable as a PDF).

  process-resumes visual list           # PDFs that need it: the file to look at and where to save the typed-out text
  process-resumes visual render FILE    # page images of that PDF, for an agent that cannot open a PDF's pages
  process-resumes visual confirm FILE [--remove TEXT]...   # after the user has checked the typed-out text

The parser never reads images. When it cannot read a PDF it reports the file; the agent then asks the user, and only
after a yes reads the pages as images and saves the text it saw as a transcript under `output/visual/` in the home
folder. A transcript is used in place of the PDF text only after `confirm`, which ties it to the checksum of the PDF
as it is then: a transcript edit never changes which PDF it belongs to, and a replaced PDF never reuses an old
transcript. The ledger records the transcript checksum and state, so a newly confirmed transcript is read even when its
text is unchanged. The resume folder is never written. Library module apart from the `cmd_` functions.
"""
from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from jk import common
from jk.resumes import extract, visual_compare, visual_render
from jk.resumes import parse_resume as pr
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
    """The document of a file. A PDF with a transcript confirmed for it is read from the transcript, whether the
    parser could read the PDF (a reconciled reading) or not (a scan). Raises NeedsVisualRead for a PDF that needs a
    visual reading and has none, saying so when the transcript is unconfirmed or for an earlier PDF."""
    confirmed = path.suffix.lower() == ".pdf" and state(path, transcript) == "fresh"
    try:
        if not confirmed:
            return extract.extract(path)
    except extract.NeedsVisualRead as error:
        found = state(path, transcript)
        if found == "none":
            raise
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
        print(f"{item['key']}: {STATE_TEXT[item['state']]}\n  reason: {common.hide_home(item['reason'])}\n"
              f"  pdf: {common.hide_home(item['pdf'])}\n"
              f"  save the transcript as: {common.hide_home(item['transcript'])}")


def locate(files: dict[Path, tuple[str, str]], name: str) -> tuple[Path, Path, str]:
    """(file, transcript path, key) of the one resume PDF whose key or file name is `name`; `files` maps each file
    to its (ledger key, transcript file name). Raises ToolError unless exactly one PDF matches."""
    found = [(path, VISUAL_DIR / names[1], names[0]) for path, names in files.items()
             if path.suffix.lower() == ".pdf" and name in (names[0], path.name)]
    if len(found) != 1:
        raise common.ToolError(f"{name!r} matches {len(found)} PDF resumes; use the path shown by "
                               "`process-resumes visual list` or relative to the resume folder.")
    return found[0]


def parse_document(document: extract.ExtractedDocument) -> pr.ParsedResume:
    """Parse a document with the employers found in it added to the registry (as a run of `process-resumes` does)."""
    found = pr.discover_companies(document.layout_text or document.text) or pr.discover_companies(document.text)
    pr.set_companies({**pr.COMPANIES, **{k: (v, re.escape(v) + rf"(?:{pr.SEP}(?P<t>.+))?")
                                         for k, v in found.items() if k not in pr.COMPANIES}})
    return pr.parse_resume(document.text, document.layout_text)


def _roles(parsed: pr.ParsedResume) -> list[tuple[str, str, str | None, list[str]]]:
    """(employer id, employer name, start, bullets) of each role of a parse; none for a file that is not a resume."""
    if parsed["is_resume"] is False:
        return []
    return [(e["company_id"], pr.COMPANIES.get(e["company_id"], (e["company_id"],))[0], e["start"], list(e["bullets"]))
            for e in parsed["work"]]


def _pair(role: tuple[str, str, str | None, list[str]], pool: list[tuple[str, str, str | None, list[str]]]) -> int | None:
    """Index in `pool` of the role that is `role`: the same employer and start, else the same employer."""
    same = [i for i, other in enumerate(pool) if other[0] == role[0]]
    return next((i for i in same if pool[i][2] == role[2]), same[0] if same else None)


def lost_items(before: pr.ParsedResume, after: pr.ParsedResume) -> list[str]:
    """What the PDF's own text has and a transcript lost, one entry each: a role as 'EMPLOYER START', a bullet as its
    text. Roles are paired by employer and start date and bullets within a role by likeness, so a bullet moved to
    another employer or a removed duplicate is a loss even when the totals stay equal; a reworded bullet is not."""
    lost: list[str] = []
    pool = _roles(after)
    for role in _roles(before):
        index = _pair(role, pool)
        if index is None:
            lost.append(f"{role[1]} {role[2] or ''}".strip())
            continue
        kept = pool.pop(index)[3]
        for bullet in role[3]:
            best = max(kept, key=lambda other, b=bullet: pr.similar(other, b), default=None)
            if best is None or pr.similar(best, bullet) < visual_compare.SIMILAR_BULLET:
                lost.append(bullet)
            else:
                kept.remove(best)
    return lost


def _removals(transcript: Path) -> Path:
    """The small file that records the roles and bullets the user agreed to remove when confirming a transcript."""
    return transcript.with_name(transcript.name + ".removed")


def check_correction(path: Path, transcript: Path, approved: list[str]) -> list[str]:
    """The roles and bullets of the PDF's own text that the transcript drops, each of them approved; raises
    ToolError naming any loss not in `approved`, or an approval that matches no loss.

    The parser reads work history from the layout text and the other sections from the reading-order text, but a
    transcript is read as both, so a transcript saved from `visual text` can lose work bullets the PDF kept; a
    correction may also remove an erroneous role or bullet on purpose, which the user approves item by item. Nothing
    is checked for a PDF the parser cannot read (a scan has no parse to compare with).
    """
    try:
        original = extract.extract(path)
    except common.ToolError:
        return []
    text = transcript.read_text(encoding="utf-8")
    lost = lost_items(parse_document(original), parse_document(extract.ExtractedDocument(text, text, "visual")))
    wanted = {visual_compare.exact(item) for item in approved}
    unknown = sorted(wanted - {visual_compare.exact(item) for item in lost})
    if unknown:
        raise common.ToolError(f"Not confirmed: --remove {unknown[0]!r} is not a role or bullet the transcript drops.")
    unapproved = [item for item in lost if visual_compare.exact(item) not in wanted]
    if unapproved:
        raise common.ToolError(
            "Not confirmed: the transcript drops these roles or work bullets of the PDF's own text:\n"
            + "\n".join(f"  {item}" for item in unapproved)
            + "\nIf the user agreed to remove one, confirm again with `--remove TEXT` for each (TEXT as listed). "
            "Otherwise put the work history in the transcript in the order of `process-resumes visual text FILE "
            "--layout`, then confirm again.")
    return lost


def cmd_confirm(files: dict[Path, tuple[str, str]], name: str, approved: list[str] | None = None) -> None:
    """Confirm the saved transcript of one PDF (see `locate`); `approved` lists the roles and bullets the user agreed
    to remove, which are recorded beside the transcript."""
    path, transcript, key = locate(files, name)
    removed = check_correction(path, transcript, approved or []) if transcript_sha(transcript) is not None else []
    confirm(path, transcript)
    if removed:
        _removals(transcript).write_text("\n".join(removed) + "\n", encoding="utf-8")
    else:
        _removals(transcript).unlink(missing_ok=True)
    visual_render.clear(visual_render.pages_folder(transcript))
    extra = f" with {len(removed)} agreed removal(s), recorded in {common.hide_home(str(_removals(transcript)))}" if removed else ""
    print(f"Confirmed the transcript for {key}{extra}. Run process-resumes to read it.")


def cmd_render(files: dict[Path, tuple[str, str]], name: str) -> None:
    """Write the pages of one PDF as images under `output/visual/pages/` and print their paths."""
    path, transcript, _ = locate(files, name)
    for image in visual_render.render(path, visual_render.pages_folder(transcript)):
        print(common.hide_home(str(image)))


def cmd_compare(files: dict[Path, tuple[str, str]], name: str, reading_text: str) -> None:
    """Compare a visual reading (JSON text, see READING_SCHEMA) of one PDF with what the parser reads from it."""
    path, transcript, key = locate(files, name)
    reading = visual_compare.read_reading(reading_text)
    document = read_document(path, transcript)
    parsed = parse_document(document)
    if parsed["is_resume"] is False:
        parsed = pr.Resume(is_resume=True, work=[], skills={}, summary="", headline="", profile_points=[],
                           certifications=[], education=[], projects=[], problems=parsed["problems"])
    print(visual_compare.format_report(key, visual_compare.compare(parsed, reading)))
    if document.format == "visual":
        print(f"(the parser side is the confirmed transcript at {common.hide_home(str(transcript))})")
    elif visual_compare.compare(parsed, reading):
        print(f"If corrections are agreed: save the full corrected text as {common.hide_home(str(transcript))} "
              f"(its current text is shown by "
              f"`process-resumes visual text {name}`), then run `process-resumes visual confirm {name}`.")


def cmd_text(files: dict[Path, tuple[str, str]], name: str, layout: bool = False) -> None:
    """Print the text the parser works from for one PDF (the confirmed transcript when there is one); with `layout`,
    the layout reading the work history is parsed from."""
    path, transcript, _ = locate(files, name)
    document = read_document(path, transcript)
    print(document.layout_text if layout else document.text)


def add_parser(sub: Any, run: Any) -> None:
    """Register `visual list` and `visual confirm FILE` on a subparsers action; `run(args)` does the work."""
    visual = sub.add_parser("visual", help="PDFs the parser cannot read, for a visual reading the user agreed to")
    actions = visual.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    confirm_cmd = actions.add_parser("confirm")
    confirm_cmd.add_argument("file", help="the PDF, as shown by `visual list`")
    confirm_cmd.add_argument("--remove", action="append", default=[], metavar="TEXT",
                             help="a role or work bullet the user agreed to remove, as the refusal lists it (repeatable)")
    actions.add_parser("render", help="write the pages of a PDF as images and print their paths").add_argument("file")
    actions.add_parser("schema", help="print the JSON a visual reading must return")
    text = actions.add_parser("text", help="print the text the parser works from for a PDF")
    text.add_argument("file")
    text.add_argument("--layout", action="store_true", help="print the layout reading (work history is parsed from it)")
    compare = actions.add_parser("compare", help="compare a visual reading (JSON) of a PDF with what the parser read")
    compare.add_argument("file", help="the PDF, as shown by `visual list` or relative to the resume folder")
    compare.add_argument("--reading", required=True, help="the visual reading as JSON; `-` reads standard input")
    visual.set_defaults(fn=run)
