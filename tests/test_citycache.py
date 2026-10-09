"""Tests for bin/citycache.py: read and update DATA/cities/{city-slug}.md (R3, R15).

All hotels and cities here are made up.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import citycache  # noqa: E402

LEGACY = """# Testgrad

*City slug: testgrad*
*Updated: 2025-06-01*

---

## Searched

<!-- One line per search/round: `YYYY-MM-DD R{N}: {query} → {outcome / file}` -->
2025-06-01 R1: Testgrad boutique → 3 picks

---

## Recommended

<!-- Active picks. Table: Name | Type | Area | Rating | Notes
| Hotel Foo Boutique | boutique | Old Town | 8.7 | LHW |
-->

| Name | Type | Area | Rating | Notes |
|---|---|---|---|---|
| Casa Velarta | boutique | Old Quarter | 9.0 | patio |
| | | | | |

---

## Mentioned section (researched, not selected)

| Name | Type | Source/Context | Date |
|---|---|---|---|
| Hotel Sombra | boutique | press | 2025-06 |

---

## Excluded (with reason)

<!-- e.g.
- Hotel Generic Chain — too corporate
-->
- Hotel Gris Plomo — too corporate (partner: "no personality")
- Hostal Ruido — обшарпанный, ремонт 2008 года

---

## Round 1 — partner rejected: too corporate

