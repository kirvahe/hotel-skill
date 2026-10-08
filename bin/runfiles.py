#!/usr/bin/env python3
"""Shared helpers for the find-hotel pipeline scripts. Not a pipeline step of its own.

Holds the hotel name key that every script matches names with, the run-folder
file readers, and the checkpoint records that render.py and apply_reply.py share.

Files the pipeline adds to the run folder (see ledger.py for the rest):
    merged.jsonl          merge_candidates.py   one record per hotel, all families merged
    merge-decisions.json  the model            {"same": [["Name A", "Name B"], ...]} for close pairs
    fit-rules.json        the model            {"floor", "limited_choice", "do_not_recommend", "excluded_kinds"}
    blacklist.json        blacklist.py output, saved as is
    stays.json            stays.py output, saved as is
    fit.json              fit_filter.py        keep / remove per candidate, reason code, flags, past stays
    status.json           status_table.py      available / unavailable / unknown per candidate
    verdicts.json         the model            {"clearly_better": [{"candidate", "reason"}]} (R25)
    numbers.json          render.py            stable entry numbers {"numbers": {id: n}, "next": n}
    checkpoints.json      apply_reply.py       strike-outs and changes, one record per reply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ledger

# Words dropped from a name key, so "Hotel Casa Velarta" and "Casa Velarta" match.
GENERIC_WORDS = ("hotel",)


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
    trip = load_json(run_dir, "trip.json", "start the run with ledger.py init")
    errors = ledger.validate_trip(trip)
    if errors:
        raise RunError("trip.json: " + "; ".join(errors))
    return trip


def load_merged(run_dir: Path) -> list:
    path = Path(run_dir) / "merged.jsonl"
    if not path.is_file():
        raise RunError(f"merged.jsonl not found in {run_dir}: run merge_candidates.py first")
    return read_jsonl(path)


def read_numbers(run_dir: Path) -> dict:
    return optional_json(run_dir, "numbers.json", {"numbers": {}, "next": 1})


def read_checkpoints(run_dir: Path) -> list:
    return optional_json(run_dir, "checkpoints.json", {"checkpoints": []})["checkpoints"]


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
