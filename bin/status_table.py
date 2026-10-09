#!/usr/bin/env python3
"""Map availability evidence to a status per candidate: RUN_DIR/status.json (KTD4, R12).

Usage:
    python3 status_table.py RUN_DIR

Reads trip.json, merged.jsonl and evidence.jsonl (a missing evidence file means
no evidence). Every evidence line goes through ledger.py's evidence validation;
a rejected line counts as no evidence and is reported. Evidence is matched to a
candidate by name key, so "Hotel Casa Velarta" evidence reaches "Casa Velarta".

The decision table, for the nights [check_in, check_out):
    closure      a "closure" record with closed_from (first closed night) and/or
                 closed_until (last closed night, inclusive) that overlaps any night
    engine       "engine_price" / "engine_no_rooms" records whose dates_shown equal the
                 trip dates and that come from the hotel's own engine (a Booking or
                 Airbnb page is not); the latest read_at wins, a priced reading wins a tie

    closure overlaps and the engine prices the dates   -> unknown (reason "conflict")
    closure overlaps                                    -> unavailable
    engine prices the dates                             -> available, with price_eur
    engine says no rooms for the dates                  -> unavailable
    anything else (no evidence, unreadable engine,
    a closure without dates, other dates shown)         -> unknown

price_eur is the engine's price with its price_basis: "per_night", or "unknown" when the page
did not say whether it is per night or for the whole stay (a record without a basis is per night).
The budget split against it happens in render.py.
A "scarcity" record whose dates_shown equal the trip dates is attached as a quote.

Prints counts, rejected lines and unmatched evidence names as JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ledger
import runfiles


def _dates_match(record: dict, check_in: str, check_out: str) -> bool:
    shown = record.get("dates_shown") or {}
    return shown.get("check_in") == check_in and shown.get("check_out") == check_out


def _from_ota(record: dict) -> bool:
    url = str(record.get("source_url") or record.get("url") or "").lower()
    return any(host in url for host in ledger.OTA_DOMAINS)


def closure_overlaps(record: dict, check_in: str, check_out: str):
    """True or False, or None when the closure has no readable dates."""
    start, end = record.get("closed_from"), record.get("closed_until")
    if not (start or end):
        return None
    if any(value and not ledger.is_date(value) for value in (start, end)):
        return None
    return (not start or start < check_out) and (not end or end >= check_in)


def decide(evidence: list, trip: dict) -> dict:
    check_in, check_out = trip["check_in"], trip["check_out"]
    result = {"status": "unknown", "price_eur": None, "price_basis": None, "reason": "no_evidence",
              "quote": "", "source_url": "", "scarcity": None}
    result["scarcity"] = next((e.get("quote") for e in evidence
                               if e["kind"] == "scarcity" and _dates_match(e, check_in, check_out)), None)

    closures = [e for e in evidence if e["kind"] == "closure"]
    overlapping = [e for e in closures if closure_overlaps(e, check_in, check_out)]
    engine = [e for e in evidence if e["kind"] in ledger.ENGINE_KINDS and not _from_ota(e)]
    matching = [e for e in engine if _dates_match(e, check_in, check_out)]
    latest = max(matching, key=lambda e: (str(e["read_at"]), e["kind"] == "engine_price")) if matching else None

    def cite(record: dict) -> dict:
        return {"quote": record.get("quote", ""), "source_url": record.get("source_url") or record.get("url", "")}

    if overlapping and latest and latest["kind"] == "engine_price":
        result.update(status="unknown", reason="conflict", **cite(overlapping[0]))
    elif overlapping:
        result.update(status="unavailable", reason="closure", **cite(overlapping[0]))
    elif latest and latest["kind"] == "engine_price":
        result.update(status="available", reason="engine_price", price_eur=latest["price_eur"],
                      price_basis=latest.get("price_basis", "per_night"), **cite(latest))
    elif latest:
        result.update(status="unavailable", reason="engine_no_rooms", **cite(latest))
    elif engine:
        result.update(reason="dates_mismatch")
    elif any(e["kind"] == "engine_unreadable" for e in evidence) or any(
            closure_overlaps(e, check_in, check_out) is None for e in closures):
        result.update(reason="unreadable")
    return result


def read_evidence(run_dir: Path) -> tuple[list, list]:
    path = Path(run_dir) / runfiles.EVIDENCE
    if not path.is_file():
        return [], []
    return ledger.read_records(path, "evidence", label="candidate")


def status_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    merged = runfiles.load_merged(run_dir)
    evidence, rejected = read_evidence(run_dir)
    by_candidate, unmatched = runfiles.match_by_name(merged, evidence)

    candidates = {c["id"]: dict({"name": c["name"]}, **decide(by_candidate[c["id"]], trip)) for c in merged}
    counts = {status: sum(s["status"] == status for s in candidates.values())
              for status in ("available", "unavailable", "unknown")}
    out = {"trip_dates": {"check_in": trip["check_in"], "check_out": trip["check_out"]},
           "candidates": candidates, "counts": counts,
           "rejected": rejected, "unmatched": sorted(set(unmatched))}
    runfiles.write_json(run_dir / runfiles.STATUS, out)
    return out


def main(argv: list) -> int:
    if len(argv) != 2:
        print("Usage: python3 status_table.py RUN_DIR", file=sys.stderr)
        return 2
    out = status_run(Path(argv[1]).expanduser())
    print(json.dumps({key: out[key] for key in ("counts", "rejected", "unmatched")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
