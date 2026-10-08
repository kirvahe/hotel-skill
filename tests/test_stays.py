"""Tests for bin/stays.py: list every stay, legacy tables and new H3 blocks alike.

All data here is made up.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "stays.py"

HISTORY = """# Booking History

## Rating scale (1–10)

| Rating | Category | Meaning |
|---|---|---|
| 9–10 | Legend | Top |

## Legacy stays (2021–2026)

### 2025

| Hotel | City | Dates | Nights | Room | Price | Guests | Rating | Comment |
|---|---|---|---|---|---|---|---|---|
| Hotel Alpha | Testgrad | ~Dec 2025 | ? | ? | ? | ? | 7-8 | |
| Casa Beta | Primersk | ~May 2025 | ? | ? | ? | ? | 5-6 (7 для Примерска) | Meh |

### 2023

| Hotel | City | Dates | Nights | Room | Price | Guests | Rating | Comment |
|---|---|---|---|---|---|---|---|---|
| Casa Beta | Primersk | ~Mar 2023 | ? | ? | ? | ? | 5-6 (7 для Примерска) | Repeat |
| Hotel Gone | Nowhere | — | — | — | Cancelled | — | — | Cancelled |

## Stays

### Villa Delta — Ozersk, 2026-06-01 — 8.4/10

**Peak:** the terrace

### Hotel Echo — Testgrad, 2026-12-20 — Upcoming

**Notes:** Upcoming.
"""


def run(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "booking-history.md"
        path.write_text(text, encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
        return result, json.loads(result.stdout) if result.stdout else None


class StaysTest(unittest.TestCase):
    def test_counts_every_legacy_stay_and_new_block(self):
        result, out = run(HISTORY)
        self.assertEqual(result.returncode, 0, result.stderr)
        legacy = [s for s in out["stays"] if s["section"] == "legacy"]
        new = [s for s in out["stays"] if s["section"] == "stays"]
        self.assertEqual(len(legacy), 4)
        self.assertEqual(len(new), 2)

    def test_ratings_are_kept_as_written(self):
        result, out = run(HISTORY)
        beta = [s["rating"] for s in out["stays"] if s["hotel"] == "Casa Beta"]
        self.assertEqual(beta, ["5-6 (7 для Примерска)", "5-6 (7 для Примерска)"])
        delta = next(s for s in out["stays"] if s["hotel"] == "Villa Delta")
        self.assertEqual((delta["city"], delta["date"], delta["rating"]), ("Ozersk", "2026-06-01", "8.4"))

    def test_upcoming_and_unrated_stays_are_marked(self):
        result, out = run(HISTORY)
        echo = next(s for s in out["stays"] if s["hotel"] == "Hotel Echo")
        self.assertTrue(echo["upcoming"])
        gone = next(s for s in out["stays"] if s["hotel"] == "Hotel Gone")
        self.assertFalse(gone["rated"])
        self.assertEqual(out["counts"]["rated"], 4)

    def test_rating_scale_table_is_not_a_stay(self):
        result, out = run(HISTORY)
        self.assertNotIn("9–10", [s["hotel"] for s in out["stays"]])


if __name__ == "__main__":
    unittest.main()
