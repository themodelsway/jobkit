#!/usr/bin/env python3
"""EXPERIMENTAL: rate how well your stored resume lines cover a job posting (a match estimate, not any ATS score).

  match-score extract --jd posting.txt          # the requirements code can rate, or the stored result if seen before
  match-score check requests.json --jd posting.txt   # validate pass 1 output; which close calls take a fallback
  match-score run requests.json --jd posting.txt     # score, store and print the report (--json: everything)
  match-score list                              # stored results
  match-score show KEY                          # print a stored result again

`requests.json` and the posting may be "-" (standard input), but not both. The score is arithmetic over the
requirements the agent rated against your lines; it is a lower and an upper value, never a prediction.
This is not `query-resume match` (an alias of `for-jd`), which ranks lines and gives no score.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from jobkit import common
from jobkit.resumes import match_bands, match_codepass, match_engine, match_facts, match_flags, match_report
from jobkit.resumes import match_request as mr
from jobkit.resumes import match_tables


@dataclass
class Prepared:
    """A validated request with everything needed to score it."""

    request: mr.Request
    facts: match_facts.ResumeFacts
    key: str
    band: str
    weights: dict[str, Decimal]
    requirements: list[match_engine.Requirement]
    infos: list[match_flags.FlagInfo]
    assumptions: list[str]
    code_notes: list[str]
    code_ids_missing: list[str]


def _json_text(value: Any) -> str:
    """Pretty JSON text."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _read_posting(args: argparse.Namespace) -> str:
    """The posting text (`--jd`)."""
    if not args.jd:
        raise common.ToolError("Give the posting with --jd FILE (or - for standard input).")
    if getattr(args, "requests", None) == "-" and args.jd == "-":
        raise common.ToolError("Only one of the request and the posting can come from standard input.")
    text = common.read_text_arg(args.jd)
    if not text.strip():
        raise common.ToolError("The posting is empty.")
    return text


def _read_request(arg: str) -> Any:
    """The request JSON."""
    try:
        return json.loads(common.read_text_arg(arg))
    except ValueError as exc:
        raise common.ToolError(f"The request is not valid JSON: {exc}") from exc


def today() -> date:
    """The assessment date (a function so tests can set it)."""
    return date.today()


def _key(posting: str, facts: match_facts.ResumeFacts, bands_fp: str) -> str:
    """The cache key for this posting, resume data, versions and assessment date."""
    return match_facts.result_key(match_facts.posting_fingerprint(posting), match_facts.resume_fingerprint(facts),
                                  match_engine.RUBRIC_VERSION, match_engine.WEIGHTS_VERSION + bands_fp,
                                  today().isoformat())


def _run_key(base: str, band: str, request: mr.Request) -> str:
    """The stored key of a result: the cache key plus a short digest of the chosen band and the requests, so a
    different judgment of the same posting is kept next to the earlier result, not over it."""
    items = [(i.id, i.category, i.priority, str(i.importance), i.level, i.evidence, i.contest,
              None if i.flag is None else i.flag.readings) for i in request.items]
    return f"{base}-{match_facts.variant_key(band, items)}"


def prepare(args: argparse.Namespace) -> Prepared:
    """Read, validate and settle a request: priority rules, the code pass, the band, the fallbacks."""
    posting = _read_posting(args)
    facts = match_facts.load_facts()
    bands, bands_fp = match_bands.load_bands()
    request = mr.parse_request(_read_request(args.requests), facts, bands)
    if args.band:
        if args.band not in bands:
            raise common.ToolError(f"Unknown band {args.band!r}. Bands: {', '.join(bands)}.")
        request.band, request.band_alternatives = args.band, []
    mr.apply_priority_rules(request)
    code_items = match_codepass.code_pass(posting, facts)
    notes = match_codepass.apply_code(request, code_items)
    band, band_note = mr.choose_band(request)
    requirements = match_flags.build_requirements(request)
    infos = match_flags.flag_infos(request, requirements, bands[band])
    asked = {r.id for r in request.items}
    assumptions = ([band_note] if band_note else []) + [match_flags.assumption(i, match_engine.whole(i.gain))
                                                        for i in infos]
    assumptions += [note for item in code_items if item["id"] in asked for note in item.get("set_aside", [])]
    missing = [i["id"] for i in code_items if i["id"] not in asked]
    return Prepared(request, facts, _run_key(_key(posting, facts, bands_fp), band, request), band, bands[band], requirements, infos,
                    assumptions, notes, missing)


def _rows(prep: Prepared) -> list[dict[str, Any]]:
    """Each requirement as stored: its text, evidence (with the cited line text), source and flag."""
    rows = []
    for item in prep.request.items:
        try:
            texts = [match_facts.resolve(r, prep.facts) for r in item.evidence]
        except match_facts.EvidenceError as exc:
            raise common.ToolError(f"Requirement {item.label!r} cites evidence the stored resume does not "
                                   f"have: {exc}") from exc
        rows.append({"id": item.id, "label": item.label, "quote": item.quote, "section": item.section,
                     "reason": item.reason, "confidence": item.confidence, "importance": float(item.importance),
                     "evidence": item.evidence,
                     "evidence_text": texts,
                     "related": item.related, "source": "fallback" if item.flag else item.source,
                     "code_level": item.code_level,
                     "flag": None if item.flag is None else {"kind": item.flag.kind,
                                                             "readings": list(item.flag.readings)}})
    return rows


