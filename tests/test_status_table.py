"""Tests for bin/status_table.py: availability evidence to available / unavailable / unknown.

All hotels here are made up (see tests/fixtures/pipeline/runkit.py).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pipeline"
sys.path.insert(0, str(FIXTURES))

import runkit  # noqa: E402
from runkit import BIN, read_json, read_jsonl, write_jsonl  # noqa: E402

import merge_candidates  # noqa: E402
import status_table  # noqa: E402

TRIP = {"check_in": "2026-11-20", "check_out": "2026-11-22"}
MATCH = {"check_in": "2026-11-20", "check_out": "2026-11-22"}
OTHER = {"check_in": "2026-11-21", "check_out": "2026-11-23"}


def ev(kind, at="2026-10-08T10:00:00+00:00", url="https://hotel.example/book", **extra):
    record = {"candidate": "Hotel Test", "kind": kind, "source_url": url, "quote": f"{kind} quote", "read_at": at}
    record.update(extra)
    return record


class DecideTest(unittest.TestCase):
    # AE1
    def test_booking_says_full_but_the_engine_prices_the_dates(self):
        result = status_table.decide([
            ev("engine_no_rooms", url="https://www.booking.com/hotel/tg/x.html", dates_shown=MATCH),
            ev("engine_price", dates_shown=MATCH, price_eur=160),
        ], TRIP)
        self.assertEqual((result["status"], result["price_eur"]), ("available", 160))

    def test_price_basis_is_carried_and_a_record_without_one_is_per_night(self):
        result = status_table.decide([ev("engine_price", dates_shown=MATCH, price_eur=351, price_basis="unknown")], TRIP)
        self.assertEqual((result["price_eur"], result["price_basis"]), (351, "unknown"))
        result = status_table.decide([ev("engine_price", dates_shown=MATCH, price_eur=160)], TRIP)
        self.assertEqual(result["price_basis"], "per_night")

    def test_booking_no_rooms_alone_is_not_evidence(self):
        result = status_table.decide([ev("engine_no_rooms", url="https://www.booking.com/hotel/tg/x.html",
                                         dates_shown=MATCH)], TRIP)
        self.assertEqual(result["status"], "unknown")

    # #14: the host decides, as for the guard and the reader, not a "booking.com" anywhere in the URL
    def test_the_hotel_engine_counts_when_its_url_only_names_booking(self):
        for url in ("https://hotel.example/book?utm_source=booking.com", "https://reservas.myhotelbooking.com/",
                    "https://hotel.example/reservas/airbnb.es"):
            result = status_table.decide([ev("engine_price", url=url, dates_shown=MATCH, price_eur=160)], TRIP)
            self.assertEqual((result["status"], result["price_eur"]), ("available", 160), url)
        for url in ("https://secure.booking.com/book.html", "https://www.airbnb.com/rooms/1", "booking.com/hotel/tg/x"):
            result = status_table.decide([ev("engine_price", url=url, dates_shown=MATCH, price_eur=160)], TRIP)
            self.assertEqual(result["status"], "unknown", url)

    # AE2
    def test_closure_from_the_second_night_is_unavailable(self):
        result = status_table.decide([ev("closure", closed_from="2026-11-21")], TRIP)
        self.assertEqual(result["status"], "unavailable")

    def test_closure_from_check_out_day_is_kept(self):
        result = status_table.decide([ev("closure", closed_from="2026-11-22", closed_until="2027-02-28")], TRIP)
        self.assertEqual(result["status"], "unknown")

    def test_closure_that_ended_before_check_in_is_kept(self):
        result = status_table.decide([ev("closure", closed_from="2026-01-10", closed_until="2026-11-19")], TRIP)
        self.assertEqual(result["status"], "unknown")

    def test_closure_ending_on_the_first_night_overlaps(self):
        result = status_table.decide([ev("closure", closed_until="2026-11-20")], TRIP)
        self.assertEqual(result["status"], "unavailable")

    def test_closure_without_dates_is_unreadable_not_unavailable(self):
        result = status_table.decide([ev("closure")], TRIP)
        self.assertEqual(result["status"], "unknown")

    # AE3
    def test_no_evidence_is_unknown(self):
        self.assertEqual(status_table.decide([], TRIP)["status"], "unknown")

    def test_unreadable_engine_is_unknown(self):
        self.assertEqual(status_table.decide([ev("engine_unreadable")], TRIP)["status"], "unknown")

    # KTD4 dates_shown
    def test_price_for_other_dates_is_unknown(self):
        result = status_table.decide([ev("engine_price", dates_shown=OTHER, price_eur=150)], TRIP)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["price_eur"])

    def test_no_rooms_for_other_dates_is_unknown(self):
        result = status_table.decide([ev("engine_no_rooms", dates_shown=OTHER)], TRIP)
        self.assertEqual(result["status"], "unknown")

    def test_no_rooms_from_the_hotel_engine_for_the_dates_is_unavailable(self):
        result = status_table.decide([ev("engine_no_rooms", dates_shown=MATCH)], TRIP)
        self.assertEqual(result["status"], "unavailable")

    def test_latest_engine_reading_wins(self):
        price = ev("engine_price", at="2026-10-08T10:00:00+00:00", dates_shown=MATCH, price_eur=160)
        full = ev("engine_no_rooms", at="2026-10-08T12:00:00+00:00", dates_shown=MATCH)
        self.assertEqual(status_table.decide([price, full], TRIP)["status"], "unavailable")
        price_later = dict(price, read_at="2026-10-08T13:00:00+00:00", price_eur=175)
        result = status_table.decide([price, full, price_later], TRIP)
        self.assertEqual((result["status"], result["price_eur"]), ("available", 175))

    def test_closure_against_a_priced_engine_is_unknown(self):
        result = status_table.decide([ev("closure", closed_from="2026-11-21"),
                                      ev("engine_price", dates_shown=MATCH, price_eur=160)], TRIP)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "conflict")

    def test_scarcity_for_the_dates_is_attached(self):
        result = status_table.decide([ev("engine_price", dates_shown=MATCH, price_eur=160),
                                      ev("scarcity", dates_shown=MATCH, quote="Only 1 room left")], TRIP)
        self.assertEqual(result["scarcity"], "Only 1 room left")
        stale = status_table.decide([ev("scarcity", dates_shown=OTHER, quote="Only 1 room left")], TRIP)
        self.assertIsNone(stale["scarcity"])


class StatusRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)
        merge_candidates.merge_run(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def statuses(self) -> dict:
        status_table.status_run(self.run)
        data = read_json(self.run / "status.json")
        return {s["name"]: s for s in data["candidates"].values()}

    def test_fixture_statuses(self):
        s = self.statuses()
        self.assertEqual((s["Casa Velarta"]["status"], s["Casa Velarta"]["price_eur"]), ("available", 160))
        self.assertEqual(s["Palacio Ñandú"]["status"], "unknown")
        self.assertEqual(s["Hotel Invierno"]["status"], "unavailable")
        self.assertEqual(s["Hotel Otoño"]["status"], "unknown")
        self.assertEqual(s["Hotel Marquesa Vieja"]["status"], "unknown")
        self.assertEqual(s["Hotel Sombra"]["status"], "unknown")
        self.assertEqual(s["El Patio Lunar"]["status"], "unknown")
        self.assertEqual((s["Hotel Torre Alta"]["status"], s["Hotel Torre Alta"]["price_eur"]), ("available", 290))

    def test_evidence_the_ledger_rejects_is_ignored_and_reported(self):
        records = read_jsonl(self.run / "evidence.jsonl")
        records.append({"candidate": "Hotel Otoño", "kind": "engine_no_rooms", "source_url": "https://hotelotono.example/",
                        "quote": "full", "read_at": "2026-10-08T11:00:00+00:00"})
        write_jsonl(self.run / "evidence.jsonl", records)
        report = status_table.status_run(self.run)
        self.assertEqual([r["line"] for r in report["rejected"]], [12])
        self.assertEqual(self.statuses()["Hotel Otoño"]["status"], "unknown")

    def test_a_line_that_is_not_an_object_is_rejected_not_a_crash(self):
        with open(self.run / "evidence.jsonl", "a", encoding="utf-8") as handle:
            handle.write("[1]\n")
        report = status_table.status_run(self.run)
        self.assertEqual(report["rejected"], [{"line": 12, "problems": ["not a JSON object"]}])
        self.assertEqual(self.statuses()["Casa Velarta"]["price_eur"], 160)

    def test_missing_evidence_file_means_every_candidate_is_unknown(self):
        (self.run / "evidence.jsonl").unlink()
        self.assertEqual({s["status"] for s in self.statuses().values()}, {"unknown"})

    def test_evidence_for_an_unknown_name_is_reported(self):
        records = read_jsonl(self.run / "evidence.jsonl")
        records.append({"candidate": "Hotel Nowhere", "kind": "engine_unreadable", "source_url": "https://x.example/",
                        "quote": "x", "read_at": "2026-10-08T11:00:00+00:00"})
        write_jsonl(self.run / "evidence.jsonl", records)
        report = status_table.status_run(self.run)
        self.assertEqual(report["unmatched"], ["Hotel Nowhere"])

    def test_cli_writes_status_json(self):
        result = subprocess.run([sys.executable, str(BIN / "status_table.py"), str(self.run)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("counts", json.loads(result.stdout))
        self.assertTrue((self.run / "status.json").is_file())


if __name__ == "__main__":
    unittest.main()
