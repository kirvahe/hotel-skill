"""Tests for bin/apply_reply.py: strike-outs and changes at the shortlist checkpoint (R15, R24).

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
from runkit import BIN, edit_candidate, entries, pet, read_json  # noqa: E402

import apply_reply  # noqa: E402
import render  # noqa: E402
import runfiles  # noqa: E402

EN = render.LABELS["en"]


def statuses(run: Path) -> dict:
    return {s["name"]: s for s in read_json(run / "status.json")["candidates"].values()}


class ApplyReplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = runkit.make_run(self.tmp.name)
        runkit.pipeline(self.run)
        self.numbers = entries(render.render_shortlist(self.run, "en"))

    def tearDown(self):
        self.tmp.cleanup()

    def shortlist(self) -> dict:
        return entries(render.render_shortlist(self.run, "en"))

    def test_strike_out_is_recorded_with_its_reason_and_leaves_the_list(self):
        result = apply_reply.apply(self.run, {"strike": [{"number": self.numbers["Hotel Sombra"], "reason": "too far out"}]})
        self.assertEqual([(s["name"], s["reason"]) for s in result["struck"]], [("Hotel Sombra", "too far out")])
        saved = read_json(self.run / "checkpoints.json")["checkpoints"]
        self.assertEqual(saved[0]["strikes"][0]["reason"], "too far out")
        listed = self.shortlist()
        self.assertNotIn("Hotel Sombra", listed)
        self.assertEqual(listed["Casa Velarta"], self.numbers["Casa Velarta"])

    def test_strike_out_without_a_reason(self):
        apply_reply.apply(self.run, {"strike": [{"number": self.numbers["Hotel Sombra"]}]})
        self.assertNotIn("Hotel Sombra", self.shortlist())

    def test_strikes_without_a_change_accumulate(self):
        apply_reply.apply(self.run, {"strike": [{"number": self.numbers["Hotel Sombra"]}]})
        apply_reply.apply(self.run, {"strike": [{"number": self.numbers["El Patio Lunar"]}]})
        listed = self.shortlist()
        self.assertNotIn("Hotel Sombra", listed)
        self.assertNotIn("El Patio Lunar", listed)

    # AE8 and a mixed reply
    def test_mixed_reply_strikes_and_moves_the_dates_without_new_research(self):
        merged_before = (self.run / "merged.jsonl").read_bytes()
        result = apply_reply.apply(self.run, {
            "strike": [{"number": self.numbers["Hotel Sombra"], "reason": "dark rooms"}],
            "change": {"check_in": "2026-11-27", "check_out": "2026-11-29"},
        })
        trip = read_json(self.run / "trip.json")
        self.assertEqual((trip["check_in"], trip["check_out"]), ("2026-11-27", "2026-11-29"))
        self.assertEqual((self.run / "merged.jsonl").read_bytes(), merged_before)
        self.assertTrue(result["needs_availability_check"])
        self.assertIn("Casa Velarta", result["to_check"])
        self.assertNotIn("Hotel Sombra", result["to_check"])
        self.assertNotIn("Hotel Invierno", result["to_check"])
        s = statuses(self.run)
        self.assertEqual((s["Hotel Marquesa Vieja"]["status"], s["Hotel Marquesa Vieja"]["price_eur"]), ("available", 150))
        self.assertEqual(s["Casa Velarta"]["status"], "unknown")
        self.assertEqual(s["Hotel Otoño"]["status"], "unavailable")
        listed = self.shortlist()
        self.assertNotIn("Hotel Sombra", listed)
        self.assertNotIn("Hotel Otoño", listed)
        self.assertEqual(listed["Hotel Marquesa Vieja"], self.numbers["Hotel Marquesa Vieja"])

    def test_strike_struck_earlier_returns_after_a_budget_increase(self):
        apply_reply.apply(self.run, {"strike": [{"number": self.numbers["Casa Velarta"], "reason": "too plain"}]})
        self.assertNotIn("Casa Velarta", self.shortlist())
        result = apply_reply.apply(self.run, {"change": {"budget_max": 300}})
        self.assertEqual([r["name"] for r in result["released"]], ["Casa Velarta"])
        text = render.render_shortlist(self.run, "en")
        listed = entries(text)
        self.assertEqual(listed["Casa Velarta"], self.numbers["Casa Velarta"])
        self.assertIn("Hotel Torre Alta", listed)
        self.assertNotIn(EN["beyond_budget"], text)
        self.assertEqual(read_json(self.run / "trip.json")["budget"]["max"], 300)

    def test_dog_change_reruns_the_fit_filter_on_saved_candidates(self):
        edit_candidate(self.run, "curated-press", "Hotel Sombra", pet_policy=pet("not allowed"))
        runkit.pipeline(self.run)
        self.assertIn("Hotel Sombra", self.shortlist())
        result = apply_reply.apply(self.run, {"change": {"dog": True}})
        self.assertFalse(result["needs_availability_check"])
        self.assertNotIn("Hotel Sombra", self.shortlist())

    def test_reply_that_keeps_nothing_leads_to_the_suggestions(self):
        apply_reply.apply(self.run, {"strike": [{"number": n} for n in self.numbers.values()]})
        text = render.render_shortlist(self.run, "en")
        self.assertEqual(entries(text), {})
        self.assertIn(EN["nothing_fits"], text)
        for key in ("relax_district", "relax_dates"):
            self.assertIn(EN[key], text)

    def test_unknown_number_is_an_error_and_nothing_is_saved(self):
        with self.assertRaises(runfiles.RunError):
            apply_reply.apply(self.run, {"strike": [{"number": 99}]})
        self.assertFalse((self.run / "checkpoints.json").exists())

    def test_bad_dates_are_an_error_and_the_trip_is_unchanged(self):
        with self.assertRaises(runfiles.RunError):
            apply_reply.apply(self.run, {"change": {"check_in": "2026-11-29", "check_out": "2026-11-27"}})
        self.assertEqual(read_json(self.run / "trip.json")["check_in"], "2026-11-20")

    # #5: after "nothing fits" no shortlist was numbered, yet a change must still apply
    def test_a_change_needs_no_entry_numbers_but_a_strike_does(self):
        run = runkit.make_run(Path(self.tmp.name) / "unnumbered")
        runkit.pipeline(run)
        self.assertFalse((run / "numbers.json").exists())
        with self.assertRaises(runfiles.RunError) as ctx:
            apply_reply.apply(run, {"strike": [{"number": 1}], "change": {"budget_max": 300}})
        self.assertIn("render the shortlist first", str(ctx.exception))
        self.assertEqual(read_json(run / "trip.json")["budget"]["max"], 200)
        result = apply_reply.apply(run, {"change": {"budget_max": 300}})
        self.assertEqual(result["changed"], {"budget_max": 300})
        self.assertEqual(read_json(run / "trip.json")["budget"]["max"], 300)

    def test_cli_reads_the_reply_file(self):
        reply = Path(self.tmp.name) / "reply.json"
        reply.write_text(json.dumps({"strike": [{"number": self.numbers["Hotel Sombra"], "reason": "x"}]}), encoding="utf-8")
        result = subprocess.run([sys.executable, str(BIN / "apply_reply.py"), str(self.run), str(reply)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["checkpoint"], 1)


if __name__ == "__main__":
    unittest.main()
