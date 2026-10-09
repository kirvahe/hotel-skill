#!/usr/bin/env python3
"""Shared helpers for the find-hotel pipeline scripts. Not a pipeline step of its own.

Holds the hotel name key that every script matches names with, the run-folder
file names and readers, the evidence merge, and the checkpoint records that
render.py and apply_reply.py share. This docstring is the one list of run files.

Files the pipeline adds to the run folder (see ledger.py for trip, candidates,
envelopes, evidence and state):
    merged.jsonl          merge_candidates.py  one record per hotel, all families merged
    merge-decisions.json  the model            {"same": [["Name A", "Name B"], ...]} for close pairs
    fit-rules.json        the model            {"floor", "limited_choice", "do_not_recommend", "excluded_kinds"}
    taste.json            the model            {"taste_summary", "judgment_rules"} for the agent prompts
    context.json          orchestrate.py       dog note and the city cache read at stage 2
    blacklist.json        orchestrate.py       blacklist.py output plus the city cache's Excluded rows
    stays.json            orchestrate.py       stays.py output plus Gmail bookings
    gmail-bookings.json   the Gmail agent      Booking confirmations (ledger kind "gmail")
    research.json         orchestrate.py       source map, district notes and negative reports from the envelopes
    families.json         orchestrate.py       ran / partial / failed per research family, re-prompts
    modules.json          orchestrate.py       ran / partial / skipped / failed per optional module (R22)
    batches.json          orchestrate.py       resolver and final-check batches
    resolved-{n}.jsonl    resolver agent       official site and judgment calls (ledger kind "resolved")
    resolved.json         orchestrate.py       resolver lines merged per candidate
    evidence-resolver-{n}.jsonl, evidence-final-{n}.jsonl, evidence-reader.jsonl
                          agents and reader    evidence parts, merged into evidence.jsonl by merge_evidence()
    reads.json            orchestrate.py       which candidates the reader read, for which dates
    final-{n}.jsonl       final-check agent    rate and cancellation (ledger kind "final")
    final.json            orchestrate.py       final-check lines merged per candidate
    fit.json              fit_filter.py        keep / remove per candidate, reason code, flags, past stays
    status.json           status_table.py      available / unavailable / unknown per candidate
    verdicts.json         the model            {"clearly_better": [{"candidate", "reason"}], "not_better": [...]} (R25)
    advice.json           the model            overview, "why you" and vibe lines, district advice, tips
    reply.json            the model            the latest checkpoint reply, input to orchestrate.py checkpoint
    numbers.json          render.py            stable entry numbers {"numbers": {id: n}, "next": n}
    checkpoints.json      apply_reply.py       strike-outs and changes, one record per reply

The answer is saved next to the run folder, in the trip folder, as ANSWER_FILE.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import ledger

# Words dropped from a name key, so "Hotel Casa Velarta" and "Casa Velarta" match.
GENERIC_WORDS = ("hotel",)

MERGED, FIT, STATUS, TRIP, STATE = "merged.jsonl", "fit.json", "status.json", "trip.json", "state.json"
EVIDENCE = "evidence.jsonl"
EVIDENCE_PARTS = "evidence-*.jsonl"
READER_EVIDENCE = "evidence-reader.jsonl"
RESOLVER_EVIDENCE, FINAL_EVIDENCE = "evidence-resolver-{batch}.jsonl", "evidence-final-{batch}.jsonl"
RESOLVED_PART, FINAL_PART = "resolved-{batch}.jsonl", "final-{batch}.jsonl"
CANDIDATES, ENVELOPE = "candidates-{family}.jsonl", "envelope-{family}.json"
MERGE_DECISIONS = "merge-decisions.json"
RESOLVED, FINAL = "resolved.json", "final.json"
FIT_RULES, TASTE, CONTEXT = "fit-rules.json", "taste.json", "context.json"
BLACKLIST, STAYS, GMAIL = "blacklist.json", "stays.json", "gmail-bookings.json"
RESEARCH, FAMILIES, MODULES, BATCHES, READS = "research.json", "families.json", "modules.json", "batches.json", "reads.json"
VERDICTS, ADVICE, NUMBERS, CHECKPOINTS = "verdicts.json", "advice.json", "numbers.json", "checkpoints.json"
ANSWER_FILE = "hotels-shortlist.md"

MODULES_ORDER = ("gmail", "resolver", "reader", "final_check")
STATUSES = ("ran", "partial", "skipped", "failed")


class RunError(Exception):
    """A missing or broken run-folder input. Each CLI prints it and exits 2."""


def tokens(name: str) -> list[str]:
    """Lowercase ASCII words of a name: accents stripped, punctuation dropped."""
    return [word for word in ledger.city_slug(str(name)).split("-") if word]


def name_key(name: str) -> str:
    words = tokens(name)
    kept = [word for word in words if word not in GENERIC_WORDS]
    return " ".join(kept or words)


def record_keys(record: dict) -> set[str]:
    """Name keys of a candidate: its name, local name and every merged alias."""
    names = [record.get("name"), record.get("local_name")] + list(record.get("aliases") or [])
    return {name_key(name) for name in names if name}


def records_naming(candidate: dict, records: list, key: str = "candidate") -> list:
    """The records whose record[key] names this candidate by any of its names (record_keys)."""
    keys = record_keys(candidate)
    return [r for r in records if name_key(r.get(key, "")) in keys]


def match_by_name(merged: list, records: list, key: str = "candidate") -> tuple[dict, list]:
    """Group records by the merged candidate whose name key they share: ({id: [records]}, [unmatched names])."""
    by_id: dict = {c["id"]: [] for c in merged}
    keys = [(c["id"], record_keys(c)) for c in merged]
    unmatched = []
    for record in records:
        name = str(record.get(key, ""))
        own = name_key(name)
        target = next((cid for cid, ckeys in keys if own in ckeys), None)
        if target is None:
            unmatched.append(name)
        else:
            by_id[target].append(record)
    return by_id, unmatched


def nights(trip: dict) -> int:
    """Nights of the trip: check_out minus check_in."""
    return (date.fromisoformat(trip["check_out"]) - date.fromisoformat(trip["check_in"])).days


def kept_hotels(fit: dict, struck: dict) -> list:
    """fit.json candidates the filter kept in the hotels block and the user has not struck out."""
    return [c for c in fit["candidates"] if c["decision"] == "keep" and c["block"] == "hotels" and c["id"] not in struck]


def trip_dir(run_dir: Path) -> Path:
    """trips/{city-slug}-{YYYY-MM}/ holds the run folder and the saved answer."""
    return Path(run_dir).parent


def data_dir(run_dir: Path) -> Path:
    """The data folder: run folders live at DATA/trips/{city-slug}-{YYYY-MM}/run."""
    return Path(run_dir).parent.parent.parent


def merge_evidence(run_dir: Path) -> dict:
    """Merge every evidence-*.jsonl part into evidence.jsonl: validated, deduplicated, order kept.

    Agents and the reader write their own part files, so parallel writers never collide; this
    is the one place that combines them. Safe to run again: records already merged are not added.
    """
    run_dir = Path(run_dir)
    target = run_dir / EVIDENCE
    records, seen, rejected = [], set(), []
    parts = sorted(p for p in run_dir.glob(EVIDENCE_PARTS))
    before = 0
    for path in ([target] if target.is_file() else []) + parts:
        valid, bad = ledger.read_records(path, "evidence", label="candidate")
        rejected += [dict({"file": path.name}, **r) for r in bad]
        for record in valid:
            fingerprint = json.dumps(record, sort_keys=True, ensure_ascii=False)
            if fingerprint not in seen:
                seen.add(fingerprint)
                records.append(record)
        if path == target:
            before = len(records)
    write_jsonl(target, records)
    return {"records": len(records), "added": len(records) - before,
            "files": [p.name for p in parts], "rejected": rejected}


def city_key(city, default: str) -> str:
    return ledger.city_slug(city) if city else default


def read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def load_json(run_dir: Path, name: str, hint: str):
    path = Path(run_dir) / name
    if not path.is_file():
        raise RunError(f"{name} not found in {run_dir}: {hint}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunError(f"{name} in {run_dir} is not valid JSON ({error.msg})")


def optional_json(run_dir: Path, name: str, default):
    path = Path(run_dir) / name
    return load_json(run_dir, name, "") if path.is_file() else default


def load_trip(run_dir: Path) -> dict:
    trip = load_json(run_dir, TRIP, "start the run with ledger.py init")
    errors = ledger.validate_trip(trip)
    if errors:
        raise RunError(f"{TRIP}: " + "; ".join(errors))
    return trip


def load_merged(run_dir: Path) -> list:
    path = Path(run_dir) / MERGED
    if not path.is_file():
        raise RunError(f"{MERGED} not found in {run_dir}: run merge_candidates.py first")
    return read_jsonl(path)


def read_numbers(run_dir: Path) -> dict:
    return optional_json(run_dir, NUMBERS, {"numbers": {}, "next": 1})


def read_checkpoints(run_dir: Path) -> list:
    return optional_json(run_dir, CHECKPOINTS, {"checkpoints": []})["checkpoints"]


def active_strikes(checkpoints: list) -> dict:
    """id -> strike record for every strike still in force (R24).

    A strike stays in force until a later reply changes the dates, the budget or
    the dog answer; a strike made in the same reply as a change stays in force.
    """
    active: dict = {}
    for i, checkpoint in enumerate(checkpoints):
        released = any(later.get("change") for later in checkpoints[i + 1:])
        for strike in checkpoint.get("strikes", []):
            if released:
                active.pop(strike["id"], None)
            else:
                active[strike["id"]] = dict(strike, checkpoint=checkpoint["n"])
    return active


def run_cli(main, argv: list) -> int:
    try:
        return main(argv)
    except RunError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