def cmd_extract(args: argparse.Namespace) -> None:
    """Show the stored result for this posting and resume data, or the requirements code can rate."""
    posting = _read_posting(args)
    facts = match_facts.load_facts()
    _, bands_fp = match_bands.load_bands()
    key = _key(posting, facts, bands_fp)
    stored = match_tables.get_latest(key, touch=True)
    if stored is not None:
        common.emit(_json_text({"key": key, "cached": True, "report": match_report.report(stored)}), args.output)
        return
    items = match_codepass.code_pass(posting, facts)
    common.emit(_json_text({"key": key, "cached": False, "code_items": items}), args.output)


def cmd_check(args: argparse.Namespace) -> None:
    """Validate pass 1 output and show how its close calls will be settled."""
    prep = prepare(args)
    flags = [{"id": i.id, "kind": i.kind, "took": i.took, "other": i.other, "swing": float(match_engine.round1(i.swing)),
              "above_threshold": i.above} for i in prep.infos]
    out = {"valid": True, "band": prep.band, "flags": flags, "vague": match_flags.is_vague(prep.infos),
           "priority_rules_applied": prep.request.rules_applied, "code_pass_notes": prep.code_notes,
           "code_items_not_in_request": prep.code_ids_missing, "assumptions": prep.assumptions}
    common.emit(_json_text(out), args.output)


def cmd_run(args: argparse.Namespace) -> None:
    """Score a request, store the result and print the report."""
    prep = prepare(args)
    result = match_engine.score(prep.requirements, prep.weights)
    meta = {"key": prep.key, "label": prep.request.label, "band": prep.band, "band_reason": prep.request.band_reason,
            "rubric_version": match_engine.RUBRIC_VERSION, "weights_version": match_engine.WEIGHTS_VERSION,
            "assumptions": prep.assumptions, "vague": match_flags.is_vague(prep.infos),
            "priority_rules_applied": prep.request.rules_applied, "code_pass_notes": prep.code_notes}
    body = match_report.build_body(_rows(prep), result, meta)
    match_tables.prune()
    match_tables.save_result(prep.key, body)
    common.emit(_json_text(body) if args.json else match_report.report(body), args.output)


def cmd_list(args: argparse.Namespace) -> None:
    """List the stored results."""
    rows = match_tables.list_results()
    if args.json:
        common.emit(_json_text(rows), args.output)
        return
    for row in rows:
        print(f"{row['key']}  {row['created']}  {row['band']}  {row['lower']:.1f} to {row['upper']:.1f}  "
              f"{row['label']}")
    print(f"{len(rows)} stored result(s)")


def cmd_show(args: argparse.Namespace) -> None:
    """Print a stored result again (the key or its first letters)."""
    keys = [r["key"] for r in match_tables.list_results() if r["key"].startswith(args.key)]
    if len(keys) != 1:
        raise common.ToolError(f"No stored result matches {args.key!r}." if not keys
                               else f"{args.key!r} matches several results; give more of the key.")
    body = match_tables.get_result(keys[0], touch=True)
    if body is None:
        raise common.ToolError(f"No stored result matches {args.key!r}.")
    common.emit(_json_text(body) if args.json else match_report.report(body), args.output)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn, helptext in (("extract", cmd_extract, "stored result, or what code can rate from the posting"),
                               ("check", cmd_check, "validate pass 1 output and settle its close calls"),
                               ("run", cmd_run, "score, store and print the report")):
        step = sub.add_parser(name, help=helptext)
        if name != "extract":
            step.add_argument("requests", help="the requirements JSON from pass 1, or - for stdin")
            step.add_argument("--band", help="use this band instead of the one in the request")
        step.add_argument("--jd", help="the job posting text file, or - for stdin")
        step.add_argument("-o", "--output", help="write the output to this file")
        if name == "run":
            step.add_argument("--json", action="store_true", help="print the full result as JSON")
        step.set_defaults(fn=fn)
    listing = sub.add_parser("list", help="stored results")
    listing.add_argument("--json", action="store_true")
    listing.add_argument("-o", "--output")
    listing.set_defaults(fn=cmd_list)
    show = sub.add_parser("show", help="print a stored result again")
    show.add_argument("key", help="the key from `list` (the first letters are enough)")
    show.add_argument("--json", action="store_true")
    show.add_argument("-o", "--output")
    show.set_defaults(fn=cmd_show)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    args = build_parser().parse_args(argv)
    return common.run(args, lock=args.cmd in ("extract", "run", "show"))


if __name__ == "__main__":
    raise SystemExit(main())
