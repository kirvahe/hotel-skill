#!/usr/bin/env python3
"""The run ledger: one folder per find-hotel run, shared by every stage.

Layout (inside the user's data folder):
    trips/{city-slug}-{YYYY-MM}/run/
        trip.json                  trip parameters (city, dates, guests, budget, dog)
        candidates-{family}.jsonl  one candidate record per line, one file per research family
        envelope-{family}.json     the family agent's status report
        evidence.jsonl             availability, closure, pet and scarcity evidence
        state.json                 current stage, agents still running, history
        (later stages add more files; bin/runfiles.py lists them all)

Usage:
    python3 ledger.py init --data DIR --city NAME --check-in YYYY-MM-DD --check-out YYYY-MM-DD
                           --guests N --budget-min EUR --budget-max EUR --dog yes|no
    python3 ledger.py validate FILE --kind candidate|evidence|trip|envelope|state|resolved|final|gmail
    python3 ledger.py state RUN_DIR [--set STAGE] [--waiting fam1,fam2]
    python3 ledger.py slug "City name"

validate exits 1 and prints "line N: problem" for every invalid record.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

FAMILIES = ("curated-press", "reddit", "booking-search")
KINDS = ("hotel", "special-format", "apartment", "bnb", "hostal", "guesthouse")
STAGES = ("intake", "context", "research", "filter", "availability", "shortlist", "final", "answer", "done")
EVIDENCE_KINDS = ("engine_price", "engine_no_rooms", "engine_unreadable", "closure", "pet_policy", "scarcity")
ENGINE_KINDS = ("engine_price", "engine_no_rooms")
PRICE_BASES = ("per_night", "unknown")
PET_EVIDENCE_VALUES = ("allowed", "not allowed", "restricted", "hotel-level only")
VERDICTS = ("pass", "fail")
OTA_DOMAINS = ("booking.com", "airbnb.")
BANNED_DOMAINS = ("tripadvisor.", "yelp.", "instagram.com")
REDDIT_PERMALINK = re.compile(r"reddit\.com/r/[^/]+/comments/[^/]+")
CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def city_slug(name: str) -> str:
    """Lowercase ASCII slug: accents stripped, Cyrillic transliterated, spaces to hyphens."""
    text = "".join(CYRILLIC.get(ch, ch) for ch in name.strip().lower())
    text = text.replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def is_date(value) -> bool:
    """True when value is a YYYY-MM-DD date."""
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _source_errors(obj: dict, where: str) -> list[str]:
    errors = []
    url = str(obj.get("source_url") or obj.get("url") or "")
    if not url:
        errors.append(f"{where}: no source url")
    if not obj.get("quote"):
        errors.append(f"{where}: no quote")
    if any(domain in url.lower() for domain in BANNED_DOMAINS):
        errors.append(f"{where}: banned source {url}")
    return errors


def validate_candidate(record: dict) -> list[str]:
    errors = []
    if not record.get("name"):
        errors.append("no name")
    if record.get("kind") not in KINDS:
        errors.append(f"kind must be one of {', '.join(KINDS)}")
    mentions = record.get("mentions") or []
    if not mentions:
        errors.append("no source: a candidate needs at least one mention")
    for n, mention in enumerate(mentions, 1):
        where = f"mention {n}"
        errors += _source_errors(mention, where)
        if mention.get("family") not in FAMILIES:
            errors.append(f"{where}: family must be one of {', '.join(FAMILIES)}")
        if mention.get("family") == "reddit" and not REDDIT_PERMALINK.search(str(mention.get("url", ""))):
            errors.append(f"{where}: a Reddit mention needs the permalink of the thread or comment that was read")
    for field in ("rooms", "booking_score", "pet_policy"):
        if record.get(field):
            errors += _source_errors(record[field], field)
    for n, signal in enumerate(record.get("closure_signals") or [], 1):
        errors += _source_errors(signal, f"closure signal {n}")
    return errors


def validate_evidence(record: dict) -> list[str]:
    errors = []
    if not record.get("candidate"):
        errors.append("no candidate name")
    if record.get("kind") not in EVIDENCE_KINDS:
        errors.append(f"kind must be one of {', '.join(EVIDENCE_KINDS)}")
    errors += _source_errors(record, "evidence")
    if not record.get("read_at"):
        errors.append("no read_at time")
    if record.get("kind") in ENGINE_KINDS:
        shown = record.get("dates_shown") or {}
        if not (is_date(shown.get("check_in")) and is_date(shown.get("check_out"))):
            errors.append("engine evidence needs dates_shown.check_in and dates_shown.check_out")
    if record.get("kind") == "engine_price" and not isinstance(record.get("price_eur"), (int, float)):
        errors.append("engine_price needs a numeric price_eur")
    if "price_basis" in record and record["price_basis"] not in PRICE_BASES:
        errors.append(f"price_basis must be one of {', '.join(PRICE_BASES)}")
    if record.get("kind") == "pet_policy":
        if record.get("value") not in PET_EVIDENCE_VALUES:
            errors.append(f"pet_policy value must be one of {', '.join(PET_EVIDENCE_VALUES)}")
        if "room_types" in record and not (isinstance(record["room_types"], list)
                                           and all(isinstance(r, str) for r in record["room_types"])):
            errors.append("room_types must be a list of room-type names")
    return errors


def validate_resolved(record: dict) -> list[str]:
    """One line of resolved-{batch}.jsonl: the resolver's official site and judgment calls."""
    errors = [] if record.get("candidate") else ["no candidate name"]
    official = record.get("official_url")
    if official is not None:
        if not isinstance(official, dict) or not str(official.get("value", "")).startswith(("http://", "https://")):
            errors.append("official_url must be null or {value: an http(s) URL, source_url, quote}")
        else:
            errors += _source_errors(official, "official_url")
            if any(domain in official["value"].lower() for domain in OTA_DOMAINS):
                errors.append("official_url: a Booking or Airbnb page is not the hotel's own site")
    judgments = record.get("judgments", [])
    if not isinstance(judgments, list):
        return errors + ["judgments must be a list"]
    for n, judgment in enumerate(judgments, 1):
        where = f"judgment {n}"
        if not judgment.get("rule"):
            errors.append(f"{where}: no rule")
        if judgment.get("verdict") not in VERDICTS:
            errors.append(f"{where}: verdict must be pass or fail")
        if not judgment.get("reason"):
            errors.append(f"{where}: no reason")
        if judgment.get("verdict") == "fail":
            errors += _source_errors(judgment, f"{where} (a fail needs a quoted source)")
    return errors


