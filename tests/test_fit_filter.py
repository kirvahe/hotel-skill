"""Tests for bin/fit_filter.py: the profile's hard rules, applied mechanically.

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
from runkit import BIN, edit_candidate, pet, read_json, score, write_json  # noqa: E402

import fit_filter  # noqa: E402
import merge_candidates  # noqa: E402
import runfiles  # noqa: E402


class FitFilterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def filtered(self) -> dict:
        merge_candidates.merge_run(self.run)
        fit_filter.filter_run(self.run)
        fit = read_json(self.run / "fit.json")
        return {c["name"]: c for c in fit["candidates"]}

    def set_rules(self, **changes):
        rules = read_json(self.run / "fit-rules.json")
        rules.update(changes)
        write_json(self.run / "fit-rules.json", rules)

    def set_dog(self, dog: bool):
        trip = read_json(self.run / "trip.json")
        trip["dog"] = dog
        write_json(self.run / "trip.json", trip)

    # AE4
    def test_booking_only_candidate_passes_with_its_flag(self):
        lunar = self.filtered()["El Patio Lunar"]
        self.assertEqual(lunar["decision"], "keep")
        self.assertIn("booking_only", lunar["flags"])

    # AE5
    def test_dog_at_home_skips_the_pet_rule(self):
        edit_candidate(self.run, "curated-press", "Hotel Sombra", pet_policy=pet("not allowed"))
        result = self.filtered()
        self.assertEqual(result["Hotel Sombra"]["decision"], "keep")
        self.assertFalse(any("pet_unknown" in c["flags"] for c in result.values()))

    def test_dog_travels_removes_not_allowed_and_flags_unknown(self):
        self.set_dog(True)
        edit_candidate(self.run, "curated-press", "Hotel Sombra", pet_policy=pet("not allowed"))
        edit_candidate(self.run, "curated-press", "Casa Velarta", pet_policy=pet("allowed"))
        result = self.filtered()
        self.assertEqual(result["Hotel Sombra"]["decision"], "remove")
        self.assertEqual(result["Hotel Sombra"]["reason_code"], "pet_not_allowed")
        self.assertEqual(result["Casa Velarta"]["decision"], "keep")
        self.assertNotIn("pet_unknown", result["Casa Velarta"]["flags"])
        self.assertEqual(result["Hotel Otoño"]["decision"], "keep")
        self.assertIn("pet_unknown", result["Hotel Otoño"]["flags"])

    def test_conflicting_pet_sources_are_unknown_not_removed(self):
        self.set_dog(True)
        edit_candidate(self.run, "curated-press", "Casa Velarta", pet_policy=pet("allowed"))
        edit_candidate(self.run, "booking-search", "Hotel Casa Velarta", pet_policy=pet("not allowed"))
        velarta = self.filtered()["Casa Velarta"]
        self.assertEqual(velarta["decision"], "keep")
        self.assertIn("pet_unknown", velarta["flags"])

    # R9 floor and AE9
    def test_verified_score_below_the_floor_is_removed(self):
        gris = self.filtered()["Hostería Gris"]
        self.assertEqual(gris["decision"], "remove")
        self.assertEqual(gris["reason_code"], "below_floor")

    def test_limited_choice_city_keeps_a_7_6_with_the_below_floor_flag(self):
        self.set_rules(limited_choice=True)
        gris = self.filtered()["Hostería Gris"]
        self.assertEqual(gris["decision"], "keep")
        self.assertIn("below_floor", gris["flags"])

    def test_an_unverified_score_never_removes(self):
        edit_candidate(self.run, "curated-press", "Hotel Sombra", booking_score=score("7.2"))
        sombra = self.filtered()["Hotel Sombra"]
        self.assertEqual(sombra["decision"], "keep")
        self.assertIn("score_unverified", sombra["flags"])
        self.assertNotIn("below_floor", sombra["flags"])

    def test_no_score_never_removes(self):
        edit_candidate(self.run, "reddit", "Grandchain Testgrad Centro", booking_score=None)
        self.set_rules(do_not_recommend=[])
        grand = self.filtered()["Grandchain Testgrad Centro"]
        self.assertEqual(grand["decision"], "keep")
        self.assertIn("score_unverified", grand["flags"])

    # R9 blacklist
    def test_blacklisted_hotel_in_the_same_city_is_removed_with_a_skip_line(self):
        ceniza = self.filtered()["Hotel Ceniza"]
        self.assertEqual(ceniza["decision"], "remove")
        self.assertEqual(ceniza["reason_code"], "blacklist")
        self.assertEqual(ceniza["skip_line"], "Skipped: blacklist — Hotel Ceniza — no soul, like an office")

    def test_blacklist_entry_for_another_city_does_not_remove(self):
        nandu = self.filtered()["Palacio Ñandú"]
        self.assertEqual(nandu["decision"], "keep")

    # R9 and R10 do-not-recommend chains
    def test_named_do_not_recommend_chain_is_removed_with_a_skip_line(self):
        grand = self.filtered()["Grandchain Testgrad Centro"]
        self.assertEqual(grand["decision"], "remove")
        self.assertEqual(grand["reason_code"], "dnr_chain")
        self.assertIn("Skipped:", grand["skip_line"])
        self.assertIn("Grandchain Testgrad Centro", grand["skip_line"])

    def test_chain_not_named_in_do_not_recommend_passes(self):
        self.set_rules(do_not_recommend=["Room Mate"])
        self.assertEqual(self.filtered()["Grandchain Testgrad Centro"]["decision"], "keep")

    def test_chain_name_matches_whole_words_only(self):
        self.set_rules(do_not_recommend=["Grand"])
        self.assertEqual(self.filtered()["Grandchain Testgrad Centro"]["decision"], "keep")

    # R10 past stays
    def test_previously_stayed_hotel_carries_its_past_ratings(self):
        result = self.filtered()
        marquesa = result["Hotel Marquesa Vieja"]
        self.assertEqual(marquesa["decision"], "keep")
        self.assertEqual([s["rating"] for s in marquesa["past_stays"]], ["7-8", "8.5"])
        self.assertEqual([s["date"] for s in marquesa["past_stays"]], ["~Mar 2024", "2025-10-03"])
        self.assertEqual(result["Casa Velarta"]["past_stays"], [])

    # R19 kinds
    def test_apartments_leave_the_hotel_list(self):
        lirio = self.filtered()["Apartamentos Lirio"]
        self.assertEqual(lirio["decision"], "remove")
        self.assertEqual(lirio["reason_code"], "excluded_kind")

    def test_special_formats_go_to_the_airbnb_block_without_a_floor(self):
        edit_candidate(self.run, "curated-press", "Carmen del Aljibe Rojo", booking_score=score("7.0"))
        carmen = self.filtered()["Carmen del Aljibe Rojo"]
        self.assertEqual(carmen["decision"], "keep")
        self.assertEqual(carmen["block"], "airbnb")
        self.assertNotIn("below_floor", carmen["flags"])

    def test_hotels_stay_in_the_hotel_block(self):
        self.assertEqual(self.filtered()["Casa Velarta"]["block"], "hotels")

    def test_every_removal_carries_a_reason_code_and_a_skip_line(self):
        removed = [c for c in self.filtered().values() if c["decision"] == "remove"]
        self.assertEqual({c["name"] for c in removed},
                         {"Hotel Ceniza", "Grandchain Testgrad Centro", "Apartamentos Lirio", "Hostería Gris"})
        for c in removed:
            self.assertIn(c["reason_code"], fit_filter.REASON_CODES)
            self.assertTrue(c["skip_line"].startswith("Skipped: "), c)

    # inputs
    def test_missing_fit_rules_is_a_clear_error(self):
        merge_candidates.merge_run(self.run)
        (self.run / "fit-rules.json").unlink()
        with self.assertRaises(runfiles.RunError) as ctx:
            fit_filter.filter_run(self.run)
        self.assertIn("fit-rules.json", str(ctx.exception))

    def test_missing_blacklist_is_a_clear_error(self):
        merge_candidates.merge_run(self.run)
        (self.run / "blacklist.json").unlink()
        with self.assertRaises(runfiles.RunError) as ctx:
            fit_filter.filter_run(self.run)
        self.assertIn("blacklist.py", str(ctx.exception))

    def test_unknown_excluded_kind_is_a_clear_error(self):
        merge_candidates.merge_run(self.run)
        self.set_rules(excluded_kinds=["apartments"])
        with self.assertRaises(runfiles.RunError):
            fit_filter.filter_run(self.run)

    def test_cli_prints_skip_lines(self):
        merge_candidates.merge_run(self.run)
        result = subprocess.run([sys.executable, str(BIN / "fit_filter.py"), str(self.run)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIn("Skipped: blacklist — Hotel Ceniza — no soul, like an office", out["skip_lines"])

    def test_cli_reports_a_missing_input_with_exit_2(self):
        result = subprocess.run([sys.executable, str(BIN / "fit_filter.py"), str(self.run)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("merged.jsonl", result.stderr)


if __name__ == "__main__":
    unittest.main()
