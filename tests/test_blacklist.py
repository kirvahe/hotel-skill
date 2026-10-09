"""Tests for bin/blacklist.py: read every city feedback file into one blacklist.

All hotels here are made up.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "blacklist.py"

SKILL_FORMAT = """---
city: Testgrad
slug: testgrad
---

# Testgrad — Hotel Feedback

## Blacklist

| Hotel | Reason | Source |
|---|---|---|
| Hôtel Ëcho Gris | "Бездушно" — no character | user feedback, 2026-04 |
| Grand Plain | chain feel | user feedback, 2026-05 |

## Positive reference

| Hotel | Reason | Source |
|---|---|---|
| Casa Buena | real character | user note, 2026-04 |
"""

MEMORY_FORMAT = """---
name: Twin Bay hotel feedback
type: feedback
---

# Twin Bay — hotel feedback

## Blacklist (do not recommend)

| Hotel | Reason | Source |
|---|---|---|
| Room Mate Nowhere | generic design chain | user feedback, 2026-04 |
"""

EMPTY_TABLE = """---
city: Emptyville
slug: emptyville
---

# Emptyville — Hotel Feedback

## Blacklist

| Hotel | Reason | Source |
|---|---|---|
"""

PRINCIPLE_FILE = """---
name: No soulless hotels
type: feedback
---

Never recommend generic modern hotels without character.
"""


def run_parser(files: dict):
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in files.items():
            (Path(tmp) / name).write_text(text, encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), tmp], capture_output=True, text=True)
        return result


class BlacklistTest(unittest.TestCase):
    def test_reads_every_hotel_from_both_formats(self):
        result = run_parser({
            "feedback_testgrad_hotels.md": SKILL_FORMAT,
            "feedback_tb_hotels.md": MEMORY_FORMAT,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        names = sorted(entry["hotel"] for entry in data["blacklist"])
        self.assertEqual(names, ["Grand Plain", "Hôtel Ëcho Gris", "Room Mate Nowhere"])
        echo = next(e for e in data["blacklist"] if e["hotel"] == "Hôtel Ëcho Gris")
        self.assertEqual(echo["city"], "Testgrad")
        self.assertEqual(echo["reason"], '"Бездушно" — no character')

    def test_positive_references_are_not_blacklisted(self):
        result = run_parser({"feedback_testgrad_hotels.md": SKILL_FORMAT})
        data = json.loads(result.stdout)
        self.assertNotIn("Casa Buena", [e["hotel"] for e in data["blacklist"]])

    def test_empty_blacklist_table_returns_empty_list(self):
        result = run_parser({"feedback_emptyville_hotels.md": EMPTY_TABLE})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["blacklist"], [])
        self.assertEqual(data["skipped"], [])

    def test_file_without_blacklist_table_is_skipped_and_reported(self):
        result = run_parser({
            "feedback_testgrad_hotels.md": SKILL_FORMAT,
            "feedback_no_soulless_hotels.md": PRINCIPLE_FILE,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["blacklist"]), 2)
        self.assertEqual([s["file"] for s in data["skipped"]], ["feedback_no_soulless_hotels.md"])

    def test_missing_folder_is_an_empty_result_not_a_crash(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "/nonexistent/feedback"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["blacklist"], [])
        self.assertIn("not found", data["note"])


if __name__ == "__main__":
    unittest.main()
