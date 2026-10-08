"""Tests for bin/migrate_check.py: every hotel row and rating survives a profile/history migration.

All data here is made up. Real profiles never go into this repository.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "migrate_check.py"

ORIGINAL = """# Профиль

## Сильные (7-9)

| Отель | Город | Оценка |
|-------|-------|--------|
| Hotel Alpha | Тестоград | 8-9 |
| Casa Beta | Примерск | 5-6 (7 для Примерска) |
| Casa Beta | Примерск | 5-6 (7 для Примерска) |

## Референсы

| Отель | Город | Впечатление |
|-------|-------|-------------|
| Villa Gamma | Озёрск | Замечательное |
"""

MIGRATED_OK = """# Profile

## Strong (7-9)

| Hotel | City | Rating |
|---|---|---|
| Hotel Alpha | Testgrad | 8-9 |
| Casa Beta | Primersk | 5-6 (7 для Примерска) |
| Casa Beta | Primersk | 5-6 (7 для Примерска) |

## Aspirational tier

| Hotel | City | Impression |
|---|---|---|
| Villa Gamma | Ozersk | Wonderful |
"""


def run_check(original: str, migrated: str):
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = Path(tmp) / "orig.md"
        mig_path = Path(tmp) / "mig.md"
        orig_path.write_text(original, encoding="utf-8")
        mig_path.write_text(migrated, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(orig_path), str(mig_path)],
            capture_output=True,
            text=True,
        )


class MigrateCheckTest(unittest.TestCase):
    def test_passes_when_every_row_and_rating_survives(self):
        result = run_check(ORIGINAL, MIGRATED_OK)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_fails_when_a_row_is_missing(self):
        migrated = MIGRATED_OK.replace("| Villa Gamma | Ozersk | Wonderful |\n", "")
        result = run_check(ORIGINAL, migrated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Villa Gamma", result.stdout)

    def test_fails_when_a_range_rating_is_normalized(self):
        migrated = MIGRATED_OK.replace("| Hotel Alpha | Testgrad | 8-9 |", "| Hotel Alpha | Testgrad | 8.5 |")
        result = run_check(ORIGINAL, migrated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Hotel Alpha", result.stdout)

    def test_fails_when_a_context_note_in_the_rating_is_dropped(self):
        migrated = MIGRATED_OK.replace("5-6 (7 для Примерска) |\n| Casa Beta", "5-6 |\n| Casa Beta", 1)
        result = run_check(ORIGINAL, migrated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Casa Beta", result.stdout)

    def test_fails_when_a_repeated_stay_loses_one_copy(self):
        migrated = MIGRATED_OK.replace("| Casa Beta | Primersk | 5-6 (7 для Примерска) |\n", "", 1)
        result = run_check(ORIGINAL, migrated)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Casa Beta", result.stdout)


if __name__ == "__main__":
    unittest.main()
