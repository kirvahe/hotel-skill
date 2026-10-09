"""Tests for bin/runfiles.py: run-file names and the evidence merge.

All hotels here are made up (see tests/fixtures/pipeline/runkit.py).
"""
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pipeline"
sys.path.insert(0, str(FIXTURES))

import runkit  # noqa: E402
from runkit import read_jsonl, write_jsonl  # noqa: E402

import runfiles  # noqa: E402

CLOSURE = {"candidate": "Hotel Invierno", "kind": "closure", "source_url": "https://hotelinvierno.example/noticias",
           "quote": "Cerrado por temporada desde el 21 de noviembre", "read_at": "2026-10-09T10:00:00+00:00",
           "closed_from": "2026-11-21"}
PRICE = {"candidate": "Casa Velarta", "kind": "engine_price", "source_url": "https://casavelarta.example/book",
         "quote": "Doble 175 € por noche", "read_at": "2026-10-09T11:00:00+00:00", "price_eur": 175,
         "dates_shown": {"check_in": "2026-11-20", "check_out": "2026-11-22"}}


class MergeEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)
        self.before = read_jsonl(self.run / "evidence.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_per_agent_files_are_merged_into_evidence_jsonl(self):
        write_jsonl(self.run / "evidence-resolver-1.jsonl", [CLOSURE])
        write_jsonl(self.run / "evidence-final-1.jsonl", [PRICE])
        report = runfiles.merge_evidence(self.run)
        merged = read_jsonl(self.run / "evidence.jsonl")
        self.assertEqual(len(merged), len(self.before) + 2)
        self.assertIn(CLOSURE, merged)
        self.assertIn(PRICE, merged)
        self.assertEqual(report["added"], 2)
        self.assertEqual(sorted(report["files"]), ["evidence-final-1.jsonl", "evidence-resolver-1.jsonl"])

    def test_merging_twice_adds_nothing(self):
        write_jsonl(self.run / "evidence-resolver-1.jsonl", [CLOSURE, CLOSURE])
        runfiles.merge_evidence(self.run)
        report = runfiles.merge_evidence(self.run)
        self.assertEqual(report["added"], 0)
        self.assertEqual(read_jsonl(self.run / "evidence.jsonl").count(CLOSURE), 1)

    def test_invalid_lines_are_reported_and_left_out(self):
        bad = dict(CLOSURE, quote="")
        (self.run / "evidence-resolver-2.jsonl").write_text(
            '{"not json\n' + __import__("json").dumps(bad) + "\n", encoding="utf-8")
        report = runfiles.merge_evidence(self.run)
        self.assertEqual([(r["file"], r["line"]) for r in report["rejected"]],
                         [("evidence-resolver-2.jsonl", 1), ("evidence-resolver-2.jsonl", 2)])
        self.assertNotIn(bad, read_jsonl(self.run / "evidence.jsonl"))

    def test_a_line_that_is_not_an_object_is_rejected_not_a_crash(self):
        (self.run / "evidence-resolver-3.jsonl").write_text("[1]\n5\n", encoding="utf-8")
        report = runfiles.merge_evidence(self.run)
        self.assertEqual(report["rejected"], [
            {"file": "evidence-resolver-3.jsonl", "line": 1, "problems": ["not a JSON object"]},
            {"file": "evidence-resolver-3.jsonl", "line": 2, "problems": ["not a JSON object"]}])
        self.assertEqual(read_jsonl(self.run / "evidence.jsonl"), self.before)

    def test_without_an_evidence_file_the_merge_creates_one(self):
        (self.run / "evidence.jsonl").unlink()
        write_jsonl(self.run / "evidence-reader.jsonl", [PRICE])
        runfiles.merge_evidence(self.run)
        self.assertEqual(read_jsonl(self.run / "evidence.jsonl"), [PRICE])


class MatchByNameTest(unittest.TestCase):
    def test_records_reach_the_candidate_by_any_name_variant(self):
        merged = [{"id": "casa-velarta", "name": "Casa Velarta", "aliases": ["Casa Velarta", "Hotel Casa Velarta"]},
                  {"id": "palacio-nandu", "name": "Palacio Ñandú", "aliases": ["Palacio Ñandú", "Palacio Nandu"]}]
        records = [{"candidate": "Hotel Casa Velarta"}, {"candidate": "palacio nandu"}, {"candidate": "Elsewhere"}]
        by_id, unmatched = runfiles.match_by_name(merged, records, key="candidate")
        self.assertEqual(by_id["casa-velarta"], [records[0]])
        self.assertEqual(by_id["palacio-nandu"], [records[1]])
        self.assertEqual(unmatched, ["Elsewhere"])


class RunDirsTest(unittest.TestCase):
    def test_data_and_trip_folders_come_from_the_run_folder(self):
        run = Path("/x/data/trips/testgrad-2026-11/run")
        self.assertEqual(runfiles.trip_dir(run), Path("/x/data/trips/testgrad-2026-11"))
        self.assertEqual(runfiles.data_dir(run), Path("/x/data"))


if __name__ == "__main__":
    unittest.main()
