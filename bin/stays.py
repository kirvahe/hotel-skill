#!/usr/bin/env python3
"""List every stay in booking-history.md: legacy tables and new H3 blocks alike.

Usage:
    python3 stays.py PATH/TO/booking-history.md

Legacy stays are rows of any table that has both a "Hotel" and a "Rating"
column (the per-year tables under "## Legacy stays"). New stays are H3 blocks
under "## Stays" with the header "### {Hotel} — {City}, {YYYY-MM-DD} — {Rating}/10"
(or "— Upcoming" for a booking not yet reviewed).

Each stay carries its comment (legacy tables) for revisits.
Ratings are returned exactly as written ("5-6 (7 для Примерска)" stays as is);
"rated" is false for "—", "?" or an empty cell, and for Upcoming blocks.

Prints JSON {"stays": [...], "counts": {...}}.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

H3_STAY = re.compile(r"^### (?P<hotel>.+?) — (?P<city>.+?), (?P<date>\d{4}-\d{2}-\d{2}) — (?P<rating>.+?)\s*$")
UNRATED = {"", "—", "-", "?"}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse(text: str) -> list[dict]:
    stays: list[dict] = []
    lines = text.splitlines()
    in_stays = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            in_stays = line.strip() == "## Stays" or line.startswith("## Stays ")
        match = H3_STAY.match(line) if in_stays else None
        if match:
            raw = match.group("rating")
            upcoming = raw.lower().startswith("upcoming")
            rating = raw[:-3] if raw.endswith("/10") else raw
            stays.append({
                "hotel": match.group("hotel").strip(),
                "city": match.group("city").strip(),
                "date": match.group("date"),
                "rating": "" if upcoming else rating.strip(),
                "comment": "",
                "rated": not upcoming and rating.strip() not in UNRATED,
                "upcoming": upcoming,
                "section": "stays",
            })
            i += 1
            continue
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if line.lstrip().startswith("|") and next_line.lstrip().startswith("|"):
            header = [cell.lower() for cell in _cells(line)]
            if "hotel" in header and "rating" in header:
                cols = {name: header.index(name) for name in ("hotel", "city", "dates", "rating", "comment") if name in header}
                i += 2
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    cells = _cells(lines[i])
                    get = lambda name: cells[cols[name]] if name in cols and cols[name] < len(cells) else ""
                    rating = get("rating")
                    stays.append({
                        "hotel": get("hotel"),
                        "city": get("city"),
                        "date": get("dates"),
                        "rating": rating,
                        "comment": get("comment"),
                        "rated": rating not in UNRATED,
                        "upcoming": False,
                        "section": "legacy",
                    })
                    i += 1
                continue
        i += 1
    return stays


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python3 stays.py PATH/TO/booking-history.md", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    if not path.is_file():
        print(json.dumps({"stays": [], "counts": {}, "note": f"not found: {path}"}, ensure_ascii=False))
        return 0
    stays = parse(path.read_text(encoding="utf-8"))
    counts = {
        "total": len(stays),
        "legacy": sum(s["section"] == "legacy" for s in stays),
        "stays": sum(s["section"] == "stays" for s in stays),
        "rated": sum(s["rated"] for s in stays),
        "upcoming": sum(s["upcoming"] for s in stays),
    }
    print(json.dumps({"stays": stays, "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
