"""Tests for bin/orchestrate.py: stage transitions, the resume rule, agent prompts, the
checkpoint and the answer, run offline from fixtures (U12).

All hotels, cities, dogs and trips here are made up (see tests/fixtures/orchestrator/orchkit.py).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "orchestrator"
sys.path.insert(0, str(FIXTURES))

import orchkit  # noqa: E402
from orchkit import (BIN, ENGINES, FAMILIES, block, edit_candidate, entries, read_json, read_jsonl,  # noqa: E402
                     reader_calls, write_json, write_jsonl)

import citycache  # noqa: E402
import ledger  # noqa: E402
import orchestrate  # noqa: E402
import render  # noqa: E402
import runfiles  # noqa: E402

TODAY = date(2026, 10, 9)
EN = render.LABELS["en"]
RESOLVER_FILES = ("resolved-1.jsonl", "evidence-resolver-1.jsonl", "resolved-2.jsonl", "evidence-resolver-2.jsonl")
CLEARLY_BETTER = {"clearly_better": [{"candidate": "Hotel Torre Alta", "reason": "the only valley view in town"}],
                  "not_better": []}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = orchkit.make_data(self.tmp.name)
        self.contract = orchkit.approved_contract(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **changes):
        out = orchestrate.start(self.data, **dict(orchkit.TRIP, **changes), today=TODAY)
        self.run = Path(out["run_dir"])
        return out

    def to_research(self, **changes):
        self.start(**changes)
        orchestrate.context(self.run)
        orchkit.write_inputs(self.run)
        return orchestrate.fanout(self.run, "research", contract=self.contract)

    def to_filter(self, invalid_reddit=False, **changes):
        self.to_research(**changes)
        orchkit.research_outputs(self.run, invalid_reddit)
        orchestrate.collect(self.run, returned=FAMILIES)
        return orchestrate.filter_stage(self.run)

    def to_shortlist(self, **changes):
        self.to_filter(**changes)
        orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)
        orchkit.agent_files(self.run, *RESOLVER_FILES)
        orchestrate.resolved(self.run)
        out = orchestrate.availability(self.run, reader_fixtures=ENGINES)
        write_json(self.run / "verdicts.json", CLEARLY_BETTER)
        return out

    def shortlist(self) -> str:
        return orchestrate.ask(self.run)["text"]

    def stage(self) -> str:
        return ledger.read_state(self.run)["stage"]

    def statuses(self) -> dict:
        return {s["name"]: s for s in read_json(self.run / "status.json")["candidates"].values()}

    def reads(self) -> dict:
        return read_json(self.run / "reads.json")["reads"]


class CapsTest(Base):
    def test_the_repo_contract_still_waits_for_approval(self):
        caps = orchestrate.parse_caps(orchkit.CONTRACT.read_text(encoding="utf-8"))
        self.assertIsNone(caps["agents"]["curated-press"]["query cap"])
        self.assertIsNone(caps["credit_floor"])
        self.assertIn("curated-press: query cap", caps["pending"])
        self.assertIn("Firecrawl credit floor", caps["pending"])
        self.assertEqual(caps["agents"]["final-check"]["reader page timeout"], "20 s")

    def test_caps_check_before_the_run_starts(self):
        with self.assertRaises(orchestrate.Stop) as ctx:
            orchestrate.caps()
        self.assertEqual(ctx.exception.payload["status"], "caps_pending")
        self.assertEqual(orchestrate.caps(self.contract), {"status": "approved", "pending": []})
        self.assertFalse((self.data / "trips").exists())

    def test_fanout_stops_before_spawning_while_caps_are_pending(self):
        self.start()
        orchestrate.context(self.run)
        orchkit.write_inputs(self.run)
        with self.assertRaises(orchestrate.Stop) as ctx:
            orchestrate.fanout(self.run, "research")
        self.assertEqual(ctx.exception.payload["status"], "caps_pending")
        self.assertIn("approv", ctx.exception.payload["message"])
        self.assertEqual(ledger.read_state(self.run)["waiting_for"], [])
        self.assertEqual(self.stage(), "context")

    def test_approved_caps_reach_each_prompt(self):
        out = self.to_research()
        prompts = {a["name"]: a["prompt"] for a in out["agents"]}
        self.assertEqual(sorted(prompts), sorted(FAMILIES))
        self.assertIn("- query cap: 7", prompts["curated-press"])
        self.assertIn("- fetch cap: 7", prompts["curated-press"])
        self.assertIn("- Firecrawl credit floor: 7", prompts["curated-press"])
        for cap in ("thread cap", "scan cap", "scan pages"):
            self.assertIn(f"- {cap}: 7", prompts["reddit"])
        self.assertIn("- fetch cap: none, ever", prompts["booking-search"])
        self.assertEqual(out["model"], "opus")
        self.assertEqual(ledger.read_state(self.run)["waiting_for"], list(FAMILIES))
        self.assertEqual(self.stage(), "research")


class StartResumeTest(Base):
    def test_start_writes_the_trip_with_the_language_set(self):
        out = self.start()
        trip = read_json(self.run / "trip.json")
        self.assertEqual(ledger.validate_trip(trip), [])
        self.assertEqual((trip["country"], trip["lang"], trip["occasion"]), ("Testland", "en", "city-break"))
        self.assertEqual(trip["languages"], "A = Spanish, B = English, C = none")
        self.assertEqual(out["stage"], "context")
        self.assertEqual(out["stage_file"], "workflows/find-hotel/2-context.md")
        self.assertEqual(self.run, self.data / "trips" / "testgrad-2099-11" / "run")

    def test_resume_lists_an_open_run_with_its_stage_file(self):
        self.start()
        runs = orchestrate.resume(self.data, today=TODAY)["open_runs"]
        self.assertEqual([(r["run_dir"], r["stage"], r["stage_file"]) for r in runs],
                         [(str(self.run), "context", "workflows/find-hotel/2-context.md")])

    def test_resume_matches_the_city_in_any_spelling(self):
        self.start()
        self.assertEqual(len(orchestrate.resume(self.data, city="Тестград", today=TODAY)["open_runs"]), 1)
        self.assertEqual(orchestrate.resume(self.data, city="Otherburg", today=TODAY)["open_runs"], [])

    def test_start_and_resume_record_the_sessions_working_on_the_run(self):
        # The guard's open-run blocks apply only to these sessions (KTD9, the user's decision).
        self.start(session="0b6c2a1e-5f1d-4e2b-9a7c-1d2e3f4a5b6c")
        self.assertEqual(read_json(self.run / "state.json")["sessions"], ["0b6c2a1e-5f1d-4e2b-9a7c-1d2e3f4a5b6c"])
        orchestrate.resume(self.data, city="Testgrad", today=TODAY, session="7e8f9a0b-1c2d-4e3f-8a9b-0c1d2e3f4a5b")
        orchestrate.resume(self.data, city="Testgrad", today=TODAY, session="7e8f9a0b-1c2d-4e3f-8a9b-0c1d2e3f4a5b")
        self.assertEqual(read_json(self.run / "state.json")["sessions"],
                         ["0b6c2a1e-5f1d-4e2b-9a7c-1d2e3f4a5b6c", "7e8f9a0b-1c2d-4e3f-8a9b-0c1d2e3f4a5b"])
        orchestrate.resume(self.data, city="Otherburg", today=TODAY, session="aaaaaaaa-0000-4000-8000-000000000000")
        self.assertNotIn("aaaaaaaa-0000-4000-8000-000000000000", read_json(self.run / "state.json")["sessions"])

    def test_a_session_placeholder_that_was_not_filled_in_is_ignored(self):
        for value in ("${CLAUDE_SESSION_ID}", "", "x; rm -rf /"):
            with self.subTest(value=value):
                self.start(session=value, new=True)
                self.assertEqual(read_json(self.run / "state.json").get("sessions", []), [])

    def test_finished_and_past_runs_are_not_open(self):
        self.start()
        ledger.write_state(self.run, stage="done", waiting_for=[])
        self.start(check_in="2026-09-01", check_out="2026-09-03")
        out = orchestrate.resume(self.data, today=TODAY)
        self.assertEqual(out["open_runs"], [])
        self.assertEqual([r["check_in"] for r in out["stale"]], ["2026-09-01"])

    def test_close_ends_a_run_without_an_answer(self):
        self.start(check_in="2026-09-01", check_out="2026-09-03")
        out = orchestrate.close(self.run, "the trip dates have passed")
        self.assertEqual((out["stage"], self.stage()), ("done", "done"))
        self.assertEqual(ledger.read_state(self.run)["closed_reason"], "the trip dates have passed")
        self.assertEqual(orchestrate.resume(self.data, today=TODAY), {"open_runs": [], "stale": []})
        self.assertFalse((self.data / "cities" / "testgrad.md").read_text(encoding="utf-8").count("testgrad-2026-09"))

    def test_start_refuses_to_overwrite_an_open_run(self):
        self.start()
        with self.assertRaises(orchestrate.Stop) as ctx:
            self.start(check_in="2099-11-27", check_out="2099-11-29")
        self.assertEqual(ctx.exception.payload["status"], "open_run")
        self.assertEqual(read_json(self.run / "trip.json")["check_in"], "2099-11-20")

    def test_a_new_run_archives_the_old_one(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        out = self.start(new=True)
        self.assertTrue(Path(out["archived"]).is_dir())
        self.assertTrue((Path(out["archived"]) / "candidates-reddit.jsonl").is_file())
        self.assertFalse((self.run / "candidates-reddit.jsonl").exists())

    def test_a_finished_run_is_archived_without_asking(self):
        self.start()
        ledger.write_state(self.run, stage="done", waiting_for=[])
        self.assertIsNotNone(self.start()["archived"])

    # #11: a rejected start writes nothing, so no run folder is left that counts as open
    def test_an_invalid_trip_leaves_no_run_folder(self):
        with self.assertRaises(runfiles.RunError) as ctx:
            self.start(check_in="2099-11-22", check_out="2099-11-20")
        self.assertIn("check_out must be after check_in", str(ctx.exception))
        self.assertEqual(list(self.data.glob("trips/*/run")), [])

    def test_an_invalid_new_start_keeps_the_open_run_in_place(self):
        self.start()
        with self.assertRaises(runfiles.RunError):
            self.start(new=True, guests=0)
        self.assertEqual(read_json(self.run / "trip.json")["guests"], 2)
        self.assertEqual(list(self.data.glob("trips/*/run-*")), [])

    def test_close_ends_a_run_folder_without_a_trip_file(self):
        run = self.data / "trips" / "testgrad-2099-12" / "run"
        run.mkdir(parents=True)  # what a failed start used to leave behind
        out = orchestrate.close(run, "abandoned")
        self.assertEqual((out["stage"], ledger.read_state(run)["stage"]), ("done", "done"))
        self.assertEqual(ledger.read_state(run)["closed_reason"], "abandoned")
        with self.assertRaises(runfiles.RunError):
            orchestrate.close(self.data / "trips" / "testgrad-2099-12" / "not-a-run", "x")

    # #15: a new run for the same city and month keeps the earlier answer and Searched line
    def test_a_new_run_keeps_the_old_answer_and_its_searched_line(self):
        self.start()
        trip_dir = runfiles.trip_dir(self.run)
        orchestrate.write_cache(self.run, final=False, today=TODAY)
        (trip_dir / runfiles.ANSWER_FILE).write_text("# the first run's answer\n", encoding="utf-8")
        first_id = orchestrate.cache_run_id(self.run)
        ledger.write_state(self.run, stage="done", waiting_for=[])
        out = self.start(new=True)
        self.assertEqual((Path(out["archived"]) / runfiles.ANSWER_FILE).read_text(encoding="utf-8"),
                         "# the first run's answer\n")
        self.assertFalse((trip_dir / runfiles.ANSWER_FILE).exists())
        orchestrate.write_cache(self.run, final=False, today=TODAY)
        second_id = orchestrate.cache_run_id(self.run)
        self.assertNotEqual(first_id, second_id)
        searched = (self.data / "cities" / "testgrad.md").read_text(encoding="utf-8").split("## Searched")[1]
        searched = searched.split("\n## ")[0]
        self.assertIn(f" {first_id}:", searched)
        self.assertIn(f" {second_id}:", searched)


class ContextTest(Base):
    def test_blacklist_takes_the_feedback_files_and_the_cache_exclusions(self):
        self.start()
        out = orchestrate.context(self.run)
        rows = {r["hotel"]: r for r in read_json(self.run / "blacklist.json")["blacklist"]}
        self.assertEqual(rows["Hotel Ceniza"]["reason"], "no soul, like an office")
        self.assertEqual(rows["Hotel Niebla"]["reason"], "city cache: closed for good, the building was sold")
        self.assertEqual(rows["Hotel Niebla"]["city"], "Testgrad")
        self.assertTrue(out["cache"]["exists"])
        self.assertEqual(out["needs"], ["fit-rules.json", "taste.json"])

    def test_dog_note_comes_from_the_profile_when_the_dog_travels(self):
        self.start(dog=True)
        orchestrate.context(self.run)
        self.assertIn("small terrier, about 7 kg", read_json(self.run / "context.json")["dog_note"])

    def test_no_dog_note_when_the_dog_stays_home(self):
        self.start()
        orchestrate.context(self.run)
        self.assertTrue(read_json(self.run / "context.json")["dog_note"].startswith("none"))

    def test_warm_city_slices_reach_the_family_prompts(self):
        prompts = {a["name"]: a["prompt"] for a in self.to_research()["agents"]}
        self.assertIn("Testgrad Daily", prompts["curated-press"])
        self.assertIn("site:booking.com hotel con encanto Testgrad", prompts["booking-search"])
        self.assertIn("r/testgrad", prompts["reddit"])
        self.assertIn(orchkit.TASTE["taste_summary"], prompts["reddit"])
        self.assertIn("A = Spanish, B = English, C = none", prompts["reddit"])

    def test_cold_city_slice_is_none(self):
        (self.data / "cities" / "testgrad.md").unlink()
        prompts = {a["name"]: a["prompt"] for a in self.to_research()["agents"]}
        self.assertIn("- {source_map_slice}: none", prompts["curated-press"])

    def test_fanout_needs_the_model_inputs(self):
        self.start()
        orchestrate.context(self.run)
        with self.assertRaises(runfiles.RunError) as ctx:
            orchestrate.fanout(self.run, "research", contract=self.contract)
        self.assertIn("fit-rules.json", str(ctx.exception))
        orchkit.write_inputs(self.run)
        write_json(self.run / "taste.json", {"taste_summary": ""})
        with self.assertRaises(runfiles.RunError) as ctx:
            orchestrate.fanout(self.run, "research", contract=self.contract)
        self.assertIn("taste.json", str(ctx.exception))


class CollectTest(Base):
    def test_waits_until_every_family_returns(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        out = orchestrate.collect(self.run, returned=["curated-press"])
        self.assertEqual((out["status"], out["waiting_for"]), ("waiting", ["reddit", "booking-search"]))
        self.assertEqual(self.stage(), "research")

    def test_invalid_lines_get_one_reprompt_then_the_family_is_partial(self):
        self.to_research()
        orchkit.research_outputs(self.run, invalid_reddit=True)
        out = orchestrate.collect(self.run, returned=FAMILIES)
        self.assertEqual(out["status"], "reprompt")
        self.assertEqual([r["family"] for r in out["reprompt"]], ["reddit"])
        self.assertTrue(any("line 3" in p and "permalink" in p for p in out["reprompt"][0]["problems"]))
        self.assertEqual(orchestrate.collect(self.run, reprompted=["reddit"])["waiting_for"], ["reddit"])
        out = orchestrate.collect(self.run, returned=["reddit"])
        self.assertEqual(out["status"], "ready")
        families = read_json(self.run / "families.json")["families"]
        self.assertEqual(families["reddit"]["status"], "partial")
        self.assertIn("1 invalid line", families["reddit"]["reason"])
        self.assertTrue(families["reddit"]["reprompted"])
        self.assertEqual(families["curated-press"]["status"], "ran")
        self.assertEqual(self.stage(), "filter")

    def test_a_line_that_is_not_an_object_is_rejected_not_a_crash(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        with open(self.run / "candidates-reddit.jsonl", "a", encoding="utf-8") as handle:
            handle.write("[1]\n")
        out = orchestrate.collect(self.run, returned=FAMILIES)
        self.assertEqual(out["reprompt"][0]["problems"], ["candidates-reddit.jsonl line 3: not a JSON object"])
        orchestrate.collect(self.run, reprompted=["reddit"])
        reddit = orchestrate.collect(self.run, returned=["reddit"])["families"]["reddit"]
        self.assertEqual((reddit["status"], reddit["records"], reddit["invalid"]), ("partial", 2, 1))

    def test_a_failed_family_is_reported_without_a_reprompt(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        (self.run / "candidates-reddit.jsonl").unlink()
        write_json(self.run / "envelope-reddit.json", {"family": "reddit", "status": "failed",
                                                       "reason": "Reddit backend unreachable"})
        out = orchestrate.collect(self.run, returned=FAMILIES)
        self.assertEqual(out["status"], "ready")
        reddit = out["families"]["reddit"]
        self.assertEqual((reddit["status"], reddit["reason"], reddit["reprompted"]),
                         ("failed", "Reddit backend unreachable", False))
        self.assertEqual(reddit["why"], [{"code": "text", "text": "Reddit backend unreachable"}])

    def test_a_missing_envelope_gets_a_reprompt(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        (self.run / "envelope-booking-search.json").unlink()
        out = orchestrate.collect(self.run, returned=FAMILIES)
        self.assertEqual([r["family"] for r in out["reprompt"]], ["booking-search"])


class FilterTest(Base):
    def test_filter_merges_and_keeps_the_envelope_data(self):
        out = self.to_filter()
        research = read_json(self.run / "research.json")
        self.assertEqual({s["family"] for s in research["source_map"]}, set(FAMILIES))
        self.assertEqual(research["district_notes"][0]["area"], "Old Quarter")
        self.assertEqual(research["negative_reports"][0]["candidate"], "Hotel Sombra")
        self.assertIn("Skipped: blacklist — Hotel Ceniza — no soul, like an office", out["fit"]["skip_lines"])
        self.assertEqual(out["merge"]["merged"], 13)
        self.assertEqual(self.stage(), "availability")

    def test_gmail_bookings_join_the_past_stays(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        orchkit.agent_files(self.run, "gmail-bookings.json")
        orchestrate.collect(self.run, returned=FAMILIES)
        orchestrate.filter_stage(self.run)
        nandu = next(c for c in read_json(self.run / "fit.json")["candidates"] if c["name"] == "Palacio Ñandú")
        self.assertEqual([s["date"] for s in nandu["past_stays"]], ["2025-02-14"])


class ResolverAvailabilityTest(Base):
    def test_resolver_batches_cover_the_kept_hotels_only(self):
        self.to_filter(dog=True)
        out = orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)
        names = [c["name"] for a in out["agents"] for c in a["candidates"]]
        self.assertEqual(len(out["agents"]), 2)
        self.assertEqual(sorted(names), sorted(["Casa Velarta", "Hotel Sombra", "Hotel Invierno", "Hotel Otoño",
                                                "Hotel Torre Alta", "Hotel Marquesa Vieja", "Palacio Ñandú",
                                                "El Patio Lunar"]))
        prompt = out["agents"][0]["prompt"]
        self.assertIn("large or mainstream hotel", prompt)
        self.assertIn("small terrier", prompt)
        self.assertIn("- query cap per candidate: 7", prompt)
        self.assertEqual(ledger.read_state(self.run)["waiting_for"], ["resolver-1", "resolver-2"])

    # AE2 through a resolver evidence record from the hotel's own site
    def test_a_closure_found_by_the_resolver_removes_the_hotel(self):
        self.to_shortlist()
        invierno = self.statuses()["Hotel Invierno"]
        self.assertEqual((invierno["status"], invierno["reason"]), ("unavailable", "closure"))
        self.assertNotIn("invierno", self.reads())
        text = self.shortlist()
        self.assertNotIn("Hotel Invierno", entries(text))
        self.assertIn("Hotel Invierno — El hotel cierra por temporada", text)
        self.assertEqual(read_json(self.run / "modules.json")["modules"]["resolver"]["status"], "ran")

    def test_a_missing_resolver_batch_makes_the_module_partial(self):
        self.to_filter()
        orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)
        orchkit.agent_files(self.run, "resolved-1.jsonl", "evidence-resolver-1.jsonl")
        out = orchestrate.resolved(self.run)
        self.assertEqual(out["module"]["status"], "partial")
        self.assertIn("batch 2", out["module"]["reason"])

    def test_availability_prices_flags_and_the_over_budget_pool(self):
        out = self.to_shortlist()
        s = self.statuses()
        self.assertEqual((s["Casa Velarta"]["status"], s["Casa Velarta"]["price_eur"]), ("available", 160))
        self.assertEqual((s["El Patio Lunar"]["status"], s["El Patio Lunar"]["price_eur"]), ("available", 130))
        self.assertEqual((s["Palacio Ñandú"]["status"], s["Palacio Ñandú"]["reason"]), ("unknown", "unreadable"))
        self.assertEqual(s["Hotel Sombra"]["status"], "unknown")
        self.assertEqual([p["name"] for p in out["over_budget"]], ["Hotel Torre Alta"])
        self.assertEqual(out["reader"]["status"], "ran")
        text = self.shortlist()
        self.assertIn("Hotel Torre Alta", text)
        self.assertIn("€160", block(text, "Casa Velarta"))
        self.assertIn("the street outside is loud until 3am", block(text, "Hotel Sombra"))
        self.assertIn("the staircase is steep", block(text, "Hotel Marquesa Vieja"))
        self.assertEqual(self.stage(), "shortlist")

    # R25: the over-budget pool and the shortlist match a verdict by any name of the hotel
    def test_a_verdict_naming_another_name_of_the_hotel_is_honored_by_the_pool_and_the_shortlist(self):
        self.to_research()
        orchkit.research_outputs(self.run)
        edit_candidate(self.run, "curated-press", "Hotel Torre Alta", local_name="Torre del Valle")
        orchestrate.collect(self.run, returned=FAMILIES)
        orchestrate.filter_stage(self.run)
        orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)
        orchkit.agent_files(self.run, *RESOLVER_FILES)
        orchestrate.resolved(self.run)
        orchestrate.availability(self.run, reader_fixtures=ENGINES)
        write_json(self.run / "verdicts.json", {"clearly_better": [{"candidate": "Torre del Valle",
                                                                    "reason": "the only valley view in town"}],
                                                "not_better": []})
        out = orchestrate.availability(self.run, reader_fixtures=ENGINES)
        self.assertEqual([(p["name"], p["verdict"]) for p in out["over_budget"]], [("Hotel Torre Alta", "clearly_better")])
        text = self.shortlist()
        self.assertIn("the only valley view in town", block(text, "Hotel Torre Alta"))
        self.assertIn("Hotel Torre Alta", text.split(f"### {EN['beyond_budget']}")[1])

    def test_reader_runs_with_the_approved_limits_and_skips_without_a_browser(self):
        self.to_filter()
        orchestrate.fanout(self.run, "resolver", batches=1, contract=self.contract)
        orchkit.agent_files(self.run, "resolved-1.jsonl", "evidence-resolver-1.jsonl")
        (self.run / "resolved-2.jsonl").unlink(missing_ok=True)
        orchestrate.resolved(self.run)
        log = Path(self.tmp.name) / "reader-calls.txt"
        fake = Path(self.tmp.name) / "fake_reader.py"
        fake.write_text("import sys\nopen(sys.argv[1], 'a').write(' '.join(sys.argv[2:]) + '\\n')\n"
                        "print('SKIPPED: background browser not installed')\nsys.exit(4)\n", encoding="utf-8")
        out = orchestrate.availability(self.run, reader=[sys.executable, str(fake), str(log)])
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertIn("--page-timeout-s 20 --give-up-after-s 45", calls[0])
        self.assertEqual(out["reader"]["status"], "skipped")
        self.assertEqual(out["reader"]["why"], [{"code": "reader_missing"}])
        self.assertIn("not installed", out["reader"]["reason"])

    # F2: nothing survives the checks
    def test_nothing_left_goes_straight_to_the_answer(self):
        self.to_research()
        rules = read_json(orchkit.PIPELINE / "run" / "fit-rules.json")
        rules["excluded_kinds"] = ["hotel", "special-format", "apartment"]
        write_json(self.run / "fit-rules.json", rules)
        orchkit.research_outputs(self.run)
        orchestrate.collect(self.run, returned=FAMILIES)
        orchestrate.filter_stage(self.run)
        self.assertEqual(orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)["status"],
                         "nothing_to_resolve")
        out = orchestrate.availability(self.run, reader_fixtures=ENGINES)
        self.assertEqual(out["entries"], 0)
        self.assertEqual(self.stage(), "answer")
        modules = read_json(self.run / "modules.json")["modules"]
        self.assertEqual(modules["final_check"]["status"], "skipped")

    # R25: a hotel named in both verdict lists is not better, for the pool and for the shortlist alike
    def test_a_not_better_verdict_wins_over_a_clearly_better_one(self):
        self.to_shortlist()
        both = {"candidate": "Hotel Torre Alta", "reason": "the only valley view in town"}
        write_json(self.run / "verdicts.json", {"clearly_better": [both], "not_better": [both]})
        out = orchestrate.availability(self.run, reader_fixtures=ENGINES)
        self.assertEqual([(p["name"], p["verdict"]) for p in out["over_budget"]], [("Hotel Torre Alta", "not_better")])
        text = self.shortlist()
        self.assertNotIn("Hotel Torre Alta", entries(text))
        self.assertNotIn(EN["beyond_budget"], text)


class ReaderTest(Base):
    """The engine reader as availability runs it: limits, crashes and its bookkeeping (R22)."""

    def to_reader(self, batches=2):
        self.to_filter()
        orchestrate.fanout(self.run, "resolver", batches=batches, contract=self.contract)
        orchkit.agent_files(self.run, *RESOLVER_FILES)
        orchestrate.resolved(self.run)

    # #12: a reader that crashes on every hotel is a failed module, not "nothing to read"
    def test_reader_crashes_on_every_hotel_make_the_module_failed(self):
        self.to_reader()
        names = ["Casa Velarta", "Hotel Sombra", "Hotel Otoño", "Hotel Torre Alta", "Hotel Marquesa Vieja",
                 "Palacio Ñandú", "El Patio Lunar"]
        command, log = orchkit.fake_reader(self.tmp.name, fail=names)
        out = orchestrate.availability(self.run, reader=command)
        self.assertEqual(len(reader_calls(log)), 7)
        self.assertEqual(out["reader"]["status"], "failed")
        self.assertEqual(out["reader"]["why"], [{"code": "reader_error", "count": 7}])
        self.assertIn("reader failed on 7", out["reader"]["reason"])
        self.assertTrue(all(r["why"] == "reader error (exit 1)" for r in out["not_read"] if r["name"] in names))
        self.assertEqual(self.reads(), {})
        text = render.render_answer(self.run, "ru")
        self.assertIn(render.LABELS["ru"]["status_failed"], text)
        self.assertIn(render.why_text([{"code": "reader_error", "count": 7}], render.LABELS["ru"]), text)

    def test_reader_crashes_on_some_hotels_make_the_module_partial(self):
        self.to_reader()
        command, log = orchkit.fake_reader(self.tmp.name, fail=["Hotel Sombra"])
        out = orchestrate.availability(self.run, reader=command)
        self.assertEqual(out["reader"]["status"], "partial")
        self.assertEqual(out["reader"]["why"], [{"code": "reader_error", "count": 1}])
        self.assertNotIn("sombra", self.reads())
        # the crashed hotel is read again next time; the others are not
        orchkit.fake_reader(self.tmp.name)
        again = orchestrate.availability(self.run, reader=command)
        self.assertEqual([r["name"] for r in again["read"]], ["Hotel Sombra"])
        self.assertEqual(again["reader"]["status"], "ran")

    # residual: reads.json is saved after each hotel, so an interrupted run does not read everything again
    def test_reads_are_saved_after_each_hotel(self):
        self.to_reader()
        command, log = orchkit.fake_reader(self.tmp.name)
        orchestrate.availability(self.run, reader=command)
        self.assertEqual([c["reads_on_file"] for c in reader_calls(log)], list(range(7)))

    # #5 and F2: every hotel priced above the budget, then the user raises it
    def test_a_budget_raise_after_nothing_fits_returns_to_the_shortlist_without_new_research(self):
        self.to_research(budget_max=100)
        rules = read_json(orchkit.PIPELINE / "run" / "fit-rules.json")
        rules["excluded_kinds"].append("special-format")  # no Airbnb block in this test
        write_json(self.run / "fit-rules.json", rules)
        orchkit.research_outputs(self.run)
        orchestrate.collect(self.run, returned=FAMILIES)
        orchestrate.filter_stage(self.run)
        orchestrate.fanout(self.run, "resolver", batches=2, contract=self.contract)
        orchkit.agent_files(self.run, *RESOLVER_FILES)
        orchestrate.resolved(self.run)
        command, log = orchkit.fake_reader(self.tmp.name, price=400)
        out = orchestrate.availability(self.run, reader=command)
        self.assertEqual((out["entries"], out["next"], self.stage()), (0, "answer", "answer"))
        self.assertFalse((self.run / "numbers.json").exists())
        self.assertIn(EN["relax_budget"], render.render_answer(self.run, "en"))
        merged_before = (self.run / "merged.jsonl").read_bytes()
        families_before = {f: (self.run / f"candidates-{f}.jsonl").read_bytes() for f in FAMILIES}
        calls_before, history_before = len(reader_calls(log)), len(ledger.read_state(self.run)["history"])
        out = orchestrate.checkpoint(self.run, {"change": {"budget_max": 450}}, reader=command)
        self.assertEqual(out["next"], "shortlist")
        self.assertEqual(out["entries"], 7)
        self.assertEqual(self.stage(), "shortlist")
        self.assertEqual(len(reader_calls(log)), calls_before)  # same dates: nothing read again
        self.assertEqual((self.run / "merged.jsonl").read_bytes(), merged_before)
        self.assertEqual({f: (self.run / f"candidates-{f}.jsonl").read_bytes() for f in FAMILIES}, families_before)
        new_stages = [h["stage"] for h in ledger.read_state(self.run)["history"][history_before:]]
        self.assertNotIn("research", new_stages)
        self.assertIn("Casa Velarta", entries(self.shortlist()))
        stage8 = (BIN.parent / "workflows" / "find-hotel" / "8-answer.md").read_text(encoding="utf-8")
        self.assertIn("orchestrate.py checkpoint RUN RUN/reply.json", stage8.split("Nothing fits")[-1])


class ReadCommandTest(Base):
    """#1: the final check's reader runs take a candidate id; names and URLs never reach a shell."""
    NAME = 'Casa $(touch pwned-name) `touch pwned-tick` "Velarta"'
    URL = "https://casavelarta.example/$(touch pwned-url)/`touch pwned-url-tick`/"

    def setUp(self):
        super().setUp()
        self.to_shortlist()
        merged = read_jsonl(self.run / "merged.jsonl")
        for candidate in merged:
            if candidate["id"] == "casa-velarta":
                candidate["name"] = self.NAME
        write_jsonl(self.run / "merged.jsonl", merged)
        resolved = read_json(self.run / "resolved.json")
        for line in resolved["resolved"]:
            if line["candidate"] == "Casa Velarta":
                line["official_url"]["value"] = self.URL
        write_json(self.run / "resolved.json", resolved)
        self.out = self.run / "evidence-final-1.jsonl"

    def pwned(self) -> list:
        return sorted(p.name for p in Path(self.tmp.name).rglob("pwned*")) + sorted(
            p.name for p in Path.cwd().glob("pwned*"))

    def test_read_passes_the_name_and_url_as_single_arguments(self):
        command, log = orchkit.fake_reader(self.tmp.name, price=185)
        out = orchestrate.read(self.run, "casa-velarta", self.out, reader=command)
        argv = reader_calls(log)[0]["argv"]
        self.assertIn(f"--candidate={self.NAME}", argv)
        self.assertIn(f"--url={self.URL}", argv)
        self.assertIn("--page-timeout-s 20 --give-up-after-s 45", " ".join(argv))
        self.assertEqual(argv[argv.index("--out") + 1], str(self.out))
        self.assertEqual((out["status"], out["exit"], out["record"]["price_eur"]), ("ok", 0, 185))
        self.assertEqual([r["candidate"] for r in read_jsonl(self.out)], [self.NAME])
        self.assertEqual(self.pwned(), [])

    def test_the_cli_runs_the_real_reader_without_a_shell(self):
        result = subprocess.run([sys.executable, str(BIN / "orchestrate.py"), "read", str(self.run),
                                 "--candidate-id", "casa-velarta", "--out", str(self.out),
                                 "--reader-fixtures", str(ENGINES)],
                                capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual((out["status"], out["record"]["kind"]), ("ok", "engine_price"))
        self.assertEqual([r["candidate"] for r in read_jsonl(self.out)], [self.NAME])
        self.assertEqual(out["url"], self.URL)
        self.assertEqual(self.pwned(), [])

    def test_read_refuses_an_unknown_id_and_a_file_outside_the_run(self):
        command, log = orchkit.fake_reader(self.tmp.name)
        for cid, out in (("no-such-hotel", self.out), ("casa-velarta$(id)", self.out),
                         ("casa-velarta", Path(self.tmp.name) / "evidence-final-1.jsonl"),
                         ("casa-velarta", self.run / "evidence.jsonl")):
            with self.assertRaises(runfiles.RunError, msg=(cid, out)):
                orchestrate.read(self.run, cid, out, reader=command)
        self.assertEqual(reader_calls(log), [])

    def test_final_check_prompts_carry_ids_and_the_brief_builds_no_reader_command(self):
        orchestrate.checkpoint(self.run, {"strike": []})
        out = orchestrate.fanout(self.run, "final", batches=1, contract=self.contract)
        ids = {c["id"] for c in out["agents"][0]["candidates"]}
        self.assertIn("casa-velarta", ids)
        self.assertIn('"id": "casa-velarta"', out["agents"][0]["prompt"])
        brief = (BIN.parent / "references" / "briefs" / "final-check.md").read_text(encoding="utf-8")
        self.assertIn("orchestrate.py read {run_dir} --candidate-id {id}", brief)
        self.assertNotIn("engine_reader.py --candidate", brief)


class CheckpointTest(Base):
    def numbers(self) -> dict:
        return entries(self.shortlist())

    # AE8 and the mixed reply
    def test_mixed_reply_records_strikes_and_reruns_only_the_availability_stage(self):
        self.to_shortlist()
        n = self.numbers()
        merged_before = (self.run / "merged.jsonl").read_bytes()
        families_before = {f: (self.run / f"candidates-{f}.jsonl").read_bytes() for f in FAMILIES}
        history_before = len(ledger.read_state(self.run)["history"])
        out = orchestrate.checkpoint(self.run, {"strike": [{"number": n["Hotel Sombra"], "reason": "dark rooms"}],
                                                "change": {"check_in": "2099-11-27", "check_out": "2099-11-29"}},
                                     reader_fixtures=ENGINES)
        self.assertEqual(out["next"], "shortlist")
        self.assertEqual((self.run / "merged.jsonl").read_bytes(), merged_before)
        self.assertEqual({f: (self.run / f"candidates-{f}.jsonl").read_bytes() for f in FAMILIES}, families_before)
        new_stages = [h["stage"] for h in ledger.read_state(self.run)["history"][history_before:]]
        self.assertNotIn("research", new_stages)
        self.assertNotIn("filter", new_stages)
        read_now = {cid for cid, reads in self.reads().items() if any(r["check_in"] == "2099-11-27" for r in reads)}
        self.assertEqual(read_now, {"casa-velarta", "el-patio-lunar", "palacio-nandu", "torre-alta", "marquesa-vieja"})
        s = self.statuses()
        self.assertEqual(s["Casa Velarta"]["price_eur"], 170)
        self.assertEqual(s["Hotel Otoño"]["status"], "unavailable")
        self.assertEqual(s["El Patio Lunar"]["reason"], "dates_mismatch")
        text = self.shortlist()
        self.assertNotIn("Hotel Sombra", entries(text))
        self.assertEqual(entries(text)["Casa Velarta"], n["Casa Velarta"])
        # R15: the strike-out and its reason are in the city cache
        struck = citycache.read(self.data / "cities" / "testgrad.md")["struck_out"]
        self.assertIn({"name": "Hotel Sombra", "reason": "dark rooms", "date": TODAY.isoformat(), "trip": "testgrad-2099-11"},
                      [dict(r, date=TODAY.isoformat()) for r in struck])

    # R24: a struck hotel returns after the budget goes up
    def test_a_struck_hotel_returns_after_a_budget_raise(self):
        self.to_shortlist()
        n = self.numbers()
        orchestrate.checkpoint(self.run, {"strike": [{"number": n["Hotel Sombra"], "reason": "dark rooms"}],
                                          "change": {"check_in": "2099-11-27", "check_out": "2099-11-29"}},
                               reader_fixtures=ENGINES)
        out = orchestrate.checkpoint(self.run, {"change": {"budget_max": 300}}, reader_fixtures=ENGINES)
        self.assertEqual([r["name"] for r in out["apply"]["released"]], ["Hotel Sombra"])
        text = self.shortlist()
        self.assertEqual(entries(text)["Hotel Sombra"], n["Hotel Sombra"])
        self.assertIn("€165", block(text, "Hotel Sombra"))

    def test_a_reply_without_a_change_moves_to_the_final_check(self):
        self.to_shortlist()
        out = orchestrate.checkpoint(self.run, {"strike": [{"number": self.numbers()["Palacio Ñandú"]}]})
        self.assertEqual(out["next"], "final")
        self.assertEqual(self.stage(), "final")

    def test_a_reply_that_keeps_nothing_goes_to_the_answer(self):
        self.to_shortlist()
        out = orchestrate.checkpoint(self.run, {"strike": [{"number": v} for v in self.numbers().values()]})
        self.assertEqual(out["next"], "answer")
        self.assertEqual(read_json(self.run / "modules.json")["modules"]["final_check"]["status"], "skipped")
        self.assertIn(EN["nothing_fits"], render.render_answer(self.run, "en"))

    def test_a_fresh_session_gets_the_same_shortlist_and_applies_the_strikes(self):
        self.to_shortlist()
        before = self.shortlist()
        runs = orchestrate.resume(self.data, today=TODAY)["open_runs"]
        self.assertEqual((runs[0]["stage"], runs[0]["stage_file"]), ("shortlist", "workflows/find-hotel/6-shortlist.md"))
        again = orchestrate.ask(Path(runs[0]["run_dir"]))
        self.assertEqual(again["text"], before)
        self.assertEqual(again["mode"], "question")
        orchestrate.checkpoint(Path(runs[0]["run_dir"]), {"strike": [{"number": entries(before)["Hotel Sombra"]}]})
        self.assertNotIn("Hotel Sombra", entries(self.shortlist()))


class FinalAnswerTest(Base):
    def to_final(self):
        self.to_shortlist()
        n = entries(self.shortlist())
        orchestrate.checkpoint(self.run, {"strike": [{"number": n["Hotel Sombra"], "reason": "dark rooms"}],
                                          "change": {"check_in": "2099-11-27", "check_out": "2099-11-29"}},
                               reader_fixtures=ENGINES)
        orchestrate.checkpoint(self.run, {"strike": [{"number": n["Palacio Ñandú"], "reason": "no online booking"}]})
        return orchestrate.fanout(self.run, "final", batches=1, contract=self.contract)

    def test_final_check_removes_on_no_rooms_reprices_and_keeps_unknowns(self):
        out = self.to_final()
        names = [c["name"] for c in out["agents"][0]["candidates"]]
        self.assertEqual(sorted(names), sorted(["Casa Velarta", "El Patio Lunar", "Hotel Marquesa Vieja", "Hotel Torre Alta"]))
        orchkit.agent_files(self.run, "final-1.jsonl", "evidence-final-1.jsonl")
        result = orchestrate.finalized(self.run)
        self.assertEqual([(r["name"], r["quote"]) for r in result["removed"]],
                         [("Hotel Marquesa Vieja", "No hay disponibilidad para las fechas seleccionadas.")])
        self.assertEqual([(r["name"], r["before"], r["after"]) for r in result["price_changed"]],
                         [("Casa Velarta", 170, 185)])
        self.assertIn("El Patio Lunar", [r["name"] for r in result["unknown"]])
        self.assertEqual(result["module"]["status"], "ran")
        self.assertEqual(self.stage(), "answer")

    def test_answer_reports_every_check_passes_the_output_check_and_updates_the_cache(self):
        self.to_final()
        orchkit.agent_files(self.run, "final-1.jsonl", "evidence-final-1.jsonl")
        orchestrate.finalized(self.run)
        orchestrate.set_module(self.run, "gmail", "skipped", "no Gmail tools in this session")
        write_json(self.run / "advice.json", {"overview": "City-break pick in Testgrad — quiet old-town houses.",
                                              "entries": [{"candidate": "Casa Velarta", "why": "a merchant house"}],
                                              "districts": ["Old Quarter: quiet lanes"], "tips": []})
        out = orchestrate.answer(self.run, today=TODAY)
        self.assertEqual(out["status"], "ok", out)
        answer_file = Path(out["answer_file"])
        self.assertEqual(answer_file, self.data / "trips" / "testgrad-2099-11" / "hotels-shortlist.md")
        text = answer_file.read_text(encoding="utf-8")
        self.assertIn(EN["history_skipped"], text)
        self.assertIn("€185", block(text, "Casa Velarta"))
        self.assertIn("Doble Superior · Tarifa flexible", block(text, "Casa Velarta"))
        self.assertIn("Skipped: not available for the dates — Hotel Marquesa Vieja", text)
        self.assertIn("❓", block(text, "El Patio Lunar"))
        self.assertIn("Carmen del Aljibe Rojo", text.split(f"### {EN['airbnb']}")[1])  # AE7
        self.assertNotIn("Palacio Ñandú", entries(text))
        cache = citycache.read(self.data / "cities" / "testgrad.md")
        self.assertEqual(next(r for r in cache["recommended"] if r["name"] == "Casa Velarta")["rating"], "9.0")
        outlets = [s["outlet"] for s in cache["sources"]]
        self.assertIn("Revista Ejemplo", outlets)
        self.assertIn("Testgrad Daily", outlets)
        # struck in the same reply as the date change, Sombra stays struck; Palacio was struck after it
        self.assertEqual(sorted(r["name"] for r in cache["struck_out"] if r["trip"] == "testgrad-2099-11"),
                         ["Hotel Sombra", "Palacio Ñandú"])
        self.assertEqual(next(r for r in cache["struck_out"] if r["name"] == "Palacio Ñandú")["reason"],
                         "no online booking")
        self.assertEqual(self.stage(), "done")
        self.assertEqual(orchestrate.resume(self.data, today=TODAY)["open_runs"], [])

    def test_answer_fails_while_a_module_has_no_status(self):
        self.to_final()
        orchkit.agent_files(self.run, "final-1.jsonl", "evidence-final-1.jsonl")
        orchestrate.finalized(self.run)
        out = orchestrate.answer(self.run, today=TODAY)
        self.assertEqual(out["status"], "fail")
        self.assertIn("no status for module gmail (R22)", out["failures"])
        self.assertEqual(self.stage(), "answer")

    def test_answer_refuses_advice_for_a_hotel_the_run_does_not_hold(self):
        self.to_final()
        write_json(self.run / "advice.json", {"entries": [{"candidate": "Hotel Fantasma", "why": "x"}]})
        with self.assertRaises(runfiles.RunError) as ctx:
            orchestrate.answer(self.run, today=TODAY)
        self.assertIn("Hotel Fantasma", str(ctx.exception))


class ModuleTest(Base):
    def test_module_names_and_statuses_are_checked(self):
        self.start()
        orchestrate.set_module(self.run, "gmail", "ran")
        self.assertEqual(read_json(self.run / "modules.json")["modules"]["gmail"], {"status": "ran", "reason": ""})
        for name, status in (("gmial", "ran"), ("gmail", "done")):
            with self.assertRaises(runfiles.RunError):
                orchestrate.set_module(self.run, name, status)


class CliTest(Base):
    def cli(self, *args):
        result = subprocess.run([sys.executable, str(BIN / "orchestrate.py"), *map(str, args)],
                                capture_output=True, text=True)
        return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else {}), result.stderr

    def test_caps_pending_exits_3_with_a_message(self):
        self.start()
        orchestrate.context(self.run)
        orchkit.write_inputs(self.run)
        code, out, _ = self.cli("fanout", self.run, "research")
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "caps_pending")

    def test_resume_and_start_from_the_command_line(self):
        code, out, err = self.cli("start", "--data", self.data, "--city", "Testgrad", "--country", "Testland",
                                  "--languages", "A = Spanish, B = English, C = none", "--lang", "ru",
                                  "--check-in", "2099-01-15", "--check-out", "2099-01-17", "--guests", 2,
                                  "--budget-max", 180, "--dog", "yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(read_json(Path(out["run_dir"]) / "trip.json")["lang"], "ru")
        code, out, err = self.cli("resume", "--data", self.data, "--session", "5a6b7c8d-9e0f-4a1b-8c2d-3e4f5a6b7c8d")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["open_runs"][0]["stage"], "context")
        self.assertEqual(read_json(Path(out["open_runs"][0]["run_dir"]) / "state.json")["sessions"],
                         ["5a6b7c8d-9e0f-4a1b-8c2d-3e4f5a6b7c8d"])

    def test_a_missing_input_exits_2(self):
        self.start()
        code, _, err = self.cli("filter", self.run)
        self.assertEqual(code, 2)
        self.assertIn("error:", err)


if __name__ == "__main__":
    unittest.main()
