"""Tests for bin/merge_candidates.py: one merged candidate file from every research family.

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
from runkit import BIN, edit_candidate, read_jsonl, score, write_json, write_jsonl  # noqa: E402

import merge_candidates  # noqa: E402
import runfiles  # noqa: E402


def merged_by_name(run: Path) -> dict:
    return {r["name"]: r for r in read_jsonl(run / "merged.jsonl")}


def find(run: Path, alias: str) -> dict:
    hits = [r for r in read_jsonl(run / "merged.jsonl") if alias in r["aliases"]]
    assert len(hits) == 1, (alias, hits)
    return hits[0]


class NameKeyTest(unittest.TestCase):
    def test_hotel_prefix_case_punctuation_and_accents_share_a_key(self):
        key = runfiles.name_key("Casa Velarta")
        for variant in ("Hotel Casa Velarta", "CASA VELARTA.", "Casa-Velarta", "Hôtel Casa Velarta", "Casa Velarta Hotel"):
            self.assertEqual(runfiles.name_key(variant), key, variant)
        self.assertEqual(runfiles.name_key("Palacio Ñandú"), runfiles.name_key("Palacio Nandu"))

    def test_different_names_keep_different_keys(self):
        self.assertNotEqual(runfiles.name_key("Casa Velarta"), runfiles.name_key("Casa Velarde"))


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_name_variants_merge_into_one_record_with_every_mention(self):
        merge_candidates.merge_run(self.run)
        velarta = find(self.run, "Hotel Casa Velarta")
        self.assertIn("Casa Velarta", velarta["aliases"])
        self.assertEqual(len(velarta["mentions"]), 2)
        self.assertEqual({m["family"] for m in velarta["mentions"]}, {"curated-press", "booking-search"})
        self.assertEqual(velarta["street"], "Calle del Pozo 4")
        self.assertTrue(velarta["booking_url"].startswith("https://www.booking.com/hotel/tg/casa-velarta.html"))

    def test_accent_variants_merge(self):
        merge_candidates.merge_run(self.run)
        nandu = find(self.run, "Palacio Nandu")
        self.assertIn("Palacio Ñandú", nandu["aliases"])
        self.assertEqual(len(nandu["mentions"]), 2)

    def test_booking_hotel_url_falls_back_to_a_booking_search_mention(self):
        merge_candidates.merge_run(self.run)
        self.assertEqual(find(self.run, "Palacio Nandu")["booking_url"], "https://www.booking.com/hotel/tg/palacio-nandu.html")
        self.assertEqual(find(self.run, "Carmen del Aljibe Rojo")["booking_url"], "")

    def test_every_candidate_appears_once(self):
        report = merge_candidates.merge_run(self.run)
        names = [r["name"] for r in read_jsonl(self.run / "merged.jsonl")]
        self.assertEqual(len(names), 13)
        self.assertEqual(report["merged"], 13)
        self.assertEqual(len({r["id"] for r in read_jsonl(self.run / "merged.jsonl")}), 13)

    def test_same_name_in_another_city_stays_separate(self):
        records = read_jsonl(self.run / "candidates-curated-press.jsonl")
        other = dict(records[0], city="Otherburg")
        write_jsonl(self.run / "candidates-curated-press.jsonl", records + [other])
        merge_candidates.merge_run(self.run)
        velartas = [r for r in read_jsonl(self.run / "merged.jsonl") if "Casa Velarta" in r["aliases"]]
        self.assertEqual(sorted(r["city"] for r in velartas), ["Otherburg", "Testgrad"])

    def test_local_name_links_two_records(self):
        records = read_jsonl(self.run / "candidates-reddit.jsonl")
        records.append({"name": "Velarta House", "local_name": "Casa Velarta", "kind": "hotel", "city": "Testgrad",
                        "mentions": [{"family": "reddit", "source_name": "r/testgrad",
                                      "url": "https://www.reddit.com/r/testgrad/comments/t3st09/x/c0mm09/",
                                      "language": "en", "quote": "Velarta House was lovely"}]})
        write_jsonl(self.run / "candidates-reddit.jsonl", records)
        merge_candidates.merge_run(self.run)
        velarta = find(self.run, "Velarta House")
        self.assertEqual(len(velarta["mentions"]), 3)

    def test_booking_only_flag_when_every_mention_is_booking_search(self):
        merge_candidates.merge_run(self.run)
        lunar = find(self.run, "El Patio Lunar")
        self.assertTrue(lunar["booking_only"])
        self.assertIn("booking_only", lunar["flags"])
        velarta = find(self.run, "Casa Velarta")
        self.assertFalse(velarta["booking_only"])
        self.assertNotIn("booking_only", velarta["flags"])

    def test_equal_scores_in_different_notation_are_verified(self):
        merge_candidates.merge_run(self.run)
        velarta = find(self.run, "Casa Velarta")
        self.assertEqual(velarta["score"], {"value": 9.0, "verified": True, "why": ""})
        self.assertNotIn("score_unverified", velarta["flags"])

    def test_two_different_booking_scores_make_the_score_unverified(self):
        merge_candidates.merge_run(self.run)
        sombra = find(self.run, "Hotel Sombra")
        self.assertFalse(sombra["score"]["verified"])
        self.assertIsNone(sombra["score"]["value"])
        self.assertIn("8.4", sombra["score"]["why"])
        self.assertIn("8.9", sombra["score"]["why"])
        self.assertIn("score_unverified", sombra["flags"])

    def test_any_discrepancy_counts(self):
        edit_candidate(self.run, "booking-search", "Hotel Casa Velarta", booking_score=score("9.1"))
        merge_candidates.merge_run(self.run)
        self.assertFalse(find(self.run, "Casa Velarta")["score"]["verified"])

    def test_review_counts_are_not_compared(self):
        velarta_score = dict(score("9.0"), reviews=655)
        edit_candidate(self.run, "booking-search", "Hotel Casa Velarta", booking_score=velarta_score)
        merge_candidates.merge_run(self.run)
        self.assertTrue(find(self.run, "Casa Velarta")["score"]["verified"])

    def test_no_score_is_unverified(self):
        merge_candidates.merge_run(self.run)
        carmen = find(self.run, "Carmen del Aljibe Rojo")
        self.assertFalse(carmen["score"]["verified"])
        self.assertIn("score_unverified", carmen["flags"])

    def test_unreadable_score_is_unverified(self):
        edit_candidate(self.run, "reddit", "Grandchain Testgrad Centro", booking_score=score("Superb"))
        merge_candidates.merge_run(self.run)
        self.assertFalse(find(self.run, "Grandchain Testgrad Centro")["score"]["verified"])

    def test_lines_the_ledger_rejects_are_reported_and_left_out(self):
        path = self.run / "candidates-booking-search.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps({"name": "Hotel Listicle", "kind": "hotel", "city": "Testgrad", "mentions": [
            {"family": "booking-search", "url": "https://www.tripadvisor.com/Hotel_Review-1", "quote": "Top 10"}]}))
        lines.append("{not json")
        lines.append(json.dumps({"name": "Hotel Rumor", "kind": "hotel", "city": "Testgrad", "mentions": [
            {"family": "reddit", "url": "https://www.reddit.com/r/testgrad/", "quote": "heard of it"}]}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = merge_candidates.merge_run(self.run)
        rejected = {(r["file"], r["line"]) for r in report["rejected"]}
        self.assertEqual(rejected, {("candidates-booking-search.jsonl", 6), ("candidates-booking-search.jsonl", 7),
                                    ("candidates-booking-search.jsonl", 8)})
        names = {a for r in read_jsonl(self.run / "merged.jsonl") for a in r["aliases"]}
        self.assertNotIn("Hotel Listicle", names)
        self.assertNotIn("Hotel Rumor", names)

    def test_close_pairs_are_reported_not_merged(self):
        records = read_jsonl(self.run / "candidates-curated-press.jsonl")
        records.append({"name": "Patio Lunar", "kind": "hotel", "city": "Testgrad", "mentions": [
            {"family": "curated-press", "source_name": "Testgrad Daily", "url": "https://testgrad-daily.example/x",
             "language": "es", "quote": "el Patio Lunar"}]})
        write_jsonl(self.run / "candidates-curated-press.jsonl", records)
        report = merge_candidates.merge_run(self.run)
        pairs = [sorted(c["names"]) for c in report["close_calls"]]
        self.assertIn(["El Patio Lunar", "Patio Lunar"], pairs)
        self.assertEqual(len(read_jsonl(self.run / "merged.jsonl")), 14)

    def test_the_model_resolves_a_close_pair_through_merge_decisions(self):
        records = read_jsonl(self.run / "candidates-curated-press.jsonl")
        records.append({"name": "Patio Lunar", "kind": "hotel", "city": "Testgrad", "mentions": [
            {"family": "curated-press", "source_name": "Testgrad Daily", "url": "https://testgrad-daily.example/x",
             "language": "es", "quote": "el Patio Lunar"}]})
        write_jsonl(self.run / "candidates-curated-press.jsonl", records)
        write_json(self.run / "merge-decisions.json", {"same": [["El Patio Lunar", "Patio Lunar"]]})
        report = merge_candidates.merge_run(self.run)
        self.assertEqual(report["close_calls"], [])
        lunar = find(self.run, "Patio Lunar")
        self.assertIn("El Patio Lunar", lunar["aliases"])
        self.assertFalse(lunar["booking_only"])

    def test_kind_disagreement_is_reported(self):
        edit_candidate(self.run, "booking-search", "Hotel Casa Velarta", kind="apartment")
        report = merge_candidates.merge_run(self.run)
        self.assertEqual([c["name"] for c in report["kind_conflicts"]], ["Casa Velarta"])

    def test_cli_writes_the_merged_file_and_prints_the_report(self):
        result = subprocess.run([sys.executable, str(BIN / "merge_candidates.py"), str(self.run)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["merged"], 13)
        self.assertTrue((self.run / "merged.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
