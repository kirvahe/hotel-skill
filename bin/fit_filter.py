#!/usr/bin/env python3
"""Apply the profile's hard rules to the merged candidates: RUN_DIR/fit.json.

Usage:
    python3 fit_filter.py RUN_DIR

Reads from RUN_DIR:
    trip.json       the dog answer
    merged.jsonl    from merge_candidates.py
    fit-rules.json  written once per run by the model from the taste profile:
                    {"floor": 8.0, "limited_choice": false,
                     "do_not_recommend": ["Chain name", ...], "excluded_kinds": ["apartment", "bnb"]}
    blacklist.json  the output of blacklist.py, saved as is
    stays.json      the output of stays.py, saved as is

Checks, in this order; the first that fails removes the candidate with a reason
code and a "Skipped: ..." line:
    blacklist        a blacklist row for the same city (or with no city) names it
    excluded_kind    its kind is in excluded_kinds (apartments and B&Bs leave the list)
    dnr_chain        a do_not_recommend chain name appears as whole words in its name;
                     other chains pass (R10: the "chain with character" call is the model's)
    pet_not_allowed  the dog travels and its pet policy is "not allowed" (AE5);
                     an unknown policy keeps it with the "pet_unknown" flag
    below_floor      a verified Booking score below the floor; in a limited-choice city it
                     stays with the "below_floor" flag (R9). An unverified score never removes (R23).

Special formats (kind "special-format") go to the Airbnb block (R19): they skip
the chain and floor checks. Past stays in the same city attach their rating,
date and comment when stays.json has one (R10).

Prints the skip lines and counts as JSON. Exit 2 when an input is missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ledger
import runfiles

REASON_CODES = ("blacklist", "excluded_kind", "dnr_chain", "pet_not_allowed", "below_floor")
SKIP_TEXT = {
    "blacklist": "blacklist",
    "excluded_kind": "excluded kind",
    "dnr_chain": "do-not-recommend chain",
    "pet_not_allowed": "dogs not allowed",
    "below_floor": "below the {floor} floor",
}


def floor_text(floor) -> str:
    return str(float(floor))


def load_rules(run_dir: Path) -> dict:
    rules = runfiles.load_json(run_dir, "fit-rules.json",
                               "write it from the profile's hard rules first "
                               "(floor, limited_choice, do_not_recommend, excluded_kinds)")
    problems = []
    if isinstance(rules.get("floor"), bool) or not isinstance(rules.get("floor"), (int, float)):
        problems.append("floor must be a number")
    if not isinstance(rules.get("limited_choice"), bool):
        problems.append("limited_choice must be true or false")
    for field in ("do_not_recommend", "excluded_kinds"):
        value = rules.setdefault(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            problems.append(f"{field} must be a list of names")
    unknown = [k for k in rules.get("excluded_kinds") or [] if k not in ledger.KINDS]
    if unknown:
        problems.append(f"excluded_kinds has unknown kinds {unknown}; kinds are {', '.join(ledger.KINDS)}")
    if problems:
        raise runfiles.RunError("fit-rules.json: " + "; ".join(problems))
    return rules


def _chain_hit(names: list, chains: list):
    for chain in chains:
        words = runfiles.tokens(chain)
        for name in names:
            name_words = runfiles.tokens(name)
            if words and any(name_words[i:i + len(words)] == words
                             for i in range(len(name_words) - len(words) + 1)):
                return chain
    return None


def judge(candidate: dict, *, trip: dict, rules: dict, blacklist: list, stays: list) -> dict:
    keys = runfiles.record_keys(candidate)
    city = runfiles.city_key(candidate.get("city"), trip["city_slug"])

    def same_city(other) -> bool:
        return not other or ledger.city_slug(other) == city

    block = "airbnb" if candidate["kind"] == "special-format" else "hotels"
    flags = list(candidate.get("flags", []))
    past_stays = [
        {field: stay[field] for field in ("hotel", "city", "date", "rating", "comment") if stay.get(field)}
        for stay in stays
        if not stay.get("upcoming") and same_city(stay.get("city")) and runfiles.name_key(stay.get("hotel", "")) in keys
    ]
    floor = rules["floor"]
    removal = None
    hit = next((row for row in blacklist
                if same_city(row.get("city")) and runfiles.name_key(row.get("hotel", "")) in keys), None)
    chain = _chain_hit([candidate["name"]] + candidate.get("aliases", []), rules["do_not_recommend"])
    pet = candidate.get("pet_policy") or {"value": "unknown", "quotes": []}
    score = candidate.get("score") or {"verified": False, "value": None}
    below = score.get("verified") and score["value"] < floor

    if hit:
        removal = ("blacklist", hit.get("reason", ""))
    elif candidate["kind"] in rules["excluded_kinds"]:
        removal = ("excluded_kind", candidate["kind"])
    elif block == "hotels" and chain:
        removal = ("dnr_chain", chain)
    elif trip["dog"] and pet["value"] == "not allowed":
        removal = ("pet_not_allowed", "; ".join(q for q in pet["quotes"] if q))
    elif block == "hotels" and below and not rules["limited_choice"]:
        removal = ("below_floor", f"Booking {score['value']}")
    if not removal:
        if trip["dog"] and pet["value"] == "unknown":
            flags.append("pet_unknown")
        if block == "hotels" and below:
            flags.append("below_floor")

    result = {"id": candidate["id"], "name": candidate["name"], "block": block,
              "decision": "remove" if removal else "keep", "flags": flags,
              "reason_code": None, "reason": "", "skip_line": "", "past_stays": past_stays}
    if removal:
        code, detail = removal
        result.update(reason_code=code, reason=detail,
                      skip_line=f"Skipped: {SKIP_TEXT[code].format(floor=floor_text(floor))} — {candidate['name']} — {detail}")
    return result


def filter_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    merged = runfiles.load_merged(run_dir)
    rules = load_rules(run_dir)
    blacklist = runfiles.load_json(run_dir, "blacklist.json",
                                   "save the output of blacklist.py FEEDBACK_DIR there first")
    stays = runfiles.load_json(run_dir, "stays.json",
                               "save the output of stays.py booking-history.md there first")
    if not isinstance(blacklist.get("blacklist"), list) or not isinstance(stays.get("stays"), list):
        raise runfiles.RunError("blacklist.json and stays.json must be the outputs of blacklist.py and stays.py")

    results = [judge(c, trip=trip, rules=rules, blacklist=blacklist["blacklist"], stays=stays["stays"])
               for c in merged]
    out = {
        "trip": {key: trip[key] for key in ("city", "check_in", "check_out", "dog")},
        "rules": rules,
        "candidates": results,
        "skip_lines": [r["skip_line"] for r in results if r["skip_line"]],
        "counts": {"kept": sum(r["decision"] == "keep" for r in results),
                   "removed": sum(r["decision"] == "remove" for r in results)},
    }
    runfiles.write_json(run_dir / "fit.json", out)
    return out


def main(argv: list) -> int:
    if len(argv) != 2:
        print("Usage: python3 fit_filter.py RUN_DIR", file=sys.stderr)
        return 2
    out = filter_run(Path(argv[1]).expanduser())
    print(json.dumps({"skip_lines": out["skip_lines"], "counts": out["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
