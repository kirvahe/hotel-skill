"""Builds a throwaway data folder and find-hotel run for the orchestrator tests.

Every hotel, city, rating, dog and trip here is made up. The run reuses the
pipeline fixture's candidates (tests/fixtures/pipeline/runkit.py lists them);
the files in agents/ stand in for what the research, resolver, final-check and
Gmail agents write, and engines/ holds saved booking-engine pages for the reader.
"""
from __future__ import annotations

import fnmatch
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
BIN = REPO / "bin"
PIPELINE = HERE.parent / "pipeline"
AGENTS = HERE / "agents"
ENGINES = HERE / "engines"
CONTRACT = REPO / "references" / "briefs" / "research-contract.md"
for folder in (BIN, PIPELINE):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import ledger  # noqa: E402
import runfiles  # noqa: E402
# The pipeline fixture's helpers; the orchestrator tests import them from here.
from runkit import block, edit_candidate, entries, read_json, read_jsonl, write_json, write_jsonl  # noqa: E402,F401

TASTE = {"taste_summary": "small hotels with character in historic buildings, lively neighbourhoods, "
                          "personal service; no large chains",
         "judgment_rules": ["large or mainstream hotel (over about 60 rooms)"]}
TRIP = dict(city="Testgrad", country="Testland", languages="A = Spanish, B = English, C = none", lang="en",
            check_in="2099-11-20", check_out="2099-11-22", guests=2, budget_max=200, dog=False, occasion="city-break")
FAMILIES = ledger.FAMILIES


def make_data(tmp) -> Path:
    """DATA/ with a filled profile, the history, the feedback files and a warm Testgrad cache."""
    data = Path(tmp) / "data"
    (data / "cities").mkdir(parents=True)
    shutil.copy(HERE / "profile.md", data / "taste-profile.md")
    shutil.copy(PIPELINE / "stays-history.md", data / "booking-history.md")
    shutil.copytree(PIPELINE / "blacklist-feedback", data / "feedback")
    shutil.copy(HERE / "city-cache-testgrad.md", data / "cities" / "testgrad.md")
    return data


def approved_contract(tmp) -> Path:
    """The real contract with every "set at approval" placeholder filled with a synthetic test value.

    The value 7 is a test stand-in, not a proposal: the real caps await the user's approval.
    """
    text = re.sub(r"\{[^{}]*— set at approval\}", "7", CONTRACT.read_text(encoding="utf-8"))
    path = Path(tmp) / "contract-approved.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_inputs(run: Path) -> None:
    """What the model writes at stage 2 from the profile: the fit rules and the brief inputs."""
    shutil.copy(PIPELINE / "run" / runfiles.FIT_RULES, run / runfiles.FIT_RULES)
    (run / runfiles.TASTE).write_text(json.dumps(TASTE, ensure_ascii=False), encoding="utf-8")


def research_outputs(run: Path, invalid_reddit: bool = False) -> None:
    """What the three family agents write: candidate files and envelope files."""
    for family in FAMILIES:
        candidates, envelope = runfiles.CANDIDATES.format(family=family), runfiles.ENVELOPE.format(family=family)
        shutil.copy(PIPELINE / "run" / candidates, run / candidates)
        shutil.copy(AGENTS / envelope, run / envelope)
    if invalid_reddit:
        with open(run / runfiles.CANDIDATES.format(family="reddit"), "a", encoding="utf-8") as handle:
            handle.write((AGENTS / "invalid-reddit-line.jsonl").read_text(encoding="utf-8"))


# A stand-in for bin/engine_reader.py: the same arguments, a made-up price for every hotel it is
# asked about, exit 1 (a reader crash) for the names under "fail". Each call is logged with its
# argument list and the number of hotels reads.json already held when it ran.
FAKE_READER = r'''
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
parser = argparse.ArgumentParser()
for name in ("--candidate", "--url", "--check-in", "--check-out", "--guests", "--out",
             "--page-timeout-s", "--give-up-after-s", "--fixture"):
    parser.add_argument(name)
args = parser.parse_args(sys.argv[2:])
reads = Path(args.out).parent / "reads.json"
on_file = len(json.loads(reads.read_text(encoding="utf-8"))["reads"]) if reads.is_file() else 0
with open(config["log"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[2:], "reads_on_file": on_file}, ensure_ascii=False) + "\n")
if args.candidate in config["fail"]:
    sys.exit(1)
record = {"candidate": args.candidate, "kind": "engine_price", "source_url": args.url,
          "quote": "Doble: %s € por noche" % config["price"],
          "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "price_eur": config["price"], "price_basis": "per_night",
          "dates_shown": {"check_in": args.check_in, "check_out": args.check_out, "quote": "Llegada / Salida"}}
with open(args.out, "a", encoding="utf-8") as out:
    out.write(json.dumps(record, ensure_ascii=False) + "\n")
print(json.dumps(record, ensure_ascii=False))
'''


def fake_reader(tmp, price: float = 400, fail=()) -> tuple[list, Path]:
    """(reader command for orchestrate's reader= argument, log file of its calls)."""
    tmp = Path(tmp)
    script, config, log = tmp / "fake_reader.py", tmp / "fake-reader.json", tmp / "fake-reader-calls.jsonl"
    script.write_text(FAKE_READER, encoding="utf-8")
    config.write_text(json.dumps({"price": price, "fail": list(fail), "log": str(log)}, ensure_ascii=False),
                      encoding="utf-8")
    return [sys.executable, str(script), str(config)], log


def reader_calls(log: Path) -> list:
    return read_jsonl(log) if Path(log).is_file() else []


def agent_files(run: Path, *names: str) -> None:
    """Copy agent output files into the run. Final-check evidence is stamped one minute from now,
    so it is newer than the reader's own reads whatever day the tests run on."""
    later = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")
    for name in names:
        if fnmatch.fnmatch(name, runfiles.FINAL_EVIDENCE.format(batch="*")):
            write_jsonl(run / name, [dict(r, read_at=later) for r in read_jsonl(AGENTS / name)])
        else:
            shutil.copy(AGENTS / name, run / name)
