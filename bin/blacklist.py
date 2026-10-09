#!/usr/bin/env python3
"""Read every city feedback file into one blacklist for the fit filter.

Usage:
    python3 blacklist.py FEEDBACK_DIR

Reads each feedback_*_hotels.md file in FEEDBACK_DIR (pass the data path
itself, e.g. ~/.claude/skills/hotel/data/feedback, so a linked data folder is
followed). From each file it takes the rows of the "## Blacklist" table (the
heading may carry a suffix such as "(do not recommend)"); "Positive
reference" rows are never blacklisted.

Prints JSON:
    {"blacklist": [{"hotel", "city", "reason", "source", "file"}, ...],
     "skipped": [{"file", "why"}, ...],
     "note": "..."}

A file without a blacklist table is listed under "skipped", never silently
ignored. A missing folder is an empty result with a note, not an error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _city_of(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.lower().startswith("city:"):
                return line.split(":", 1)[1].strip()
    for line in lines:
        if line.startswith("# "):
            return line[2:].split(" — ")[0].strip()
    return ""


def parse_file(path: Path) -> tuple[list[dict], str | None]:
    """Return (blacklist rows, skip reason or None)."""
    text = path.read_text(encoding="utf-8")
    city = _city_of(text)
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.lower().startswith("## blacklist")), None)
    if start is None:
        return [], "no '## Blacklist' table"

    rows: list[dict] = []
    header: list[str] | None = None
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if header is None:
            header = [cell.lower() for cell in cells]
            continue
        if all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        record = dict(zip(header, cells))
        hotel = record.get("hotel", "")
        if hotel:
            rows.append({
                "hotel": hotel,
                "city": city,
                "reason": record.get("reason", ""),
                "source": record.get("source", ""),
                "file": path.name,
            })
    if header is None:
        return [], "'## Blacklist' heading without a table"
    return rows, None


def read_folder(folder: Path) -> tuple[list[dict], list[dict], int]:
    """(blacklist rows, skipped files as {"file", "why"}, files read) for every feedback file in folder."""
    rows: list[dict] = []
    skipped: list[dict] = []
    files = sorted(Path(folder).glob("feedback_*_hotels.md"))
    for path in files:
        found, skip = parse_file(path)
        if skip:
            skipped.append({"file": path.name, "why": skip})
        rows.extend(found)
    return rows, skipped, len(files)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python3 blacklist.py FEEDBACK_DIR", file=sys.stderr)
        return 2
    folder = Path(argv[1]).expanduser()
    result: dict = {"blacklist": [], "skipped": [], "note": ""}
    if not folder.is_dir():
        result["note"] = f"feedback folder not found: {folder}; no blacklist applied"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result["blacklist"], result["skipped"], files = read_folder(folder)
    result["note"] = f"read {files} file(s), {len(result['blacklist'])} blacklisted hotel(s)"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
