#!/usr/bin/env python3
"""Apply the user's numbered reply at the shortlist checkpoint (R15, R24).

Usage:
    python3 apply_reply.py RUN_DIR REPLY_FILE     (REPLY_FILE "-" reads stdin)

The model turns the user's reply into JSON, with either part optional:
    {"strike": [{"number": 3, "reason": "too far out"}, 5],
     "change": {"check_in": "YYYY-MM-DD", "check_out": "YYYY-MM-DD", "budget_max": 300, "dog": true}}

Numbers are the stable entry numbers from render.py (numbers.json); a reply that
only changes something needs none, as after "Nothing fits" (F2). Each reply
is saved as one checkpoint in checkpoints.json, strike-outs with their reasons.
A change updates trip.json and re-runs fit_filter and status_table on the saved
candidates, without new research. Strike-outs from earlier checkpoints are
released by a change and go through the checks again, so they can return;
strike-outs in the same reply as the change stay struck.

When the dates change, the evidence on file is for the old dates, so most hotels
fall to unknown until the availability reader runs for the new dates:
"needs_availability_check" is true and "to_check" lists the hotels to read
before running status_table.py again (kept, not struck, not already closed on
the new dates).

Prints the result as JSON. Nothing is saved when the reply is invalid (exit 2).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import fit_filter
import ledger
import runfiles
import status_table

CHANGE_KEYS = ("check_in", "check_out", "budget_max", "dog")


def _strikes(reply: dict, numbers: dict, names: dict) -> list:
    by_number = {n: cid for cid, n in numbers.items()}
    out = []
    for item in reply.get("strike") or []:
        number, reason = (item, "") if isinstance(item, int) else (item.get("number"), item.get("reason") or "")
        if number not in by_number:
            raise runfiles.RunError(f"no entry number {number} in this run")
        cid = by_number[number]
        out.append({"id": cid, "name": names.get(cid, cid), "number": number, "reason": reason})
    return out


def _new_trip(trip: dict, change: dict) -> dict:
    unknown = sorted(set(change) - set(CHANGE_KEYS))
    if unknown:
        raise runfiles.RunError(f"unknown change {unknown}; a change may set {', '.join(CHANGE_KEYS)}")
    new = copy.deepcopy(trip)
    for key in ("check_in", "check_out", "dog"):
        if key in change:
            new[key] = change[key]
    if "budget_max" in change:
        new["budget"]["max"] = change["budget_max"]
    errors = ledger.validate_trip(new)
    if errors:
        raise runfiles.RunError("the change makes trip.json invalid: " + "; ".join(errors))
    return new


def apply(run_dir: Path, reply: dict) -> dict:
    run_dir = Path(run_dir)
    if not isinstance(reply, dict) or set(reply) - {"strike", "change"}:
        raise runfiles.RunError('a reply is {"strike": [...], "change": {...}}')
    trip = runfiles.load_trip(run_dir)
    numbers = runfiles.read_numbers(run_dir)["numbers"]
    # A change-only reply needs no entry numbers: after "nothing fits" no shortlist was ever numbered (F2).
    if reply.get("strike") and not numbers:
        raise runfiles.RunError("numbers.json not found or empty: render the shortlist first")
    names = {c["id"]: c["name"] for c in runfiles.load_merged(run_dir)}
    strikes = _strikes(reply, numbers, names)
    change = {k: v for k, v in (reply.get("change") or {}).items() if v is not None}
    new_trip = _new_trip(trip, change) if change else trip

    checkpoints = runfiles.read_checkpoints(run_dir)
    before = runfiles.active_strikes(checkpoints)
    record = {"n": len(checkpoints) + 1, "at": ledger.now(), "strikes": strikes, "change": change}
    checkpoints.append(record)
    after = runfiles.active_strikes(checkpoints)
    runfiles.write_json(run_dir / runfiles.CHECKPOINTS, {"checkpoints": checkpoints})

    dates_changed = (new_trip["check_in"], new_trip["check_out"]) != (trip["check_in"], trip["check_out"])
    to_check = []
    if change:
        runfiles.write_json(run_dir / runfiles.TRIP, new_trip)
        fit = fit_filter.filter_run(run_dir)
        status = status_table.status_run(run_dir)["candidates"]
        if dates_changed:
            to_check = [c["name"] for c in runfiles.kept_hotels(fit, after)
                        if status[c["id"]]["reason"] != "closure"]
    return {
        "checkpoint": record["n"],
        "struck": strikes,
        "released": [s for cid, s in before.items() if cid not in after],
        "changed": change,
        "rerun": ["fit_filter", "status_table"] if change else [],
        "needs_availability_check": dates_changed,
        "to_check": to_check,
    }


def read_reply(arg: str):
    """The reply JSON from the file arg, or from stdin when arg is "-"."""
    text = sys.stdin.read() if arg == "-" else Path(arg).expanduser().read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise runfiles.RunError(f"the reply is not valid JSON ({error.msg})")


def main(argv: list) -> int:
    if len(argv) != 3:
        print("Usage: python3 apply_reply.py RUN_DIR REPLY_FILE", file=sys.stderr)
        return 2
    reply = read_reply(argv[2])
    print(json.dumps(apply(Path(argv[1]).expanduser(), reply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
