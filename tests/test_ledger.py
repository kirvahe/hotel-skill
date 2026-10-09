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


class ReadRecordsTest(unittest.TestCase):
    """A JSON line that is not an object is a rejected line, never a crash."""

    def write(self, tmp: str, lines: list) -> Path:
        path = Path(tmp) / "candidates-reddit.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_lines_that_are_not_objects_are_rejected(self):
        valid, banned = load("candidate-valid.json"), load("candidate-tripadvisor.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [json.dumps(valid), "[1]", "", "5", '{"not json', json.dumps(banned)])
            records, rejected = ledger.read_records(path, "candidate", label="name")
        self.assertEqual(records, [valid])
        self.assertEqual([r["line"] for r in rejected], [2, 4, 5, 6])
        self.assertEqual(rejected[0], {"line": 2, "problems": ["not a JSON object"]})
        self.assertEqual(rejected[1], {"line": 4, "problems": ["not a JSON object"]})
        self.assertTrue(rejected[2]["problems"][0].startswith("not valid JSON ("), rejected[2])
        self.assertNotIn("name", rejected[2])
        self.assertEqual(rejected[3]["name"], banned["name"])
        self.assertEqual(rejected[3]["problems"], ledger.validate_candidate(banned))

    def test_validate_reports_a_line_that_is_not_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [json.dumps(load("candidate-valid.json")), "[1]"])
            self.assertEqual(ledger.validate_file(path, "candidate"), ["line 2: not a JSON object"])
            result = subprocess.run([sys.executable, str(BIN / "ledger.py"), "validate", str(path), "--kind", "candidate"],
                                    capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip(), result.stderr), (1, "line 2: not a JSON object", ""))


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


class PetEvidenceTest(unittest.TestCase):
    RECORD = {"candidate": "Hotel Test", "kind": "pet_policy", "source_url": "https://hotel.example/pets",
              "quote": "Dogs up to 8 kg in Superior rooms", "read_at": "2026-10-08T10:00:00+00:00",
              "value": "restricted", "room_types": ["Superior"]}

    def test_the_four_brief_values_pass(self):
        for value in ("allowed", "not allowed", "restricted", "hotel-level only"):
            self.assertEqual(ledger.validate_evidence(dict(self.RECORD, value=value)), [], value)

    def test_other_values_fail(self):
        errors = ledger.validate_evidence(dict(self.RECORD, value="yes"))
        self.assertTrue(any("value" in e for e in errors), errors)

    def test_room_types_must_be_a_list(self):
        errors = ledger.validate_evidence(dict(self.RECORD, room_types="Superior"))
        self.assertTrue(any("room_types" in e for e in errors), errors)


class ResolvedValidationTest(unittest.TestCase):
    RECORD = {"candidate": "Casa del Ejemplo",
              "official_url": {"value": "https://casadelejemplo.example/", "source_url": "https://casadelejemplo.example/contacto",
                               "quote": "Casa del Ejemplo · Calle Mayor 1 · Testgrad"},
              "judgments": [{"rule": "chain with character", "verdict": "pass", "reason": "its own design",
                             "source_url": "https://diario.example/hoteles", "quote": "un palacete rehabilitado"}]}

    def test_brief_example_passes(self):
        self.assertEqual(ledger.validate_resolved(self.RECORD), [])

    def test_no_official_url_is_null(self):
        self.assertEqual(ledger.validate_resolved(dict(self.RECORD, official_url=None, judgments=[])), [])

    def test_official_url_on_booking_or_airbnb_fails(self):
        for url in ("https://www.booking.com/hotel/xx/casa.html", "https://www.airbnb.es/rooms/1"):
            record = dict(self.RECORD, official_url=dict(self.RECORD["official_url"], value=url))
            self.assertTrue(any("official_url" in e for e in ledger.validate_resolved(record)), url)

    def test_a_fail_verdict_needs_a_quote_and_a_reason(self):
        judgment = {"rule": "large or mainstream hotel", "verdict": "fail", "reason": "240 rooms"}
        errors = ledger.validate_resolved(dict(self.RECORD, judgments=[judgment]))
        self.assertTrue(any("quote" in e for e in errors), errors)
        judgment = {"rule": "large or mainstream hotel", "verdict": "maybe", "reason": "x"}
        errors = ledger.validate_resolved(dict(self.RECORD, judgments=[judgment]))
        self.assertTrue(any("verdict" in e for e in errors), errors)

    def test_a_pass_without_evidence_is_fine(self):
        judgment = {"rule": "chain with character", "verdict": "pass", "reason": "no evidence either way"}
        self.assertEqual(ledger.validate_resolved(dict(self.RECORD, judgments=[judgment])), [])


class FinalValidationTest(unittest.TestCase):
    RECORD = {"candidate": "Casa del Ejemplo", "room_type": "Doble Superior", "rate": "Tarifa flexible",
              "cancellation": {"value": "free until 2027-01-13", "deadline": "2027-01-13",
                               "source_url": "https://casadelejemplo.example/condiciones",
                               "quote": "Cancelación gratuita hasta 2 días antes de la llegada."}}

    def test_brief_example_passes(self):
        self.assertEqual(ledger.validate_final(self.RECORD), [])

    def test_unknown_cancellation_needs_no_source(self):
        self.assertEqual(ledger.validate_final(dict(self.RECORD, cancellation={"value": "unknown"})), [])

    def test_stated_cancellation_needs_a_quote(self):
        errors = ledger.validate_final(dict(self.RECORD, cancellation={"value": "free until 2027-01-13"}))
        self.assertTrue(any("cancellation" in e for e in errors), errors)

    def test_bad_deadline_fails(self):
        cancellation = dict(self.RECORD["cancellation"], deadline="13/01/2027")
        errors = ledger.validate_final(dict(self.RECORD, cancellation=cancellation))
        self.assertTrue(any("deadline" in e for e in errors), errors)


class GmailValidationTest(unittest.TestCase):
    RECORD = {"status": "complete", "mailbox": "personal", "reason": "",
              "bookings": [{"hotel": "Casa del Ejemplo", "city": "Testgrad", "check_in": "2025-05-02",
                            "check_out": "2025-05-04", "message_date": "2025-03-01"}]}

    def test_valid_file_passes(self):
        self.assertEqual(ledger.validate_gmail(self.RECORD), [])

    def test_failed_status_needs_a_reason(self):
        errors = ledger.validate_gmail({"status": "failed", "bookings": []})
        self.assertTrue(any("reason" in e for e in errors), errors)

    def test_booking_needs_a_hotel_and_a_check_in_date(self):
        errors = ledger.validate_gmail(dict(self.RECORD, bookings=[{"hotel": "", "check_in": "May 2025"}]))
        self.assertTrue(any("hotel" in e for e in errors), errors)
        self.assertTrue(any("check_in" in e for e in errors), errors)

    def test_cli_validates_the_new_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resolved-1.jsonl"
            path.write_text(json.dumps(ResolvedValidationTest.RECORD) + "\n{\"candidate\": \"\"}\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(BIN / "ledger.py"), "validate", str(path), "--kind", "resolved"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("line 2", result.stdout)
            self.assertNotIn("line 1", result.stdout)


class SlugTest(unittest.TestCase):
    def test_cyrillic_and_latin_names_share_a_slug(self):
        self.assertEqual(ledger.city_slug("Лиссабон"), "lissabon")
        self.assertEqual(ledger.city_slug("Lissabon"), "lissabon")

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
