#!/usr/bin/env python3
"""Merge every research family's candidates into one file: RUN_DIR/merged.jsonl.

Usage:
    python3 merge_candidates.py RUN_DIR

Reads RUN_DIR/candidates-*.jsonl (curated-press first, then reddit, then
booking-search, so merged names and the merge order favour trusted sources).
Every line goes through ledger.py's candidate validation; a rejected line is
reported with its file and line number and left out (KTD3, R4).

Records merge when they share a name key within a city: "Hotel" dropped,
accents, case and punctuation ignored, and the local name counts as a name.
Pairs where one name's words are a strict subset of the other's ("Patio Lunar"
and "El Patio Lunar") are not merged: they are reported as close calls. The
model resolves a close call by adding the pair to RUN_DIR/merge-decisions.json
as {"same": [["Patio Lunar", "El Patio Lunar"]]} and running the merge again.

Each merged record carries:
    booking_only  true when every mention is from the booking-search family (R8)
    score         {"value", "verified", "why"}: verified only when at least one
                  Booking score was found and every score found has the same value;
                  any difference counts (R23). Review counts are not compared.
    booking_url   the research's booking_url, else the first booking.com/hotel/ mention URL
    pet_policy    {"value": "allowed" | "not allowed" | "restricted" | "unknown", "quotes"};
                  sources that disagree make it "unknown"
    flags         "booking_only", "score_unverified"

Prints a JSON report: merged count, files read, rejected lines, close calls and
records whose sources disagree on the kind. Exit 0; exit 2 on a missing trip.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import ledger
import runfiles

FAMILY_ORDER = ("curated-press", "reddit", "booking-search")
PET_VALUES = {"allowed": "allowed", "yes": "allowed", "not allowed": "not allowed", "no": "not allowed",
              "restricted": "restricted"}


def _family_rank(path: Path) -> tuple:
    family = path.stem[len("candidates-"):]
    return (FAMILY_ORDER.index(family) if family in FAMILY_ORDER else len(FAMILY_ORDER), path.name)


def read_candidates(run_dir: Path) -> tuple[list, list, list]:
    """Return (valid records in order, rejected lines, file names read)."""
    records, rejected, files = [], [], []
    for path in sorted(Path(run_dir).glob("candidates-*.jsonl"), key=_family_rank):
        files.append(path.name)
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                rejected.append({"file": path.name, "line": n, "problems": [f"not valid JSON ({error.msg})"]})
                continue
            problems = ledger.validate_candidate(record) if isinstance(record, dict) else ["not a JSON object"]
            if problems:
                rejected.append({"file": path.name, "line": n, "name": record.get("name", ""), "problems": problems})
            else:
                records.append(record)
    return records, rejected, files


def _parse_score(value):
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def score_summary(scores: list) -> dict:
    if not scores:
        return {"value": None, "verified": False, "why": "no Booking score found"}
    raw = list(dict.fromkeys(str(s.get("value", "")).strip() for s in scores))
    values = [_parse_score(s.get("value")) for s in scores]
    if None in values:
        return {"value": None, "verified": False, "why": "unreadable Booking score: " + ", ".join(raw)}
    if len(set(values)) > 1:
        return {"value": None, "verified": False, "why": "sources disagree: " + ", ".join(raw)}
    return {"value": values[0], "verified": True, "why": ""}


def pet_summary(policies: list) -> dict:
    values = {PET_VALUES.get(str(p.get("value", "")).strip().lower().replace("_", " ").replace("-", " "))
              for p in policies}
    value = values.pop() if len(values) == 1 and None not in values else "unknown"
    return {"value": value, "quotes": [p.get("quote", "") for p in policies]}


class _Groups:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _read_decisions(run_dir: Path) -> list:
    decisions = runfiles.optional_json(run_dir, "merge-decisions.json", {"same": []})
    pairs = decisions.get("same", []) if isinstance(decisions, dict) else None
    if not isinstance(pairs, list) or not all(isinstance(p, list) and len(p) == 2 for p in pairs):
        raise runfiles.RunError('merge-decisions.json must be {"same": [["Name A", "Name B"], ...]}')
    return pairs


def _build(group: list, city: str) -> dict:
    first = group[0]
    aliases = list(dict.fromkeys(n for r in group for n in (r.get("name"), r.get("local_name")) if n))
    mentions, seen = [], set()
    for record in group:
        for mention in record.get("mentions", []):
            key = (mention.get("url"), mention.get("quote"))
            if key not in seen:
                seen.add(key)
                mentions.append(mention)

    def first_value(field):
        return next((r[field] for r in group if r.get(field)), "")

    score = score_summary([r["booking_score"] for r in group if r.get("booking_score")])
    booking_only = all(m.get("family") == "booking-search" for m in mentions)
    flags = (["booking_only"] if booking_only else []) + ([] if score["verified"] else ["score_unverified"])
    return {
        "name": first["name"],
        "aliases": aliases,
        "local_name": first_value("local_name"),
        "kind": first["kind"],
        "city": first.get("city") or city,
        "area": first_value("area"),
        "street": first_value("street"),
        "official_url": first_value("official_url"),
        "booking_url": first_value("booking_url") or next(
            (m["url"] for m in mentions if re.match(r"https?://([a-z0-9-]+\.)*booking\.com/hotel/", m.get("url", ""))), ""),
        "rooms": first_value("rooms") or None,
        "mentions": mentions,
        "booking_scores": [r["booking_score"] for r in group if r.get("booking_score")],
        "score": score,
        "pet_policy": pet_summary([r["pet_policy"] for r in group if r.get("pet_policy")]),
        "closure_signals": [s for r in group for s in (r.get("closure_signals") or [])],
        "booking_only": booking_only,
        "flags": flags,
    }


def merge_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    records, rejected, files = read_candidates(run_dir)
    cities = [runfiles.city_key(r.get("city"), trip["city_slug"]) for r in records]
    keys = [{runfiles.name_key(n) for n in (r.get("name"), r.get("local_name")) if n} for r in records]

    groups = _Groups(len(records))
    first_with: dict = {}
    for i, (city, record_keys) in enumerate(zip(cities, keys)):
        for key in record_keys:
            if (city, key) in first_with:
                groups.union(first_with[(city, key)], i)
            else:
                first_with[(city, key)] = i
    for a, b in _read_decisions(run_dir):
        ka, kb = runfiles.name_key(a), runfiles.name_key(b)
        for (city, key), i in list(first_with.items()):
            if key == ka and (city, kb) in first_with:
                groups.union(i, first_with[(city, kb)])

    members: dict = {}
    for i in range(len(records)):
        members.setdefault(groups.find(i), []).append(i)

    merged, used_ids, group_keys = [], set(), []
    kind_conflicts = []
    for root in sorted(members):
        idx = members[root]
        city = cities[idx[0]]
        record = _build([records[i] for i in idx], trip["city"])
        base = ledger.city_slug(runfiles.name_key(record["name"])) or "candidate"
        candidate_id = base if base not in used_ids else f"{base}-{city}"
        n = 2
        while candidate_id in used_ids:
            candidate_id, n = f"{base}-{city}-{n}", n + 1
        used_ids.add(candidate_id)
        merged.append(dict({"id": candidate_id}, **record))
        group_keys.append((city, set().union(*(keys[i] for i in idx)), record["name"]))
        kinds = list(dict.fromkeys(records[i]["kind"] for i in idx))
        if len(kinds) > 1:
            kind_conflicts.append({"name": record["name"], "kinds": kinds, "kept": record["kind"]})

    close_calls = []
    for i, (city_a, keys_a, name_a) in enumerate(group_keys):
        for city_b, keys_b, name_b in group_keys[i + 1:]:
            if city_a != city_b:
                continue
            words_a = [set(k.split()) for k in keys_a]
            words_b = [set(k.split()) for k in keys_b]
            if any(a < b or b < a for a in words_a for b in words_b):
                close_calls.append({"names": [name_a, name_b], "city": city_a,
                                    "why": "one name's words are contained in the other's"})

    runfiles.write_jsonl(run_dir / "merged.jsonl", merged)
    return {"merged": len(merged), "files": files, "rejected": rejected,
            "close_calls": close_calls, "kind_conflicts": kind_conflicts}


def main(argv: list) -> int:
    if len(argv) != 2:
        print("Usage: python3 merge_candidates.py RUN_DIR", file=sys.stderr)
        return 2
    report = merge_run(Path(argv[1]).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
