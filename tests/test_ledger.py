"""Tests for bin/ledger.py: the run folder, its record formats and the city slug.

All data here is made up.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ledger"
sys.path.insert(0, str(BIN))

import ledger  # noqa: E402


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CandidateValidationTest(unittest.TestCase):
    def test_valid_candidate_passes(self):
        self.assertEqual(ledger.validate_candidate(load("candidate-valid.json")), [])

    def test_candidate_without_a_source_fails(self):
        errors = ledger.validate_candidate(load("candidate-no-source.json"))
        self.assertTrue(any("source" in e for e in errors), errors)

    def test_reddit_mention_without_permalink_fails(self):
        errors = ledger.validate_candidate(load("candidate-reddit-no-permalink.json"))
        self.assertTrue(any("permalink" in e for e in errors), errors)

    def test_tripadvisor_source_fails(self):
        errors = ledger.validate_candidate(load("candidate-tripadvisor.json"))
        self.assertTrue(any("banned" in e for e in errors), errors)

    def test_validate_file_reports_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates-reddit.jsonl"
            lines = [json.dumps(load("candidate-valid.json")), json.dumps(load("candidate-tripadvisor.json"))]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(BIN / "ledger.py"), "validate", str(path), "--kind", "candidate"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("line 2", result.stdout)
            self.assertNotIn("line 1", result.stdout)


class EvidenceValidationTest(unittest.TestCase):
    RECORD = {"candidate": "Hotel Test", "kind": "engine_price", "source_url": "https://hotel.example/book",
              "quote": "175.50 € × 2 nights", "read_at": "2026-10-08T10:00:00+00:00", "price_eur": 175.5,
              "dates_shown": {"check_in": "2026-11-20", "check_out": "2026-11-22"}}

    def test_price_basis_is_optional_and_checked_when_present(self):
        self.assertEqual(ledger.validate_evidence(self.RECORD), [])
        for basis in ("per_night", "unknown"):
            self.assertEqual(ledger.validate_evidence(dict(self.RECORD, price_basis=basis)), [])
        errors = ledger.validate_evidence(dict(self.RECORD, price_basis="total"))
        self.assertTrue(any("price_basis" in e for e in errors), errors)


class SlugTest(unittest.TestCase):
    def test_cyrillic_and_latin_names_share_a_slug(self):
        self.assertEqual(ledger.city_slug("Гранада"), "granada")
        self.assertEqual(ledger.city_slug("Granada"), "granada")

    def test_accents_and_spaces(self):
        self.assertEqual(ledger.city_slug("San Sebastián"), "san-sebastian")
        self.assertEqual(ledger.city_slug("Nîmes"), "nimes")


class RunStateTest(unittest.TestCase):
    def test_init_creates_trip_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ledger.init_run(Path(tmp), city="Testgrad", check_in="2027-01-15", check_out="2027-01-17",
                                      guests=2, budget_min=150, budget_max=200, dog=False)
            self.assertEqual(run_dir, Path(tmp) / "trips" / "testgrad-2027-01" / "run")
            trip = json.loads((run_dir / "trip.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger.validate_trip(trip), [])
            self.assertEqual(ledger.read_state(run_dir)["stage"], "intake")

    def test_state_survives_write_and_reread(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ledger.init_run(Path(tmp), city="Testgrad", check_in="2027-01-15", check_out="2027-01-17",
                                      guests=2, budget_min=150, budget_max=200, dog=True)
            ledger.write_state(run_dir, stage="research", waiting_for=["curated-press", "reddit"])
            state = ledger.read_state(run_dir)
            self.assertEqual(state["stage"], "research")
            self.assertEqual(state["waiting_for"], ["curated-press", "reddit"])
            self.assertEqual([h["stage"] for h in state["history"]], ["intake", "research"])


if __name__ == "__main__":
    unittest.main()
