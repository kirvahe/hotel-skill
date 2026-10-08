#!/usr/bin/env python3
"""Check that a migrated taste profile or booking history kept every hotel row and rating.

Usage:
    python3 migrate_check.py ORIGINAL.md MIGRATED.md

Reads every markdown table in both files. In each table it finds the hotel
column (header "Hotel" or "Отель") and, when present, the rating column
(header "Rating" or "Оценка"). Every (hotel, rating) pair in the original must
appear in the migrated file the same number of times, with both cells
character for character. Ratings are never normalized: "5-6 (7 для Примерска)"
must stay exactly that.

Exit code 0 and "OK" when nothing is missing; exit code 1 and a list of
missing rows otherwise; exit code 2 when a file cannot be read.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HOTEL_HEADERS = {"hotel", "отель"}
RATING_HEADERS = {"rating", "оценка"}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(cell and set(cell) <= set("-: ") for cell in cells)


def table_rows(text: str) -> Counter:
    """Return a Counter of (hotel, rating) pairs from every hotel table in text.

    Rating is "" for tables without a rating column.
    """
    pairs: Counter = Counter()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if line.lstrip().startswith("|") and next_line.lstrip().startswith("|") and _is_separator(_cells(next_line)):
            header = [cell.lower() for cell in _cells(line)]
            hotel_col = next((n for n, cell in enumerate(header) if cell in HOTEL_HEADERS), None)
            rating_col = next((n for n, cell in enumerate(header) if cell in RATING_HEADERS), None)
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = _cells(lines[i])
                if hotel_col is not None and hotel_col < len(cells):
                    rating = cells[rating_col] if rating_col is not None and rating_col < len(cells) else ""
                    pairs[(cells[hotel_col], rating)] += 1
                i += 1
            continue
        i += 1
    return pairs


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    try:
        original = Path(argv[1]).read_text(encoding="utf-8")
        migrated = Path(argv[2]).read_text(encoding="utf-8")
    except OSError as error:
        print(f"Cannot read input: {error}")
        return 2

    expected = table_rows(original)
    found = table_rows(migrated)
    missing = expected - found
    if not missing:
        print(f"OK: all {sum(expected.values())} hotel rows and ratings are present.")
        return 0

    print(f"MISSING {sum(missing.values())} of {sum(expected.values())} hotel rows:")
    for (hotel, rating), count in sorted(missing.items()):
        rating_text = f" | rating {rating!r}" if rating else ""
        times = f" (x{count})" if count > 1 else ""
        print(f"  - {hotel}{rating_text}{times}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