def validate_final(record: dict) -> list[str]:
    """One line of final-{batch}.jsonl: the rate the final check priced and its cancellation terms."""
    errors = [] if record.get("candidate") else ["no candidate name"]
    for field in ("room_type", "rate"):
        if field in record and not isinstance(record[field], str):
            errors.append(f"{field} must be text")
    cancellation = record.get("cancellation")
    if cancellation is not None:
        if not isinstance(cancellation, dict) or not cancellation.get("value"):
            errors.append("cancellation must be {value, deadline, source_url, quote}")
        else:
            if cancellation["value"] != "unknown":
                errors += _source_errors(cancellation, "cancellation")
            if cancellation.get("deadline") and not is_date(cancellation["deadline"]):
                errors.append("cancellation deadline must be YYYY-MM-DD")
    return errors


def validate_gmail(record: dict) -> list[str]:
    """gmail-bookings.json: Booking confirmations the read-only Gmail agent found."""
    errors = []
    if record.get("status") not in ("complete", "partial", "failed"):
        errors.append("status must be complete, partial or failed")
    elif record["status"] != "complete" and not record.get("reason"):
        errors.append("reason is required for partial and failed")
    bookings = record.get("bookings")
    if not isinstance(bookings, list):
        return errors + ["bookings must be a list"]
    for n, booking in enumerate(bookings, 1):
        if not booking.get("hotel"):
            errors.append(f"booking {n}: no hotel")
        if not is_date(booking.get("check_in")):
            errors.append(f"booking {n}: check_in must be YYYY-MM-DD")
        if booking.get("check_out") and not is_date(booking["check_out"]):
            errors.append(f"booking {n}: check_out must be YYYY-MM-DD")
    return errors


def validate_trip(record: dict) -> list[str]:
    errors = []
    for field in ("city", "city_slug"):
        if not record.get(field):
            errors.append(f"no {field}")
    if not (is_date(record.get("check_in")) and is_date(record.get("check_out"))):
        errors.append("check_in and check_out must be YYYY-MM-DD")
    elif record["check_out"] <= record["check_in"]:
        errors.append("check_out must be after check_in")
    if not isinstance(record.get("guests"), int) or record["guests"] < 1:
        errors.append("guests must be a positive integer")
    budget = record.get("budget") or {}
    if budget.get("currency") != "EUR" or not isinstance(budget.get("max"), (int, float)):
        errors.append("budget needs a numeric max in EUR")
    if not isinstance(record.get("dog"), bool):
        errors.append("dog must be true or false")
    return errors


def validate_envelope(record: dict) -> list[str]:
    errors = []
    if record.get("family") not in FAMILIES:
        errors.append(f"family must be one of {', '.join(FAMILIES)}")
    if record.get("status") not in ("complete", "partial", "failed"):
        errors.append("status must be complete, partial or failed")
    return errors


def validate_state(record: dict) -> list[str]:
    return [] if record.get("stage") in STAGES else [f"stage must be one of {', '.join(STAGES)}"]


