"""Tests for bin/check_output.py: compare a rendered answer with the run ledger.

All hotels here are made up (see tests/fixtures/pipeline/runkit.py).
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pipeline"
sys.path.insert(0, str(FIXTURES))

import runkit  # noqa: E402
from runkit import BIN, read_json, write_json  # noqa: E402

import check_output  # noqa: E402
import render  # noqa: E402

EN = render.LABELS["en"]
LINKS = ("   [Booking](https://www.booking.com/searchresults.html?ss=X) · "
         "[Google Maps](https://www.google.com/maps/search/?api=1&query=X)")


def add_entry(text: str, line: str) -> str:
    heading = f"### {EN['hotels']}\n"
    assert heading in text
    return text.replace(heading, heading + line + "\n" + LINKS + "\n", 1)


class CheckOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def answer(self) -> str:
        runkit.pipeline(self.run)
        return render.render_answer(self.run, "en")

    def test_rendered_answer_passes(self):
        self.assertEqual(check_output.check(self.run, self.answer()), [])

    def test_rendered_russian_answer_passes(self):
        runkit.pipeline(self.run)
        self.assertEqual(check_output.check(self.run, render.render_answer(self.run, "ru")), [])

    def test_blacklisted_hotel_fails(self):
        text = add_entry(self.answer(), "20. **Hotel Ceniza** — Station — €140")
        failures = check_output.check(self.run, text)
        self.assertTrue(any("blacklist" in f and "Hotel Ceniza" in f for f in failures), failures)

    def test_blacklisted_name_variant_fails(self):
        text = add_entry(self.answer(), "20. **Ceniza** — Station")
        self.assertTrue(any("blacklist" in f for f in check_output.check(self.run, text)))

    def test_skip_line_naming_a_blacklisted_hotel_is_fine(self):
        text = self.answer()
        self.assertIn("Skipped: blacklist — Hotel Ceniza", text)
        self.assertEqual(check_output.check(self.run, text), [])

    def test_below_floor_hotel_outside_a_limited_choice_city_fails(self):
        text = add_entry(self.answer(), "20. **Hostería Gris** — Station — €120")
        failures = check_output.check(self.run, text)
        self.assertTrue(any("floor" in f and "Hostería Gris" in f for f in failures), failures)

    def test_below_floor_hotel_in_a_limited_choice_city_passes(self):
        rules = read_json(self.run / "fit-rules.json")
        rules["limited_choice"] = True
        write_json(self.run / "fit-rules.json", rules)
        text = self.answer()
        self.assertIn("**Hostería Gris**", text)
        self.assertEqual(check_output.check(self.run, text), [])

    def test_entry_without_a_maps_link_fails(self):
        text = self.answer()
        text = re.sub(r"( · )?\[Google Maps\]\(https://www\.google\.com/maps/search/\?api=1&query=Casa[^)]*\)", "", text)
        failures = check_output.check(self.run, text)
        self.assertTrue(any("Casa Velarta" in f and "Maps" in f for f in failures), failures)

    def test_entry_without_a_booking_link_fails(self):
        text = add_entry(self.answer(), "20. **Hotel Otoño**").replace(
            "[Booking](https://www.booking.com/searchresults.html?ss=X) · ", "")
        failures = check_output.check(self.run, text)
        self.assertTrue(any("Hotel Otoño" in f and "Booking" in f for f in failures), failures)

    def test_airbnb_entry_without_dates_not_verified_fails(self):
        text = self.answer().replace(EN["dates_not_verified"], "")
        failures = check_output.check(self.run, text)
        self.assertTrue(any("Carmen del Aljibe Rojo" in f for f in failures), failures)

    def test_hotel_missing_from_the_ledger_fails(self):
        text = add_entry(self.answer(), "20. **Hotel Fantasma**")
        failures = check_output.check(self.run, text)
        self.assertTrue(any("Hotel Fantasma" in f and "ledger" in f for f in failures), failures)

    # R22: every family and module carries a status, and the answer shows them
    def test_a_family_without_a_status_fails(self):
        families = read_json(self.run / "families.json")
        del families["families"]["reddit"]
        write_json(self.run / "families.json", families)
        failures = check_output.check(self.run, self.answer())
        self.assertIn("no status for research family reddit (R22)", failures)

    def test_a_module_without_a_status_fails(self):
        (self.run / "modules.json").unlink()
        failures = check_output.check(self.run, self.answer())
        self.assertIn("no status for module gmail (R22)", failures)

    def test_an_answer_without_the_checks_report_fails(self):
        text = self.answer()
        cut = text.index(f"### {EN['report']}")
        failures = check_output.check(self.run, text[:cut])
        self.assertIn("the answer has no checks report (R22)", failures)

    def test_cli_exit_codes(self):
        good = self.answer()
        bad = add_entry(good, "20. **Hotel Ceniza**")
        for text, code in ((good, 0), (bad, 1)):
            path = Path(self.tmp.name) / "answer.md"
            path.write_text(text, encoding="utf-8")
            result = subprocess.run([sys.executable, str(BIN / "check_output.py"), str(self.run), str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
