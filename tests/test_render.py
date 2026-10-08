"""Tests for bin/render.py: the shortlist and the final answer, rendered from the run ledger.

All hotels here are made up (see tests/fixtures/pipeline/runkit.py).
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pipeline"
sys.path.insert(0, str(FIXTURES))

import runkit  # noqa: E402
from runkit import BIN, read_json, read_jsonl, score, write_json, write_jsonl  # noqa: E402

import render  # noqa: E402

ENTRY = re.compile(r"^(\d+)\. \*\*(.+?)\*\*", re.MULTILINE)
EN = render.LABELS["en"]


def entries(text: str) -> dict:
    """name -> number for every numbered entry."""
    return {name: int(number) for number, name in ENTRY.findall(text)}


def sections(text: str) -> dict:
    """### heading -> body text."""
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith("### "):
            current = line[4:].strip()
            out[current] = ""
        elif current is not None:
            out[current] += line + "\n"
    return out


def block(text: str, name: str) -> str:
    """The lines of one entry: its numbered line and the indented lines under it."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"^\d+\. \*\*{re.escape(name)}\*\*", line))
    out = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith("   "):
            break
        out.append(line)
    return "\n".join(out)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ready(self):
        runkit.pipeline(self.run)

    # R14 stable numbers
    def test_question_options_and_plain_list_carry_the_same_numbers(self):
        self.ready()
        text = render.render_shortlist(self.run, "en")
        options = render.question_options(self.run, "en")
        listed = entries(text)
        self.assertEqual({o["label"].split(". ", 1)[1]: o["number"] for o in options}, listed)
        for option in options:
            self.assertTrue(option["label"].startswith(f"{option['number']}. "))
        self.assertEqual(sorted(listed.values()), list(range(1, len(listed) + 1)))

    def test_numbers_are_stable_across_renders_and_into_the_answer(self):
        self.ready()
        first = entries(render.render_shortlist(self.run, "en"))
        second = entries(render.render_shortlist(self.run, "ru"))
        answer = entries(render.render_answer(self.run, "en"))
        self.assertEqual(first, second)
        self.assertEqual(first, answer)
        self.assertEqual(read_json(self.run / "numbers.json")["numbers"][read_jsonl(self.run / "merged.jsonl")[0]["id"]],
                         first["Casa Velarta"])

    # R14 flags
    def test_shortlist_shows_price_and_flags(self):
        self.ready()
        text = render.render_shortlist(self.run, "en")
        self.assertIn("€160", block(text, "Casa Velarta"))
        self.assertIn(EN["flag_booking_only"], block(text, "El Patio Lunar"))
        self.assertIn(EN["flag_score_unverified"], block(text, "Hotel Sombra"))
        self.assertIn("❓", block(text, "Palacio Ñandú"))
        self.assertNotIn("❓", block(text, "Casa Velarta"))
        marquesa = block(text, "Hotel Marquesa Vieja")
        self.assertIn("7-8", marquesa)
        self.assertIn("8.5", marquesa)

    def test_below_floor_and_pet_flags(self):
        rules = read_json(self.run / "fit-rules.json")
        rules["limited_choice"] = True
        write_json(self.run / "fit-rules.json", rules)
        trip = read_json(self.run / "trip.json")
        trip["dog"] = True
        write_json(self.run / "trip.json", trip)
        self.ready()
        text = render.render_shortlist(self.run, "en")
        self.assertIn(EN["flag_below_floor"].format(floor="8.0"), block(text, "Hostería Gris"))
        self.assertIn(EN["flag_pet_unknown"], block(text, "Hotel Otoño"))

    def test_unavailable_and_removed_hotels_are_not_entries_but_have_skip_lines(self):
        self.ready()
        text = render.render_shortlist(self.run, "en")
        listed = entries(text)
        for name in ("Hotel Invierno", "Hotel Ceniza", "Grandchain Testgrad Centro", "Apartamentos Lirio", "Hostería Gris"):
            self.assertNotIn(name, listed)
        self.assertIn("Skipped: blacklist — Hotel Ceniza — no soul, like an office", text)
        self.assertIn("Hotel Invierno", sections(text)[EN["skipped"]])

    # R25 and AE11
    def test_over_budget_hotel_without_a_verdict_does_not_appear(self):
        self.ready()
        for text in (render.render_shortlist(self.run, "en"), render.render_answer(self.run, "en")):
            self.assertNotIn("Hotel Torre Alta", text)
            self.assertNotIn(EN["beyond_budget"], text)

    def test_over_budget_hotel_with_a_clearly_better_verdict_is_only_in_the_beyond_budget_group(self):
        write_json(self.run / "verdicts.json", {"clearly_better": [
            {"candidate": "Hotel Torre Alta", "reason": "the only one with a valley view from every room"}]})
        self.ready()
        for text in (render.render_shortlist(self.run, "en"), render.render_answer(self.run, "en")):
            parts = sections(text)
            self.assertIn("Hotel Torre Alta", parts[EN["beyond_budget"]])
            self.assertIn("valley view", parts[EN["beyond_budget"]])
            self.assertNotIn("Hotel Torre Alta", parts[EN["hotels"]])
            self.assertIn("€290", block(text, "Hotel Torre Alta"))

    def test_candidate_without_a_price_is_not_judged_against_the_budget(self):
        trip = read_json(self.run / "trip.json")
        trip["budget"]["max"] = 100
        write_json(self.run / "trip.json", trip)
        self.ready()
        text = render.render_shortlist(self.run, "en")
        self.assertIn("Palacio Ñandú", sections(text)[EN["hotels"]])
        self.assertIn("❓", block(text, "Palacio Ñandú"))
        self.assertNotIn("Casa Velarta", entries(text))

    def test_price_of_unclear_basis_is_marked_and_judged_as_a_stay_total_at_most(self):
        # 300 might be the 2-night total (150 a night) or the nightly price: the hotel stays in for
        # the user to check, marked as unclear, rather than being dropped as over budget.
        evidence = read_jsonl(self.run / "evidence.jsonl")
        for record in evidence:
            if record["candidate"] == "Casa Velarta" and record["kind"] == "engine_price":
                record.update(price_eur=300, price_basis="unknown")
        write_jsonl(self.run / "evidence.jsonl", evidence)
        self.ready()
        text = render.render_shortlist(self.run, "en")
        self.assertIn("Casa Velarta", sections(text)[EN["hotels"]])
        self.assertIn(EN["price_unclear"].format(price="€300"), block(text, "Casa Velarta"))
        self.assertNotIn(EN["per_night"].format(price="€300"), text)

    # R19 and AE7
    def test_special_format_is_in_the_airbnb_block_with_a_dated_link(self):
        self.ready()
        text = render.render_answer(self.run, "en")
        parts = sections(text)
        self.assertIn("Carmen del Aljibe Rojo", parts[EN["airbnb"]])
        self.assertNotIn("Carmen del Aljibe Rojo", parts[EN["hotels"]])
        carmen = block(text, "Carmen del Aljibe Rojo")
        self.assertIn(EN["dates_not_verified"], carmen)
        airbnb_url = re.search(r"\((https://www\.airbnb\.com/[^)]+)\)", carmen).group(1)
        q = parse_qs(urlparse(airbnb_url).query)
        self.assertEqual((q["checkin"][0], q["checkout"][0]), ("2026-11-20", "2026-11-22"))

    # R16 in the answer
    def test_answer_entries_carry_booking_and_maps_links(self):
        self.ready()
        text = render.render_answer(self.run, "en")
        velarta = block(text, "Casa Velarta")
        self.assertIn("https://www.booking.com/hotel/tg/casa-velarta.html?checkin=2026-11-20", velarta)
        self.assertIn("https://www.google.com/maps/search/?api=1", velarta)

    # R17 and AE6
    def test_everything_below_the_floor_names_what_to_relax(self):
        for family in ("curated-press", "reddit", "booking-search"):
            path = self.run / f"candidates-{family}.jsonl"
            records = [dict(r, booking_score=score("7.0")) for r in read_jsonl(path) if r["kind"] != "special-format"]
            write_jsonl(path, records)
        self.ready()
        for text in (render.render_shortlist(self.run, "en"), render.render_answer(self.run, "en")):
            self.assertEqual(entries(text), {})
            self.assertIn(EN["nothing_fits"], text)
            self.assertIn(EN["relax_district"], text)
            self.assertIn(EN["reason_below_floor"].format(floor="8.0"), text)

    def test_everything_over_budget_suggests_a_higher_budget(self):
        for family in ("curated-press", "reddit", "booking-search"):
            path = self.run / f"candidates-{family}.jsonl"
            keep = [r for r in read_jsonl(path) if r["name"] in ("Casa Velarta", "Hotel Casa Velarta", "Hotel Torre Alta")]
            write_jsonl(path, keep)
        trip = read_json(self.run / "trip.json")
        trip["budget"]["max"] = 100
        write_json(self.run / "trip.json", trip)
        self.ready()
        text = render.render_answer(self.run, "en")
        self.assertEqual(entries(text), {})
        self.assertIn(EN["relax_budget"], text)
        self.assertIn(EN["lowest_price"].format(price="€160"), text)
        self.assertNotIn(EN["relax_dates"], text)

    # R20
    def test_russian_labels(self):
        self.ready()
        ru = render.LABELS["ru"]
        shortlist = render.render_shortlist(self.run, "ru")
        answer = render.render_answer(self.run, "ru")
        self.assertIn(ru["hotels"], sections(answer))
        self.assertIn(ru["flag_booking_only"], block(shortlist, "El Patio Lunar"))
        self.assertIn(ru["dates_not_verified"], block(answer, "Carmen del Aljibe Rojo"))
        self.assertNotIn(EN["hotels"], sections(answer))

    def test_every_language_has_every_label(self):
        for lang, labels in render.LABELS.items():
            self.assertEqual(set(labels), set(EN), lang)

    def test_unknown_language_falls_back_to_english_with_a_visible_note(self):
        self.ready()
        text = render.render_shortlist(self.run, "de")
        self.assertIn(EN["hotels"], sections(text))
        self.assertIn(render.FALLBACK_NOTE.format(lang="de"), text)
        self.assertNotIn(render.FALLBACK_NOTE.format(lang="en"), render.render_shortlist(self.run, "en"))

    def test_same_layout_every_run(self):
        self.ready()
        self.assertEqual(render.render_answer(self.run, "en"), render.render_answer(self.run, "en"))

    def test_cli_renders_shortlist_options_and_answer(self):
        self.ready()
        for args in (["shortlist"], ["options"], ["answer", "--lang", "ru"]):
            result = subprocess.run([sys.executable, str(BIN / "render.py"), *args, str(self.run)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Casa Velarta", result.stdout)


if __name__ == "__main__":
    unittest.main()