VALIDATORS = {
    "candidate": validate_candidate,
    "evidence": validate_evidence,
    "trip": validate_trip,
    "envelope": validate_envelope,
    "state": validate_state,
    "resolved": validate_resolved,
    "final": validate_final,
    "gmail": validate_gmail,
}


def now() -> str:
    """The current UTC time, to the second, as the ledger records it."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_now = now


def init_run(data_dir: Path, *, city: str, check_in: str, check_out: str, guests: int,
             budget_min: float, budget_max: float, dog: bool) -> Path:
    slug = city_slug(city)
    run_dir = Path(data_dir) / "trips" / f"{slug}-{check_in[:7]}" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    trip = {
        "city": city, "city_slug": slug, "check_in": check_in, "check_out": check_out,
        "guests": guests, "budget": {"min": budget_min, "max": budget_max, "currency": "EUR"},
        "dog": dog, "created": now(),
    }
    errors = validate_trip(trip)
    if errors:
        raise ValueError("; ".join(errors))
    (run_dir / "trip.json").write_text(json.dumps(trip, ensure_ascii=False, indent=2), encoding="utf-8")
    write_state(run_dir, stage="intake", waiting_for=[])
    return run_dir


def read_state(run_dir: Path) -> dict:
    path = Path(run_dir) / "state.json"
    if not path.is_file():
        return {"stage": "intake", "waiting_for": [], "history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(run_dir: Path, *, stage: str, waiting_for: list) -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    state = read_state(run_dir)
    state.update({"stage": stage, "waiting_for": list(waiting_for), "updated": now()})
    state.setdefault("history", []).append({"stage": stage, "at": state["updated"]})
    (Path(run_dir) / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def read_records(path: Path, kind: str, label: str | None = None) -> tuple[list, list]:
    """(valid records, rejected lines) of a .jsonl file, checked against the ledger kind.

    A rejected line is {"line": N, "problems": [...]}: not valid JSON, not a JSON object, or the
    kind's validation problems. When the line is an object, it also carries the record's `label`
    field (e.g. "candidate" or "name"), so the report can say which hotel it was about.
    """
    validator = VALIDATORS[kind]
    records, rejected = [], []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            rejected.append({"line": n, "problems": [f"not valid JSON ({error.msg})"]})
            continue
        if not isinstance(record, dict):
            rejected.append({"line": n, "problems": ["not a JSON object"]})
            continue
        problems = validator(record)
        if problems:
            labelled = {label: record.get(label, "")} if label else {}
            rejected.append({"line": n, **labelled, "problems": problems})
        else:
            records.append(record)
    return records, rejected


def validate_file(path: Path, kind: str) -> list[str]:
    """Problems as 'line N: ...' for .jsonl files, or plain messages for .json files."""
    if path.suffix == ".jsonl":
        _, rejected = read_records(path, kind)
        return [f"line {r['line']}: {problem}" for r in rejected for problem in r["problems"]]
    return VALIDATORS[kind](json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="find-hotel run ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--data", required=True)
    p_init.add_argument("--city", required=True)
    p_init.add_argument("--check-in", required=True)
    p_init.add_argument("--check-out", required=True)
    p_init.add_argument("--guests", type=int, required=True)
    p_init.add_argument("--budget-min", type=float, default=0)
    p_init.add_argument("--budget-max", type=float, required=True)
    p_init.add_argument("--dog", choices=("yes", "no"), required=True)
    p_val = sub.add_parser("validate")
    p_val.add_argument("file")
    p_val.add_argument("--kind", choices=sorted(VALIDATORS), required=True)
    p_state = sub.add_parser("state")
    p_state.add_argument("run_dir")
    p_state.add_argument("--set", dest="stage")
    p_state.add_argument("--waiting", default="")
    p_slug = sub.add_parser("slug")
    p_slug.add_argument("name")
    args = parser.parse_args(argv[1:])

    if args.cmd == "slug":
        print(city_slug(args.name))
        return 0
    if args.cmd == "init":
        run_dir = init_run(Path(args.data).expanduser(), city=args.city, check_in=args.check_in,
                           check_out=args.check_out, guests=args.guests, budget_min=args.budget_min,
                           budget_max=args.budget_max, dog=args.dog == "yes")
        print(run_dir)
        return 0
    if args.cmd == "validate":
        problems = validate_file(Path(args.file).expanduser(), args.kind)
        if problems:
            print("\n".join(problems))
            return 1
        print("OK")
        return 0
    if args.cmd == "state":
        run_dir = Path(args.run_dir).expanduser()
        if args.stage:
            waiting = [w for w in args.waiting.split(",") if w]
            print(json.dumps(write_state(run_dir, stage=args.stage, waiting_for=waiting), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(read_state(run_dir), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
