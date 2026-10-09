#!/usr/bin/env python3
"""Check a final answer against the run ledger before it reaches the user.

Usage:
    python3 check_output.py RUN_DIR ANSWER_FILE

Reads the numbered entries of the answer ("N. **Hotel name**" lines, as
render.py writes them; an entry runs until the next entry or heading) and
compares each with merged.jsonl, fit-rules.json and blacklist.json. Fails on:
    - an entry for a hotel the run ledger does not hold
    - a blacklisted hotel (same city, any name variant)
    - a verified Booking score below the floor outside a limited-choice city
    - a hotel entry without both a Booking link and a Google Maps link
    - an Airbnb entry (special format, or under an Airbnb heading) without
      "dates not verified" in any label language
    - a research family or optional module with no ran / partial / skipped / failed
      status in families.json or modules.json, or an answer without the checks
      report (R22)

"Skipped: ..." lines are not entries, so naming a blacklisted hotel there is fine.
Prints OK, or one "FAIL: ..." line per problem. Exit 0 when clean, 1 on any failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import fit_filter
import render
import runfiles

ENTRY = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")
BOOKING_LINK = re.compile(r"\]\(https?://([a-z0-9-]+\.)*booking\.com/[^)]*\)")
MAPS_LINK = re.compile(r"\]\(https?://(www\.)?google\.[a-z.]+/maps/[^)]*\)")
DATES_NOT_VERIFIED = tuple(labels["dates_not_verified"] for labels in render.LABELS.values())
REPORT_HEADINGS = tuple(f"### {labels['report']}" for labels in render.LABELS.values())


def report_failures(run_dir: Path, text: str) -> list:
    failures = []
    families = runfiles.optional_json(run_dir, runfiles.FAMILIES, {}).get("families") or {}
    modules = runfiles.optional_json(run_dir, runfiles.MODULES, {}).get("modules") or {}
    for kind, names, recorded in (("research family", render.FAMILIES, families),
                                  ("module", runfiles.MODULES_ORDER, modules)):
        for name in names:
            if (recorded.get(name) or {}).get("status") not in runfiles.STATUSES:
                failures.append(f"no status for {kind} {name} (R22)")
    if not any(line.strip() in REPORT_HEADINGS for line in text.splitlines()):
        failures.append("the answer has no checks report (R22)")
    return failures


def parse_entries(text: str) -> list:
    entries, section, current = [], "", None
    for line in text.splitlines():
        if line.startswith("#"):
            section, current = line.lstrip("#").strip(), None
            continue
        match = ENTRY.match(line)
        if match:
            current = {"number": int(match.group(1)), "name": match.group(2).strip(), "section": section, "body": line}
            entries.append(current)
        elif current is not None:
            current["body"] += "\n" + line
    return entries


def check(run_dir: Path, text: str) -> list:
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    merged = runfiles.load_merged(run_dir)
    rules = fit_filter.load_rules(run_dir)
    blacklist = runfiles.load_json(run_dir, "blacklist.json", "save the output of blacklist.py there")["blacklist"]
    floor = rules["floor"]
    failures = []
    for entry in parse_entries(text):
        name, key = entry["name"], runfiles.name_key(entry["name"])
        candidate = next((c for c in merged if key in runfiles.record_keys(c)), None)
        keys = runfiles.record_keys(candidate) if candidate else {key}
        city = runfiles.city_key(candidate.get("city") if candidate else "", trip["city_slug"])
        if candidate is None:
            failures.append(f"{name}: not in the run ledger")
        row = next((r for r in blacklist
                    if (not r.get("city") or runfiles.city_key(r["city"], "") == city)
                    and runfiles.name_key(r.get("hotel", "")) in keys), None)
        if row:
            failures.append(f"{name}: on the blacklist ({row.get('reason', '')})")
        is_airbnb = "airbnb" in entry["section"].lower() or (candidate or {}).get("kind") == "special-format"
        if is_airbnb:
            if not any(label in entry["body"] for label in DATES_NOT_VERIFIED):
                failures.append(f"{name}: Airbnb entry without \"dates not verified\"")
            continue
        if not BOOKING_LINK.search(entry["body"]):
            failures.append(f"{name}: no Booking link")
        if not MAPS_LINK.search(entry["body"]):
            failures.append(f"{name}: no Google Maps link")
        score = (candidate or {}).get("score") or {}
        if score.get("verified") and score["value"] < floor and not rules["limited_choice"]:
            failures.append(f"{name}: Booking {score['value']} is below the {float(floor)} floor "
                            "and this city is not limited-choice")
    return failures + report_failures(run_dir, text)


def main(argv: list) -> int:
    if len(argv) != 3:
        print("Usage: python3 check_output.py RUN_DIR ANSWER_FILE", file=sys.stderr)
        return 2
    failures = check(Path(argv[1]).expanduser(), Path(argv[2]).expanduser().read_text(encoding="utf-8"))
    print("\n".join(f"FAIL: {f}" for f in failures) if failures else "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
