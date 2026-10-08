"""Tests for bin/links.py: Booking, Google Maps and Airbnb links. Nothing is fetched.

All hotels here are made up.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pipeline"
sys.path.insert(0, str(FIXTURES))

import runkit  # noqa: E402
from runkit import BIN  # noqa: E402

import links  # noqa: E402
import merge_candidates  # noqa: E402


def query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


class BookingLinkTest(unittest.TestCase):
    def test_hotel_url_carries_dates_adults_one_room_and_eur(self):
        url = links.booking_link("Casa Velarta", "Testgrad", "2026-11-20", "2026-11-22", 2,
                                 booking_url="https://www.booking.com/hotel/tg/casa-velarta.html?aid=123")
        parsed = urlparse(url)
        self.assertEqual(parsed.netloc, "www.booking.com")
        self.assertEqual(parsed.path, "/hotel/tg/casa-velarta.html")
        self.assertEqual(query(url), {"checkin": "2026-11-20", "checkout": "2026-11-22", "group_adults": "2",
                                      "no_rooms": "1", "selected_currency": "EUR"})

    def test_without_a_hotel_url_it_is_a_search_by_name_and_city(self):
        url = links.booking_link("Palacio Ñandú", "Testgrad", "2026-11-20", "2026-11-22", 2)
        parsed = urlparse(url)
        self.assertEqual(parsed.path, "/searchresults.html")
        q = query(url)
        self.assertEqual(q["ss"], "Palacio Ñandú, Testgrad")
        self.assertEqual((q["checkin"], q["checkout"], q["group_adults"], q["no_rooms"], q["selected_currency"]),
                         ("2026-11-20", "2026-11-22", "2", "1", "EUR"))

    def test_a_non_booking_url_is_not_used_as_the_hotel_page(self):
        url = links.booking_link("Casa Velarta", "Testgrad", "2026-11-20", "2026-11-22", 2,
                                 booking_url="https://casavelarta.example/")
        self.assertEqual(urlparse(url).netloc, "www.booking.com")
        self.assertEqual(urlparse(url).path, "/searchresults.html")


class MapsLinkTest(unittest.TestCase):
    def test_maps_link_carries_name_street_and_city(self):
        url = links.maps_link("Casa Velarta", "Calle del Pozo 4", "Testgrad")
        self.assertTrue(url.startswith("https://www.google.com/maps/search/?"))
        q = query(url)
        self.assertEqual(q["api"], "1")
        self.assertEqual(q["query"], "Casa Velarta, Calle del Pozo 4, Testgrad")

    def test_maps_link_without_a_street(self):
        self.assertEqual(query(links.maps_link("Casa Velarta", "", "Testgrad"))["query"], "Casa Velarta, Testgrad")


class AirbnbLinkTest(unittest.TestCase):
    def test_airbnb_link_carries_dates_and_adults_without_pets(self):
        url = links.airbnb_link("Hill Quarter, Testgrad", "2026-11-20", "2026-11-22", 2, pets=False)
        self.assertEqual(urlparse(url).netloc, "www.airbnb.com")
        q = query(url)
        self.assertEqual((q["checkin"], q["checkout"], q["adults"]), ("2026-11-20", "2026-11-22", "2"))
        self.assertNotIn("pets", q)

    def test_airbnb_link_adds_pets_when_the_dog_travels(self):
        url = links.airbnb_link("Testgrad", "2026-11-20", "2026-11-22", 2, pets=True)
        self.assertEqual(query(url)["pets"], "1")


class RunLinksTest(unittest.TestCase):
    def test_cli_builds_links_for_every_merged_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = runkit.make_run(tmp)
            merge_candidates.merge_run(run)
            result = subprocess.run([sys.executable, str(BIN / "links.py"), str(run)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout)
            self.assertEqual(len(out), 13)
            velarta = next(v for v in out.values() if v["name"] == "Casa Velarta")
            self.assertIn("/hotel/tg/casa-velarta.html", velarta["booking"])
            self.assertIn("airbnb", next(v for v in out.values() if v["name"] == "Carmen del Aljibe Rojo"))


if __name__ == "__main__":
    unittest.main()
