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
import time
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

    def test_engine_page_with_a_legend_other_sites_and_a_longer_stay_offer(self):
        # Laid out like a real engine from the live smoke: the calendar legend "× = No availability"
        # is not about the dates, Booking.com and Expedia prices are not the hotel's, and the
        # 6-night offer is for other dates. The price is the per-night line for the trip's 2 nights.
        record = self.read("stay-offers-en.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 175.5)
        self.assertEqual(record["price_basis"], "per_night")
        self.assertEqual(record["quote"], "175.50 € × 2 nights")
        self.assertEqual((record["dates_shown"]["check_in"], record["dates_shown"]["check_out"]),
                         ("2026-11-20", "2026-11-22"))


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

    def test_home_page_with_other_dates_goes_on_to_the_engine(self):
        fetch = SavedPages({SITE: "site-offer-today.html", ENGINE: "priced-es.html"})
        record, _ = reader.read_engine("Casa del Aljibe Inventada", SITE, TRIP, fetch,
                                       page_timeout_s=10, give_up_after_s=20, engines=[])
        self.assertEqual(fetch.requested, [SITE, ENGINE])
        self.assertEqual((record["kind"], record["source_url"], record["price_eur"]), ("engine_price", ENGINE, 160.0))

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


KNOWN = [
    {"name": "Motor Conocido", "hosts": ["motor-conocido.example"],
     "params": {"arrival": "{check_in}", "departure": "{check_out}"},
     "guests_param": None, "default_guests": 2, "verified": "2026-10-08"},
    {"name": "Motor Con Clave", "hosts": ["reservas.clave-demo.example"],
     "params": {"from": "{check_in:%d/%m/%Y}", "to": "{check_out:%d/%m/%Y}"},
     "guests_param": "adults", "default_guests": None, "verified": "2026-10-08"},
]
DATED = "https://motor-conocido.example/AbC9/?arrival=2026-11-20&departure=2026-11-22"


class KnownEngineTest(unittest.TestCase):
    def test_known_engine_link_gets_the_trip_dates(self):
        self.assertEqual(reader.dated_url("https://motor-conocido.example/AbC9/", TRIP, KNOWN), DATED)

    def test_other_parameters_stay_and_old_dates_are_replaced(self):
        url = "https://reservas.clave-demo.example/index?siteKey=x1&from=01/01/2026&adults=1&lang=es"
        self.assertEqual(reader.dated_url(url, TRIP, KNOWN),
                         "https://reservas.clave-demo.example/index?siteKey=x1&lang=es"
                         "&from=20/11/2026&to=22/11/2026&adults=2")

    def test_path_replace_swaps_the_start_page_for_the_results_page(self):
        table = [dict(KNOWN[1], path_replace=["/start.xhtml", "/result.xhtml"])]
        url = reader.dated_url("https://reservas.clave-demo.example/site/start.xhtml?siteKey=x1", TRIP, table)
        self.assertTrue(url.startswith("https://reservas.clave-demo.example/site/result.xhtml?siteKey=x1&"), url)

    def test_path_sets_the_engine_page_for_a_link_to_the_site_root(self):
        table = [dict(KNOWN[1], path="/en/hotel/demo")]
        url = reader.dated_url("https://reservas.clave-demo.example/", TRIP, table)
        self.assertTrue(url.startswith("https://reservas.clave-demo.example/en/hotel/demo?from="), url)

    def test_unknown_engine_is_left_alone(self):
        self.assertIsNone(reader.dated_url("https://reservas.motor-demo.example/casa-aljibe", TRIP, KNOWN))

    def test_engine_without_a_guests_parameter_is_used_only_for_its_default_guests(self):
        three = reader.Trip(TRIP.check_in, TRIP.check_out, 3)
        self.assertIsNone(reader.dated_url("https://motor-conocido.example/AbC9/", three, KNOWN))

    def test_site_link_to_a_known_engine_is_opened_with_the_dates(self):
        fetch = SavedPages({SITE: "site-known-engine.html", DATED: "priced-es.html"})
        record, refused = reader.read_engine("Casa del Aljibe Inventada", SITE, TRIP, fetch,
                                             page_timeout_s=10, give_up_after_s=20, engines=KNOWN)
        self.assertFalse(refused)
        self.assertEqual(fetch.requested, [SITE, DATED])
        self.assertEqual((record["kind"], record["source_url"]), ("engine_price", DATED))

    def test_start_url_on_a_known_engine_is_opened_with_the_dates(self):
        fetch = SavedPages({DATED: "priced-es.html"})
        record, _ = reader.read_engine("Casa del Aljibe Inventada", "https://motor-conocido.example/AbC9/", TRIP,
                                       fetch, page_timeout_s=10, give_up_after_s=20, engines=KNOWN)
        self.assertEqual(fetch.requested, [DATED])
        self.assertEqual(record["kind"], "engine_price")

    def test_the_users_engines_are_added_to_the_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "engines.json"
            local.write_text(json.dumps({"engines": [KNOWN[1]]}), encoding="utf-8")
            table = reader.load_engines([reader.ENGINES_FILE, local, Path(tmp) / "missing.json"])
        self.assertEqual(table[-1]["name"], "Motor Con Clave")
        self.assertEqual(len(table), len(reader.load_engines([reader.ENGINES_FILE])) + 1)

    def test_shipped_engine_table_is_well_formed(self):
        table = reader.load_engines([reader.ENGINES_FILE])
        self.assertTrue(table)
        for engine in table:
            with self.subTest(engine.get("name")):
                self.assertEqual(set(engine) - {"note", "path", "path_replace"},
                                 {"name", "hosts", "params", "guests_param", "default_guests", "verified"})
                self.assertTrue(engine["hosts"])
                date.fromisoformat(engine["verified"])
                url = f"https://{engine['hosts'][0]}/x/"
                guests = engine["default_guests"] or 2
                dated = reader.dated_url(url, reader.Trip(TRIP.check_in, TRIP.check_out, guests), table)
                page = f"https://{engine['hosts'][0]}{engine.get('path') or '/x/'}"
                self.assertTrue(dated and dated.startswith(page + "?"), dated)
                self.assertNotIn("{", dated)


class RedirectProbeTest(unittest.TestCase):
    def test_probe_reads_redirects_from_sites_with_an_incomplete_certificate_chain(self):
        # The probe only reads the status and Location header; the browser itself still checks
        # certificates when it opens the page. A real hotel site sent an incomplete chain.
        calls = []

        class Response:
            status, headers = 200, {}

            def dispose(self):
                pass

        class Request:
            def get(self, url, **kwargs):
                calls.append(kwargs)
                return Response()

        class Context:
            request = Request()

        fetcher = reader.BrowserFetcher(Context(), Exception)
        self.assertEqual(fetcher._probe("https://hotel.example/", 1000), (200, None))
        self.assertTrue(calls[0].get("ignore_https_errors"))
        self.assertEqual(calls[0].get("max_redirects"), 0)


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

    def test_calendar_legend_is_not_a_no_rooms_statement(self):
        for legend in ("× = No availability", "x = No hay disponibilidad", "■ = Nessuna disponibilità"):
            with self.subTest(legend):
                record = self.classify(self.DATES, legend, "Doble 140 €")
                self.assertEqual(record["kind"], "engine_price")

    def test_per_night_lines_in_four_languages(self):
        cases = ["175,50 € x 2 noches", "175,50 € × 2 notti", "175,50 € × 2 nuits", "175.50 € × 2 nights",
                 "175,50 € por noche", "175,50 €/noche", "€ 175,50 a notte", "175,50 € par nuit",
                 "EUR 175.50 per night", "175.50 €/night"]
        for line in cases:
            with self.subTest(line):
                record = self.classify(self.DATES, "351,00 €", line)
                self.assertEqual((record["price_eur"], record["price_basis"]), (175.5, "per_night"))
                self.assertEqual(record["quote"], line)

    def test_per_night_lines_for_another_stay_length_are_ignored(self):
        record = self.classify(self.DATES, "149.18 € × 6 nights", "175.50 € × 2 nights")
        self.assertEqual((record["price_eur"], record["price_basis"]), (175.5, "per_night"))

    def test_total_for_the_trip_nights_gives_the_per_night_price(self):
        for line in ("Total for 2 nights: €351.00", "Total: 351,00 €", "351,00 € para 2 noches", "Totale 351,00 €"):
            with self.subTest(line):
                record = self.classify(self.DATES, line)
                self.assertEqual((record["price_eur"], record["price_basis"]), (175.5, "per_night"))
                self.assertEqual(record["quote"], line)

    def test_total_for_another_stay_length_is_ignored(self):
        record = self.classify(self.DATES, "Total for 6 nights: €895.08", "Doble 160 €")
        self.assertEqual((record["price_eur"], record["price_basis"]), (160.0, "unknown"))

    def test_a_price_without_per_night_or_total_wording_has_an_unknown_basis(self):
        record = self.classify(self.DATES, "Doble 160 €")
        self.assertEqual((record["price_eur"], record["price_basis"]), (160.0, "unknown"))

    def test_other_sites_prices_are_not_the_hotels(self):
        record = self.classify(self.DATES, "Doble 160 €", "Booking.com:", "150 €", "Expedia: 140 €",
                               "Precio en Hotels.com 145 €")
        self.assertEqual(record["price_eur"], 160.0)
        self.assertEqual(record["quote"], "Doble 160 €")

    def test_amount_with_the_currency_and_night_on_the_next_line(self):
        record = self.classify(self.DATES, "217 €", "184", "EURnight", "194", "EURnight",
                               "Not included: City tax 9,24 EUR per person/night")
        self.assertEqual((record["price_eur"], record["price_basis"]), (184.0, "per_night"))
        self.assertEqual(record["quote"], "184 EURnight")

    def test_a_page_that_blocks_the_browser_says_so(self):
        for lines in (["403 ERROR", "The request could not be satisfied."], ["Access is temporarily restricted"],
                      ["Please complete the CAPTCHA to continue"]):
            with self.subTest(lines[0]):
                record = self.classify(*lines)
                self.assertEqual(record["kind"], "engine_unreadable")
                self.assertTrue(record["reason"].startswith("blocked"), record["reason"])

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
            "day range": ["20 - 22 Nov 2026"],
            "spanish day range": ["del 20 al 22 de noviembre de 2026"],
            "month first range without year": ["Nov 20-22"],
            "one part per line": ["Check in", "20", "Nov", "2026", "Check out", "22", "Nov", "2026"],
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

    def test_frames_without_a_body_do_not_stall_the_read(self):
        start = time.monotonic()
        record = self.read_live("svg-frames-en.html")
        self.assertLess(time.monotonic() - start, 8)  # the page timeout here is 10 s
        self.assertEqual((record["kind"], record["price_eur"], record["price_basis"]), ("engine_price", 144.0, "per_night"))

    def test_dates_in_the_search_boxes_of_a_framed_engine(self):
        record = self.read_live("framed-inputs-en.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual((record["dates_shown"]["check_in"], record["dates_shown"]["check_out"]),
                         ("2026-11-20", "2026-11-22"))
        self.assertEqual((record["price_eur"], record["price_basis"]), (240.0, "unknown"))

    def test_text_hidden_by_a_stylesheet_is_not_read(self):
        record = self.read_live("css-hidden-es.html")
        self.assertEqual(record["kind"], "engine_price")
        self.assertEqual(record["price_eur"], 160.0)


if __name__ == "__main__":
    unittest.main()
