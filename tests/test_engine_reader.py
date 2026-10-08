"""Tests for bin/engine_reader.py: the background reader of hotels' own booking engines.

Every hotel, engine and URL here is made up. No test reaches the web. Saved pages in
tests/fixtures/engines/ are read by the HTML parser (fixture mode) or, when Playwright is
installed, by headless Chromium opening the saved file through a file:// URL.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "engines"
sys.path.insert(0, str(BIN))

import engine_reader as reader  # noqa: E402
import ledger  # noqa: E402

TRIP = reader.Trip(check_in=date(2026, 11, 20), check_out=date(2026, 11, 22), guests=2)
TRIP_ARGS = ["--check-in", "2026-11-20", "--check-out", "2026-11-22", "--guests", "2"]
# Test values only. The real page timeout and give-up rule are chosen by the user after the live smoke.
LIMIT_ARGS = ["--page-timeout-s", "10", "--give-up-after-s", "20"]
ENGINE = "https://reservas.motor-demo.example/casa-aljibe?entrada=2026-11-20&salida=2026-11-22"
SITE = "https://casa-aljibe.example/"


def run_reader(url, out, *extra, limits=LIMIT_ARGS, env=None):
    command = [sys.executable, str(BIN / "engine_reader.py"), "--candidate", "Hotel Inventado",
               "--url", url, *TRIP_ARGS, *limits, "--out", str(out), *extra]
    return subprocess.run(command, capture_output=True, text=True, env=env)


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SavedPages:
    """A fetch function that serves saved pages by URL and remembers every request."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []
        self.timeouts = []

    def __call__(self, url, timeout_s):
        self.requested.append(url)
        self.timeouts.append(timeout_s)
        if url not in self.pages:
            raise reader.PageError(f"no saved page for {url}")
        html = (FIXTURES / self.pages[url]).read_text(encoding="utf-8")
        return reader.page_from_html(html, url)