Picks: Hotel A, Hotel B
"""

SOURCES = [
    {"family": "curated-press", "outlet": "Testgrad Daily", "kind": "local press", "language": "es",
     "where": "https://testgrad-daily.example/", "yield": 5},
    {"family": "reddit", "outlet": "r/testgrad", "kind": "subreddit", "language": "en",
     "where": "https://www.reddit.com/r/testgrad/", "yield": 2},
    {"family": "booking-search", "outlet": "Booking", "kind": "booking-query", "language": "es",
     "where": "site:booking.com hotel con encanto Testgrad", "yield": 3},
]
STRUCK = [{"name": "Hotel Sombra", "reason": "dark rooms | no view", "date": "2026-10-09", "trip": "testgrad-2026-11"}]
PICKS = [{"name": "Casa Velarta", "type": "hotel", "area": "Old Quarter", "rating": "9.0",
          "notes": "2026-11: €175/night (testgrad-2026-11)"},
         {"name": "Palacio Ñandú", "type": "hotel", "area": "Old Quarter", "rating": "", "notes": "testgrad-2026-11"}]
SEARCHED = "2026-10-09 testgrad-2026-11: 2026-11-20 → 2026-11-22 · up to €200 → kept 2"


def update(text, **changes):
    args = dict(city="Testgrad", today="2026-10-09", run_id="testgrad-2026-11", searched=SEARCHED,
                sources=SOURCES, recommended=PICKS, struck=STRUCK)
    args.update(changes)
    return citycache.update(text, **args)


def headings(text: str) -> list:
    return [line[3:] for line in text.splitlines() if line.startswith("## ")]


class ReadTest(unittest.TestCase):
    def test_legacy_cache_reads_its_exclusions_and_picks(self):
        cache = citycache.parse(LEGACY)
        self.assertEqual([(e["name"], e["reason"]) for e in cache["excluded"]],
                         [("Hotel Gris Plomo", 'too corporate (partner: "no personality")'),
                          ("Hostal Ruido", "обшарпанный, ремонт 2008 года")])
        self.assertEqual([r["name"] for r in cache["recommended"]], ["Casa Velarta"])
        self.assertEqual(cache["sources"], [])
        self.assertEqual(cache["struck_out"], [])

    def test_slices_split_the_sources_by_family(self):
        cache = citycache.parse(update(None))
        slices = citycache.slices(cache["sources"])
        self.assertEqual([s["outlet"] for s in slices["curated-press"]], ["Testgrad Daily"])
        self.assertEqual(slices["curated-press"][0]["url"], "https://testgrad-daily.example/")
        self.assertEqual(slices["booking-search"][0]["query"], "site:booking.com hotel con encanto Testgrad")
        self.assertEqual(slices["reddit"][0]["kind"], "subreddit")

    def test_missing_file_reads_as_a_cold_city(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = citycache.read(Path(tmp) / "nowhere.md")
        self.assertFalse(cache["exists"])
        self.assertEqual(citycache.slices(cache["sources"]), {"curated-press": [], "reddit": [], "booking-search": []})


class UpdateTest(unittest.TestCase):
    def test_new_cache_has_the_canonical_sections(self):
        text = update(None)
        self.assertTrue(text.startswith("# Testgrad\n"))
        self.assertIn("Updated: 2026-10-09", text)
        self.assertEqual(headings(text), ["Searched", "Sources", "Recommended", "Struck out", "Excluded (with reason)"])
        cache = citycache.parse(text)
        self.assertEqual(len(cache["sources"]), 3)
        self.assertEqual(cache["struck_out"][0]["reason"], "dark rooms / no view")
        self.assertIn(SEARCHED, text)

    def test_legacy_sections_are_kept_and_new_ones_inserted(self):
        text = update(LEGACY)
        self.assertEqual(headings(text), ["Searched", "Sources", "Recommended", "Struck out",
                                          "Mentioned section (researched, not selected)", "Excluded (with reason)",
                                          "Round 1 — partner rejected: too corporate"])
        for kept in ("| Hotel Sombra | boutique | press | 2025-06 |", "- Hostal Ruido — обшарпанный, ремонт 2008 года",
                     "Picks: Hotel A, Hotel B", "2025-06-01 R1: Testgrad boutique → 3 picks",
                     "| Hotel Foo Boutique | boutique | Old Town | 8.7 | LHW |"):
            self.assertIn(kept, text)
        self.assertIn("*Updated: 2026-10-09*", text)
        self.assertNotIn("| | | | | |", text)
        cache = citycache.parse(text)
        self.assertEqual([r["name"] for r in cache["recommended"]], ["Casa Velarta", "Palacio Ñandú"])
        self.assertEqual(cache["recommended"][0]["notes"], "2026-11: €175/night (testgrad-2026-11)")
        self.assertEqual(len(cache["excluded"]), 2)

    def test_updating_twice_for_one_run_merges_rows_and_keeps_one_searched_line(self):
        first = update(None)
        changed = [dict(SOURCES[0], **{"yield": 7})] + SOURCES[1:] + [
            {"family": "curated-press", "outlet": "Revista Ejemplo", "kind": "city magazine", "language": "es",
             "where": "https://revista.example/", "yield": 1}]
        text = update(first, sources=changed, searched=SEARCHED.replace("kept 2", "kept 1"))
        cache = citycache.parse(text)
        daily = [s for s in cache["sources"] if s["outlet"] == "Testgrad Daily"]
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]["yield"], "7")
        self.assertEqual(len(cache["sources"]), 4)
        self.assertEqual(text.count("testgrad-2026-11:"), 1)
        self.assertIn("kept 1", text)
        self.assertEqual(len(cache["struck_out"]), 1)

    def test_repeated_writes_keep_the_layout_tidy(self):
        text = update(LEGACY)
        for n in range(3):
            text = update(text, run_id=f"testgrad-2027-0{n + 1}", searched=f"2027-0{n + 1}-01 testgrad-2027-0{n + 1}: x")
        self.assertNotIn("\n\n\n", text)
        searched = text.split("## Searched")[1].split("## ")[0]
        self.assertIn("- 2027-01-01 testgrad-2027-01: x\n- 2027-02-01 testgrad-2027-02: x", searched)

    def test_a_cache_copied_from_the_template_fills_in(self):
        template = (BIN.parent / "cities-template.md").read_text(encoding="utf-8").replace("{City Name}", "Testgrad")
        text = update(template)
        self.assertEqual(headings(text), ["Searched", "Sources", "Recommended", "Struck out", "Excluded (with reason)"])
        self.assertEqual(text.count("Updated: "), 1)
        self.assertIn("Updated: 2026-10-09", text)
        cache = citycache.parse(text)
        self.assertEqual(len(cache["sources"]), 3)
        self.assertEqual(cache["excluded"], [])
        self.assertIn("Hotel Generic Chain", text)  # the commented example stays a comment

    def test_a_later_trip_adds_its_own_struck_row(self):
        text = update(update(None), run_id="testgrad-2027-03", searched="2027-02-01 testgrad-2027-03: x",
                      struck=[dict(STRUCK[0], trip="testgrad-2027-03", reason="still dark")])
        self.assertEqual([r["trip"] for r in citycache.parse(text)["struck_out"]], ["testgrad-2026-11", "testgrad-2027-03"])

    def test_write_creates_the_cities_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cities" / "testgrad.md"
            citycache.write(path, city="Testgrad", today="2026-10-09", run_id="testgrad-2026-11", searched=SEARCHED,
                            sources=SOURCES, recommended=PICKS, struck=STRUCK)
            self.assertTrue(citycache.read(path)["exists"])

    def test_cli_read_prints_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "testgrad.md"
            path.write_text(LEGACY, encoding="utf-8")
            result = subprocess.run([sys.executable, str(BIN / "citycache.py"), "read", str(path)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["excluded"]), 2)


if __name__ == "__main__":
    unittest.main()