class FixtureModeTest(unittest.TestCase):
    def read(self, name, url=ENGINE):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence.jsonl"
            result = run_reader(url, out, "--fixture", str(FIXTURES / name))
            self.assertEqual(result.returncode, 0, result.stderr)
            [record] = records(out)
        self.assertEqual(ledger.validate_evidence(record), [])
        self.assertEqual(record["source_url"], url)
        self.assertTrue(record["read_at"])
        return record

    def test_priced_page_yields_available_with_eur_price(self):
        record = self.read("priced-es.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 160.0)
        self.assertIn("160,00", record["quote"])
        self.assertEqual(record["dates_shown"]["check_in"], "2026-11-20")
        self.assertEqual(record["dates_shown"]["check_out"], "2026-11-22")
        self.assertIn("20/11/2026", record["dates_shown"]["quote"])

    def test_no_availability_page_yields_no_rooms(self):
        record = self.read("no-rooms-it.html")
        self.assertEqual(record["kind"], "engine_no_rooms")
        self.assertIn("non ci sono camere disponibili", record["quote"])
        self.assertEqual(record["dates_shown"]["check_in"], "2026-11-20")
        self.assertEqual(record["dates_shown"]["check_out"], "2026-11-22")

    def test_page_that_never_shows_a_price_yields_unknown(self):
        record = self.read("no-price-fr.html")
        self.assertEqual(record["kind"], "engine_unreadable")
        self.assertNotIn("price_eur", record)
        self.assertIn("neither a price", record["reason"])

    def test_page_showing_other_dates_records_the_dates_it_shows(self):
        record = self.read("other-dates-en.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 189.0)
        self.assertEqual(record["dates_shown"]["check_in"], "2026-11-21")
        self.assertEqual(record["dates_shown"]["check_out"], "2026-11-23")


class BookingAndAirbnbRefusalTest(unittest.TestCase):
    def test_booking_url_is_refused_with_its_own_exit_code(self):
        url = "https://www.booking.com/hotel/es/casa-del-aljibe-inventada.html"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence.jsonl"
            result = run_reader(url, out)
            self.assertEqual(result.returncode, reader.EXIT_REFUSED, result.stderr)
            [record] = records(out)
        self.assertIn("R21", result.stderr)
        self.assertEqual(record["kind"], "engine_unreadable")
        self.assertIn("R21", record["reason"])
        self.assertEqual(ledger.validate_evidence(record), [])

    def test_booking_and_airbnb_hosts_on_any_domain_are_refused(self):
        refused = ["https://booking.com/x", "https://secure.booking.com/book.html", "http://WWW.BOOKING.COM/",
                   "https://www.airbnb.es/rooms/1", "https://airbnb.com/", "https://es.airbnb.com/s/Testgrad",
                   "https://www.airbnb.co.uk/rooms/2"]
        allowed = ["https://booking.casa-aljibe.example/", "https://reservas.motor-demo.example/",
                   "https://notbooking.com/", "https://airbnbish.example/"]
        for url in refused:
            with self.subTest(url):
                self.assertTrue(reader.refused_host(url))
        for url in allowed:
            with self.subTest(url):
                self.assertIsNone(reader.refused_host(url))

    def test_hotel_site_whose_booking_link_goes_to_booking_makes_no_booking_request(self):
        fetch = SavedPages({SITE: "site-booking-link.html"})
        record, refused = reader.read_engine("Casa del Aljibe Inventada", SITE, TRIP, fetch,
                                             page_timeout_s=10, give_up_after_s=20)
        self.assertTrue(refused)
        self.assertEqual(record["kind"], "engine_unreadable")
        self.assertIn("R21", record["reason"])
        self.assertEqual(fetch.requested, [SITE])
        self.assertEqual(ledger.validate_evidence(record), [])

    def test_redirect_to_booking_is_refused_before_it_is_requested(self):
        hops = {SITE: (302, "/reservas"), SITE + "reservas": (301, "https://secure.booking.com/book.html")}
        probed = []

        def probe(url):
            probed.append(url)
            return hops[url]

        with self.assertRaises(reader.Refused):
            reader.resolve_redirects(SITE, probe)
        self.assertEqual(probed, [SITE, SITE + "reservas"])


class OfficialSiteTest(unittest.TestCase):
    def test_link_to_the_hotels_own_engine_is_followed_and_the_booking_link_skipped(self):
        fetch = SavedPages({SITE: "site-own-engine.html", ENGINE: "priced-es.html"})
        record, refused = reader.read_engine("Casa del Aljibe Inventada", SITE, TRIP, fetch,
                                             page_timeout_s=10, give_up_after_s=20)
        self.assertFalse(refused)
        self.assertEqual(fetch.requested, [SITE, ENGINE])
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["source_url"], ENGINE)

    def test_give_up_rule_stops_before_the_next_page(self):
        now = [0.0]
        pages = SavedPages({SITE: "site-own-engine.html", ENGINE: "priced-es.html"})

        def slow_fetch(url, timeout_s):
            now[0] += 25
            return pages(url, timeout_s)

        record, refused = reader.read_engine("Casa del Aljibe Inventada", SITE, TRIP, slow_fetch,
                                             page_timeout_s=10, give_up_after_s=20, clock=lambda: now[0])
        self.assertFalse(refused)
        self.assertEqual(pages.requested, [SITE])
        self.assertEqual(pages.timeouts, [10])
        self.assertEqual(record["kind"], "engine_unreadable")
        self.assertIn("gave up", record["reason"])
        self.assertEqual(ledger.validate_evidence(record), [])

    def test_url_placeholders_take_the_trip_values(self):
        url = "https://reservas.motor-demo.example/?in={check_in:%d/%m/%Y}&out={check_out}&adults={guests}"
        self.assertEqual(reader.fill_url(url, TRIP),
                         "https://reservas.motor-demo.example/?in=20/11/2026&out=2026-11-22&adults=2")

    def test_page_timeout_and_give_up_rule_have_no_defaults(self):
        for flag in ("--page-timeout-s", "--give-up-after-s"):
            limits = [arg for pair in zip(LIMIT_ARGS[::2], LIMIT_ARGS[1::2]) if pair[0] != flag for arg in pair]
            with self.subTest(flag), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "evidence.jsonl"
                result = run_reader(ENGINE, out, "--fixture", str(FIXTURES / "priced-es.html"), limits=limits)
                self.assertEqual(result.returncode, 2)
                self.assertIn(flag, result.stderr)
                self.assertFalse(out.exists())


class MissingPlaywrightTest(unittest.TestCase):
    def test_missing_playwright_exits_with_the_skip_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            shadow = Path(tmp) / "shadow" / "playwright"
            shadow.mkdir(parents=True)
            (shadow / "__init__.py").write_text('raise ImportError("hidden by the test")\n', encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(shadow.parent))
            out = Path(tmp) / "evidence.jsonl"
            result = run_reader((FIXTURES / "no-price-fr.html").as_uri(), out, env=env)
            self.assertFalse(out.exists())
        self.assertEqual(result.returncode, reader.EXIT_SKIPPED, result.stderr)
        self.assertIn("SKIPPED: background browser not installed", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


class PatternTableTest(unittest.TestCase):
    DATES = "Entrada 20/11/2026 · Salida 22/11/2026"

    def classify(self, *lines):
        page = reader.Page(url=ENGINE, lines=list(lines), links=[])
        return reader.classify("Hotel Inventado", page, TRIP)

    def test_prices_in_four_languages(self):
        cases = {
            "es": ("Habitación doble 160,00 €", 160.0),
            "it": ("Camera matrimoniale € 1.250,00", 1250.0),
            "fr": ("Chambre double 1\u202f250,00\u00a0€", 1250.0),
            "en": ("Double room EUR 189.50", 189.5),
        }
        for lang, (line, price) in cases.items():
            with self.subTest(lang):
                record = self.classify(self.DATES, line)
                self.assertEqual(record["kind"], "engine_price")
                self.assertEqual(record["price_eur"], price)

    def test_no_availability_in_four_languages(self):
        cases = {
            "es": "No hay disponibilidad para las fechas seleccionadas",
            "it": "Nessuna disponibilità per il periodo richiesto",
            "fr": "Aucune chambre disponible pour ces dates",
            "en": "No rooms available for your dates",
        }
        for lang, line in cases.items():
            with self.subTest(lang):
                record = self.classify(self.DATES, line)
                self.assertEqual(record["kind"], "engine_no_rooms")
                self.assertEqual(record["quote"], line)

    def test_tax_lines_and_zero_totals_are_not_room_prices(self):
        record = self.classify(self.DATES, "Total: 0,00 €", "Tasa turística 1,10 € por persona y noche", "Doble 140 €")
        self.assertEqual(record["price_eur"], 140.0)

    def test_price_and_no_availability_on_one_page_is_unknown(self):
        record = self.classify(self.DATES, "No hay disponibilidad", "Fechas alternativas desde 140 €")
        self.assertEqual(record["kind"], "engine_unreadable")

    def test_price_without_dates_is_unknown(self):
        record = self.classify("Doble 140 €")
        self.assertEqual(record["kind"], "engine_unreadable")
        self.assertIn("dates", record["reason"])

    def test_dates_in_page_formats(self):
        cases = {
            "iso": ["Entrada 2026-11-20", "Salida 2026-11-22"],
            "spanish words": ["20 de noviembre de 2026 – 22 de noviembre de 2026"],
            "french without year": ["ven. 20 nov. – dim. 22 nov."],
            "english month first": ["Nov 20, 2026 - Nov 22, 2026"],
        }
        for name, lines in cases.items():
            with self.subTest(name):
                shown = reader.dates_shown(lines, TRIP)
                self.assertEqual((shown["check_in"], shown["check_out"]), ("2026-11-20", "2026-11-22"))


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright is not installed")
class HeadlessBrowserOnSavedPagesTest(unittest.TestCase):
    """The live path, run on saved files through file:// URLs: no web request is made."""

    def read_live(self, name):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence.jsonl"
            result = run_reader((FIXTURES / name).as_uri(), out)
            if result.returncode == reader.EXIT_SKIPPED:
                self.skipTest(result.stdout.strip())
            self.assertEqual(result.returncode, 0, result.stderr)
            [record] = records(out)
        self.assertEqual(ledger.validate_evidence(record), [])
        return record

    def test_headless_browser_reads_a_priced_page(self):
        record = self.read_live("priced-es.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 160.0)
        self.assertEqual(record["dates_shown"]["check_in"], "2026-11-20")

    def test_text_hidden_by_a_stylesheet_is_not_read(self):
        record = self.read_live("css-hidden-es.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 160.0)


if __name__ == "__main__":
    unittest.main()
