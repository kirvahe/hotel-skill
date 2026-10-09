#!/usr/bin/env python3
"""Stage transitions of the find-hotel run: every step between the model's own work (U12).

The model asks the questions, spawns the agents and writes the judgment files
(fit-rules.json, taste.json, verdicts.json, advice.json). This script does the
rest: it starts and resumes runs, builds the agents' prompts from the contract,
checks what the agents wrote, runs the pipeline scripts and the engine reader,
applies the checkpoint reply and writes the answer and the city cache.

Usage (RUN is the run folder, DATA the skill's data folder):
    orchestrate.py caps [--contract FILE]                    are the agents' caps approved? (exit 3 when not)
    orchestrate.py resume --data DATA [--city NAME]          open runs and the stage file to continue at
    orchestrate.py start --data DATA --city NAME --country NAME --languages "A = …, B = English, C = …"
                         --lang CODE --check-in YYYY-MM-DD --check-out YYYY-MM-DD --guests N
                         --budget-max EUR [--budget-min EUR] --dog yes|no [--occasion TAG] [--new]
    orchestrate.py context RUN                               blacklist, past stays, city cache, dog note
    orchestrate.py fanout RUN research|resolver|final [--batches N] [--contract FILE]
                                                             agent prompts; stops while caps await approval
    orchestrate.py collect RUN [--returned FAMILY ...] [--reprompted FAMILY ...]
    orchestrate.py filter RUN                                merge, research summary, fit filter
    orchestrate.py resolved RUN                              resolver files in, fit filter again
    orchestrate.py availability RUN [--reader-fixtures DIR]  engine reader on what still needs a read, status table
    orchestrate.py ask RUN [--lang CODE]                     the shortlist and the question-tool payload
    orchestrate.py checkpoint RUN REPLY_FILE [--reader-fixtures DIR]
    orchestrate.py finalized RUN                             final-check files in, status again
    orchestrate.py module RUN NAME ran|partial|skipped|failed [--reason TEXT]
    orchestrate.py answer RUN [--lang CODE]                  render, output check, city cache, done
    orchestrate.py close RUN --reason TEXT                   end a run without an answer (stale or abandoned)

Every command prints JSON. Exit codes: 0 done; 1 the answer failed the output
check; 2 a missing or invalid input (the message says which); 3 stop and tell
the user (caps await approval, or an open run would be overwritten).
--reader-fixtures reads saved pages ({id}--{check_in}.html, else {id}.html)
instead of opening a browser; tests use it, a real run never does.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import apply_reply
import blacklist as blacklist_parser
import check_output
import citycache
import fit_filter
import ledger
import merge_candidates
import render
import runfiles
import stays as stays_parser
import status_table
from engine_reader import EXIT_OK, EXIT_REFUSED, EXIT_SKIPPED

BIN = Path(__file__).resolve().parent
SKILL = BIN.parent
CONTRACT = SKILL / "references" / "briefs" / "research-contract.md"
READER = [sys.executable, str(BIN / "engine_reader.py")]
# Reader limits the user approved after the reader's live smoke (references/briefs/final-check.md).
PAGE_TIMEOUT_S, GIVE_UP_AFTER_S = 20, 45
# The reader stops itself at the give-up; this outer limit only catches a hung browser process.
HUNG_READER_S = 2 * GIVE_UP_AFTER_S
FAMILIES = ledger.FAMILIES
STAGE_FILES = {"intake": "1-intake.md", "context": "2-context.md", "research": "3-research.md",
               "filter": "4-filter.md", "availability": "5-availability.md", "shortlist": "6-shortlist.md",
               "final": "7-final.md", "answer": "8-answer.md"}
AGENT_MODEL = "opus"  # KTD14: research, resolver and final-check agents run on Opus
NO_BROWSER = "background browser not installed"
CAP_LABELS = {"threads read in full": "thread cap", "sub scans": "scan cap", "pages per scan": "scan pages"}
APPROVAL = "set at approval"


class Stop(Exception):
    """Stop and tell the user: the payload's message says why. The CLI exits 3."""

    def __init__(self, payload: dict):
        super().__init__(payload.get("message", ""))
        self.payload = payload


def _stage_file(stage: str):
    return f"workflows/find-hotel/{STAGE_FILES[stage]}" if stage in STAGE_FILES else None


def _set_stage(run: Path, stage: str, waiting=()) -> None:
    ledger.write_state(run, stage=stage, waiting_for=list(waiting))


def _iso(day) -> str:
    return (day or date.today()).isoformat()


def _english(why: list) -> str:
    return render.why_text(why, render.LABELS["en"])


# ---------------------------------------------------------------- start and resume

def resume(data: Path, city: str | None = None, today: date | None = None) -> dict:
    """Runs not finished: open ones (trip still ahead) and stale ones (check-in already past)."""
    today_text, slug = _iso(today), ledger.city_slug(city) if city else None
    open_runs, stale = [], []
    for state_path in sorted(Path(data).glob("trips/*/run/state.json")):
        run = state_path.parent
        try:
            trip = runfiles.load_trip(run)
        except runfiles.RunError:
            continue
        state = ledger.read_state(run)
        if state.get("stage") == "done" or (slug and trip["city_slug"] != slug):
            continue
        info = {"run_dir": str(run), "city": trip["city"], "check_in": trip["check_in"],
                "check_out": trip["check_out"], "stage": state["stage"], "stage_file": _stage_file(state["stage"]),
                "waiting_for": state.get("waiting_for", []), "updated": state.get("updated", ""),
                "lang": trip.get("lang", "en")}
        (stale if trip["check_in"] < today_text else open_runs).append(info)
    open_runs.sort(key=lambda r: r["updated"], reverse=True)
    return {"open_runs": open_runs, "stale": stale}


def close(run: Path, reason: str) -> dict:
    """End a run without an answer: a stale run (dates past) or one the user abandons. Nothing else changes."""
    run = Path(run)
    runfiles.load_trip(run)
    state = ledger.write_state(run, stage="done", waiting_for=[])
    state["closed_reason"] = reason
    runfiles.write_json(run / runfiles.STATE, state)
    return {"run_dir": str(run), "stage": "done", "closed_reason": reason}


def _archive(run: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target, n = run.with_name(f"run-{stamp}"), 2
    while target.exists():
        target, n = run.with_name(f"run-{stamp}-{n}"), n + 1
    run.rename(target)
    return target


def start(data: Path, *, city: str, country: str, languages: str, lang: str, check_in: str, check_out: str,
          guests: int, budget_max: float, dog: bool, budget_min: float = 0, occasion: str = "",
          new: bool = False, today: date | None = None) -> dict:
    """Open the run folder for a trip. An unfinished run for the same city and month is never overwritten."""
    data = Path(data)
    run = data / "trips" / f"{ledger.city_slug(city)}-{check_in[:7]}" / "run"
    archived = None
    if run.exists():
        state = ledger.read_state(run)
        old = runfiles.optional_json(run, runfiles.TRIP, {})
        still_open = state.get("stage") != "done" and str(old.get("check_in", "")) >= _iso(today)
        if still_open and not new:
            raise Stop({"status": "open_run", "run_dir": str(run), "stage": state["stage"],
                        "stage_file": _stage_file(state["stage"]),
                        "message": f"An unfinished run for {old.get('city', city)} {old.get('check_in')} → "
                                   f"{old.get('check_out')} is at stage '{state['stage']}'. Continue it, or start "
                                   "again with --new (the old run folder is archived, not deleted)."})
        archived = str(_archive(run))
    try:
        run = ledger.init_run(data, city=city, check_in=check_in, check_out=check_out, guests=guests,
                              budget_min=budget_min, budget_max=budget_max, dog=dog)
    except ValueError as error:
        raise runfiles.RunError(f"trip: {error}")
    trip = runfiles.load_trip(run)
    trip.update(country=country, languages=languages, lang=lang, occasion=occasion)
    runfiles.write_json(run / runfiles.TRIP, trip)
    _set_stage(run, "context")
    return {"run_dir": str(run), "archived": archived, "stage": "context", "stage_file": _stage_file("context")}


# ---------------------------------------------------------------- stage 2: context

def _pet_section(profile: Path) -> str:
    if not profile.is_file():
        return ""
    lines, inside, comment = [], False, False
    for line in profile.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Pet"
            continue
        if not inside or line.strip() == "---":
            continue
        text = line.strip()
        if comment or text.startswith("<!--"):
            comment = "-->" not in text
            continue
        if text:
            lines.append(text)
    return " ".join(lines)


def _write_stays(run: Path, data: Path) -> int:
    history = data / "booking-history.md"
    rows = stays_parser.parse(history.read_text(encoding="utf-8")) if history.is_file() else []
    gmail = runfiles.optional_json(run, runfiles.GMAIL, None)
    if isinstance(gmail, dict) and not ledger.validate_gmail(gmail):
        known = {(runfiles.name_key(s["hotel"]), s["date"]) for s in rows}
        for booking in gmail["bookings"]:
            if (runfiles.name_key(booking["hotel"]), booking["check_in"]) in known:
                continue
            rows.append({"hotel": booking["hotel"], "city": booking.get("city", ""), "date": booking["check_in"],
                         "rating": "", "comment": "", "rated": False,
                         "upcoming": booking["check_in"] > date.today().isoformat(), "section": "gmail"})
    runfiles.write_json(run / runfiles.STAYS, {"stays": rows, "counts": {"total": len(rows)}})
    return len(rows)


def context(run: Path, data: Path | None = None) -> dict:
    """Stage 2: the blacklist (feedback files and the cache's Excluded lines), past stays, the city cache, the dog note."""
    run = Path(run)
    data = Path(data) if data else runfiles.data_dir(run)
    trip = runfiles.load_trip(run)
    rows, skipped, _ = blacklist_parser.read_folder(data / "feedback")
    cache = citycache.read(data / "cities" / f"{trip['city_slug']}.md")
    for item in cache["excluded"]:
        rows.append({"hotel": item["name"], "city": trip["city"], "reason": f"city cache: {item['reason']}".rstrip(": "),
                     "source": "city cache", "file": f"cities/{trip['city_slug']}.md"})
    runfiles.write_json(run / runfiles.BLACKLIST, {"blacklist": rows, "skipped": skipped,
                                                   "note": f"{len(rows)} blacklisted hotel(s)"})
    stays = _write_stays(run, data)
    pet = _pet_section(data / "taste-profile.md")
    dog_note = (pet or "the profile does not describe the dog") if trip["dog"] else "none (the dog does not travel on this trip)"
    runfiles.write_json(run / runfiles.CONTEXT, {"dog_note": dog_note, "profile": str(data / "taste-profile.md"),
                                                 "cache": dict(cache, slices=citycache.slices(cache["sources"]))})
    if ledger.read_state(run).get("stage") in ("intake", "context"):
        _set_stage(run, "context")
    return {"blacklist": len(rows), "skipped_feedback": skipped, "stays": stays, "dog_note": dog_note,
            "cache": {"exists": cache["exists"], "sources": len(cache["sources"]),
                      "struck_out": len(cache["struck_out"]), "excluded": len(cache["excluded"])},
            "needs": [name for name in (runfiles.FIT_RULES, runfiles.TASTE) if not (run / name).is_file()]}


# ---------------------------------------------------------------- caps and prompts

def _cap_value(cell: str):
    text = cell.strip().strip("`").strip()
    if not text or text == "—":
        return "n/a"
    return None if APPROVAL in text else text


def parse_caps(text: str) -> dict:
    """Caps per agent from the contract's Caps table; None marks a value still awaiting approval."""
    section = text.split("## Caps", 1)[1].split("\n## ", 1)[0] if "## Caps" in text else ""
    agents = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|") or len(cells) < 4 or cells[0] in ("Agent", "") or set(cells[0]) <= set("-: "):
            continue
        name = "final-check" if cells[0] == "final check" else cells[0]
        per = " per candidate" if name in ("resolver", "final-check") else ""
        caps = {f"query cap{per}": _cap_value(cells[1]), f"fetch cap{per}": _cap_value(cells[2])}
        for part in filter(None, (p.strip() for p in cells[3].split(";"))):
            label, _, value = part.partition(":")
            caps[CAP_LABELS.get(label.strip(), label.strip())] = _cap_value(value)
        agents[name] = {k: v for k, v in caps.items() if v != "n/a"}
    match = re.search(r"remainingCredits` is at least `([^`]+)`", text)
    floor = _cap_value(match.group(1)) if match else None
    pending = [f"{agent}: {cap}" for agent, caps in agents.items() for cap, value in caps.items() if value is None]
    if floor is None:
        pending.append("Firecrawl credit floor")
    return {"agents": agents, "credit_floor": floor, "pending": pending}


def _caps_for(names: list, contract: Path) -> dict:
    caps = parse_caps(Path(contract).read_text(encoding="utf-8"))
    pending = [p for p in caps["pending"] if p == "Firecrawl credit floor" or p.split(":")[0] in names]
    missing = [n for n in names if n not in caps["agents"]]
    if pending or missing:
        raise Stop({"status": "caps_pending", "pending": pending + [f"{n}: no caps row" for n in missing],
                    "message": "The search and fetch caps and the Firecrawl credit floor await your approval "
                               "(references/briefs/research-contract.md, Caps). No agent was started. Once the numbers "
                               "are written into the contract, the search can run; an open run continues from its stage."})
    return caps


def caps(contract: Path = CONTRACT) -> dict:
    """Stage 1's first check: every agent's caps and the credit floor approved, or Stop before any run starts."""
    _caps_for(list(FAMILIES) + ["resolver", "final-check"], contract)
    return {"status": "approved", "pending": []}


def _load_inputs(run: Path) -> tuple[dict, dict]:
    fit_filter.load_rules(run)
    taste = runfiles.load_json(run, runfiles.TASTE, "write it from the profile first: "
                                                    '{"taste_summary": "...", "judgment_rules": ["..."]}')
    if not (isinstance(taste.get("taste_summary"), str) and taste["taste_summary"].strip()
            and isinstance(taste.get("judgment_rules"), list)
            and all(isinstance(r, str) for r in taste["judgment_rules"])):
        raise runfiles.RunError('taste.json must be {"taste_summary": "non-empty text", "judgment_rules": ["...", ...]}')
    ctx = runfiles.load_json(run, runfiles.CONTEXT, "run orchestrate.py context first")
    return taste, ctx


def _prompt(agent: str, brief: str, values: dict, caps: dict, floor: str, batch=None) -> str:
    head = f"You are the {agent} agent of a /hotel find-hotel run" + (f", batch {batch}" if batch else "") + "."
    lines = [head, "", "Prompt values (use each wherever its placeholder appears in the contract and your brief):"]
    for key, value in values.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        lines.append(f"- {{{key}}}: {text}")
    lines += ["", "Caps approved by the user (they stand for the \"set at approval\" placeholders):"]
    lines += [f"- {name}: {value}" for name, value in caps.items()] + [f"- Firecrawl credit floor: {floor}"]
    lines += ["", f"Read {SKILL}/references/briefs/research-contract.md and {SKILL}/references/briefs/{brief} "
                  "in full before your first tool call, then do the task. Your final message is only what the "
                  "contract's last section defines."]
    return "\n".join(lines)


def _official_urls(run: Path, merged: list) -> dict:
    lines = runfiles.optional_json(run, runfiles.RESOLVED, {"resolved": []}).get("resolved", [])
    by_id, _ = runfiles.match_by_name(merged, lines)
    out = {}
    for candidate in merged:
        resolved = [(line.get("official_url") or {}).get("value") for line in by_id[candidate["id"]]]
        out[candidate["id"]] = next((u for u in reversed(resolved) if u), "") or candidate.get("official_url", "")
    return out


def _batches(items: list, count: int) -> list:
    count = max(1, min(count, len(items)))
    size, extra = divmod(len(items), count)
    out, start = [], 0
    for n in range(count):
        end = start + size + (1 if n < extra else 0)
        out.append(items[start:end])
        start = end
    return out


def fanout(run: Path, step: str, batches: int | None = None, contract: Path = CONTRACT) -> dict:
    """Prompts for the agents of one step, ready to pass to the Agent tool in one message."""
    run = Path(run)
    trip = runfiles.load_trip(run)
    taste, ctx = _load_inputs(run)
    common = {"skill": str(SKILL), "run_dir": str(run), "city": trip["city"], "country": trip.get("country", ""),
              "languages": trip.get("languages", ""), "check_in": trip["check_in"], "check_out": trip["check_out"],
              "guests": str(trip["guests"]), "dog": "true" if trip["dog"] else "false"}
    if step == "research":
        caps = _caps_for(list(FAMILIES), contract)
        slices = (ctx.get("cache") or {}).get("slices") or {}
        agents = [{"name": family, "brief": f"{family}.md",
                   "prompt": _prompt(family, f"{family}.md", dict(common, taste_summary=taste["taste_summary"],
                                                                    source_map_slice=slices.get(family) or "none"),
                                     caps["agents"][family], caps["credit_floor"])}
                  for family in FAMILIES]
        waiting = list(FAMILIES)
        _set_stage(run, "research", waiting)
        return {"status": "ready", "stage": "research", "model": AGENT_MODEL, "agents": agents, "waiting_for": waiting}
    if step not in ("resolver", "final"):
        raise runfiles.RunError("fanout step must be research, resolver or final")
    if not batches or batches < 1:
        raise runfiles.RunError("--batches N is required for the resolver and the final check")
    merged = runfiles.load_merged(run)
    urls = _official_urls(run, merged)
    by_id = {c["id"]: c for c in merged}
    if step == "resolver":
        fit = runfiles.load_json(run, runfiles.FIT, "run orchestrate.py filter first")
        struck = runfiles.active_strikes(runfiles.read_checkpoints(run))
        ids = [c["id"] for c in runfiles.kept_hotels(fit, struck)]
        no_url = []
    else:
        view = render.build_view(run)
        kept = [e["id"] for e in view["hotels"] + view["beyond"]]
        ids = [cid for cid in kept if urls.get(cid)]
        no_url = [by_id[cid]["name"] for cid in kept if not urls.get(cid)]
    if not ids:
        module = "resolver" if step == "resolver" else "final_check"
        why = [{"code": "no_candidates" if step == "resolver" else ("no_official_site" if no_url else "kept_nothing")}]
        record = set_module(run, module, "skipped", why=why)
        if step == "final":
            _set_stage(run, "answer")
        return {"status": "nothing_to_resolve" if step == "resolver" else "nothing_to_check",
                "reason": record["reason"], "no_url": no_url}
    agent = "resolver" if step == "resolver" else "final-check"
    caps = _caps_for([agent], contract)
    extra = {"judgment_rules": taste["judgment_rules"]} if step == "resolver" else {}
    agents, plan = [], {}
    for n, part in enumerate(_batches(ids, batches), 1):
        candidates = [{"name": by_id[cid]["name"], "area": by_id[cid].get("area", ""), "official_url": urls.get(cid) or None}
                      for cid in part]
        values = dict(common, batch=str(n), candidates=candidates, dog_note=ctx["dog_note"], **extra)
        agents.append({"name": f"{agent}-{n}", "batch": n, "brief": f"{agent}.md", "candidates": candidates,
                       "prompt": _prompt(agent, f"{agent}.md", values, caps["agents"][agent], caps["credit_floor"], n)})
        plan[str(n)] = [c["name"] for c in candidates]
    batches_doc = runfiles.optional_json(run, runfiles.BATCHES, {})
    batches_doc[step] = plan
    runfiles.write_json(run / runfiles.BATCHES, batches_doc)
    waiting = [a["name"] for a in agents]
    stage = "availability" if step == "resolver" else "final"
    _set_stage(run, stage, waiting)
    return {"status": "ready", "stage": stage, "model": AGENT_MODEL, "agents": agents, "waiting_for": waiting,
            "no_url": no_url}


# ---------------------------------------------------------------- stage 3: collect the families

def _check_family(run: Path, family: str) -> dict:
    candidates = run / runfiles.CANDIDATES.format(family=family)
    envelope_path = run / runfiles.ENVELOPE.format(family=family)
    envelope, problems = None, []
    if envelope_path.is_file():
        try:
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            problems += [f"{envelope_path.name}: {p}" for p in ledger.validate_envelope(envelope)]
        except json.JSONDecodeError as error:
            problems.append(f"{envelope_path.name}: not valid JSON ({error.msg})")
    else:
        problems.append(f"{envelope_path.name} is missing")
    records, rejected = [], []
    if candidates.is_file():
        records, rejected = ledger.read_records(candidates, "candidate")
    elif not (envelope and envelope.get("status") == "failed"):
        problems.append(f"{candidates.name} is missing")
    invalid = [f"{candidates.name} line {r['line']}: {p}" for r in rejected for p in r["problems"]]
    return {"envelope": envelope, "problems": problems, "invalid": invalid, "invalid_lines": len(rejected),
            "valid": len(records)}


def collect(run: Path, returned=(), reprompted=()) -> dict:
    """Track the family agents; re-prompt a family once for invalid output, then report it as partial."""
    run = Path(run)
    state = ledger.read_state(run)
    doc = runfiles.optional_json(run, runfiles.FAMILIES, {"families": {}})
    families = doc.setdefault("families", {})
    waiting = [w for w in state.get("waiting_for", []) if w not in returned]
    for family in reprompted:
        families.setdefault(family, {})["reprompted"] = True
        if family not in waiting:
            waiting.append(family)
    runfiles.write_json(run / runfiles.FAMILIES, doc)
    if waiting:
        _set_stage(run, "research", waiting)
        return {"status": "waiting", "waiting_for": waiting}
    reprompt, results = [], {}
    for family in FAMILIES:
        check = _check_family(run, family)
        problems = check["problems"] + check["invalid"]
        reprompted_before = bool(families.get(family, {}).get("reprompted"))
        if problems and not reprompted_before:
            reprompt.append({"family": family, "problems": problems[:20],
                             "message": "Fix every line listed, re-run both ledger validations until they print OK, "
                                        "then return the envelope again."})
            continue
        envelope = check["envelope"] or {}
        status = {"complete": "ran", "partial": "partial", "failed": "failed"}.get(envelope.get("status"), "failed")
        invalid = check["invalid_lines"]
        why = [{"code": "text", "text": envelope["reason"]}] if envelope.get("reason") else []
        if problems:
            why += [{"code": "reprompt_invalid", "count": invalid}] if invalid else []
            why += [{"code": "text", "text": p} for p in check["problems"]]
            status = "partial" if check["valid"] else "failed"
        results[family] = {"status": status, "reason": _english(why), "why": why, "records": check["valid"],
                           "invalid": invalid, "reprompted": reprompted_before}
    if reprompt:
        _set_stage(run, "research")
        return {"status": "reprompt", "reprompt": reprompt}
    runfiles.write_json(run / runfiles.FAMILIES, {"families": results})
    _set_stage(run, "filter")
    return {"status": "ready", "families": results}


# ---------------------------------------------------------------- stage 4: merge and filter

def _research_summary(run: Path) -> dict:
    out = {"source_map": [], "district_notes": [], "negative_reports": [], "notes": []}
    for family in FAMILIES:
        envelope = runfiles.optional_json(run, runfiles.ENVELOPE.format(family=family), None)
        if not isinstance(envelope, dict):
            continue
        for key in out:
            out[key] += [dict(item, family=family) for item in envelope.get(key) or [] if isinstance(item, dict)]
    runfiles.write_json(run / runfiles.RESEARCH, out)
    return out


def filter_stage(run: Path) -> dict:
    """Stage 4: past stays (with Gmail), the research summary, merge and the mechanical fit filter."""
    run = Path(run)
    trip = runfiles.load_trip(run)
    fit_filter.load_rules(run)
    _write_stays(run, runfiles.data_dir(run))
    research = _research_summary(run)
    merge = merge_candidates.merge_run(run)
    fit = fit_filter.filter_run(run)
    pet = None
    if trip["dog"]:
        pet = Counter()
        for c in fit["candidates"]:
            value = "not allowed" if c["reason_code"] == "pet_not_allowed" else (c.get("pet") or {}).get("value", "unknown")
            if c["block"] == "hotels" and (c["decision"] == "keep" or c["reason_code"] == "pet_not_allowed"):
                pet[value] += 1
    _set_stage(run, "availability")
    return {"merge": merge, "fit": {"skip_lines": fit["skip_lines"], "counts": fit["counts"]}, "pet": pet,
            "research": {k: len(v) for k, v in research.items()}}


# ---------------------------------------------------------------- stage 5: resolver and availability

def _agent_files(run: Path, step: str, part: str, kind: str) -> tuple[list, list, list]:
    """(valid lines, rejected lines, missing batch numbers) for one fan-out step."""
    plan = runfiles.optional_json(run, runfiles.BATCHES, {}).get(step) or {}
    lines, rejected, missing = [], [], []
    for batch in sorted(plan, key=int):
        path = run / part.format(batch=batch)
        if not path.is_file():
            missing.append(batch)
            continue
        valid, bad = ledger.read_records(path, kind)
        lines += valid
        rejected += [dict({"file": path.name}, **r) for r in bad]
    return lines, rejected, missing


def _module_status(missing: list, rejected: list, total: int) -> tuple:
    """(status, reason, why) for a fan-out step from its missing batches and rejected lines."""
    if total and len(missing) == total:
        return "failed", "", [{"code": "no_batch"}]
    why = [{"code": "missing_batch", "batch": b} for b in missing]
    why += [{"code": "invalid_lines", "count": len(rejected)}] if rejected else []
    return ("partial" if why else "ran"), "", why


def resolved(run: Path) -> dict:
    """Stage 5a: the resolver's official sites, closures, pet policies and judgment calls."""
    run = Path(run)
    lines, rejected, missing = _agent_files(run, "resolver", runfiles.RESOLVED_PART, "resolved")
    total = len(runfiles.optional_json(run, runfiles.BATCHES, {}).get("resolver") or {})
    runfiles.write_json(run / runfiles.RESOLVED, {"resolved": lines, "rejected": rejected})
    evidence = runfiles.merge_evidence(run)
    fit = fit_filter.filter_run(run)
    module = set_module(run, "resolver", *_module_status(missing, rejected + evidence["rejected"], total))
    _set_stage(run, "availability")
    return {"module": module, "resolved": len(lines), "rejected": rejected, "evidence": evidence,
            "skip_lines": fit["skip_lines"], "counts": fit["counts"]}


def _fixture_for(fixtures: Path, cid: str, check_in: str):
    for name in (f"{cid}--{check_in}.html", f"{cid}.html"):
        if (Path(fixtures) / name).is_file():
            return Path(fixtures) / name
    return None


def _over_budget(run: Path, trip: dict, fit: dict, status: dict, struck: dict, merged: list) -> list:
    """Kept hotels priced above the budget, with the model's R25 verdict on each. A verdict names a
    hotel by any of its names, as render.build_view matches it; a not_better verdict wins over a
    clearly_better one for the same hotel."""
    nights = runfiles.nights(trip)
    verdicts = runfiles.optional_json(run, runfiles.VERDICTS, {})
    by_id = {c["id"]: c for c in merged}
    pool = []
    for c in runfiles.kept_hotels(fit, struck):
        state = status.get(c["id"]) or {}
        if state.get("status") != "available":
            continue
        per_night = render.nightly(state["price_eur"], state.get("price_basis") or "per_night", nights)
        if per_night > trip["budget"]["max"]:
            candidate = by_id.get(c["id"], c)
            verdict = None
            for key in ("clearly_better", "not_better"):
                if runfiles.records_naming(candidate, verdicts.get(key) or []):
                    verdict = key
            pool.append({"name": c["name"], "price_eur": state["price_eur"], "price_basis": state.get("price_basis"),
                         "verdict": verdict})
    return pool


def availability(run: Path, reader_fixtures: Path | None = None, reader: list | None = None) -> dict:
    """Stage 5b: read each kept hotel's own engine once per set of dates, then the status table."""
    run = Path(run)
    trip = runfiles.load_trip(run)
    runfiles.merge_evidence(run)
    status = status_table.status_run(run)["candidates"]
    fit = runfiles.load_json(run, runfiles.FIT, "run orchestrate.py filter first")
    struck = runfiles.active_strikes(runfiles.read_checkpoints(run))
    merged = runfiles.load_merged(run)
    urls = _official_urls(run, merged)
    reads = runfiles.optional_json(run, runfiles.READS, {"reads": {}})
    dates = (trip["check_in"], trip["check_out"])
    read, not_read, kinds, skipped_reader = [], [], Counter(), False
    for c in runfiles.kept_hotels(fit, struck):
        cid = c["id"]
        why = None
        if status[cid]["reason"] == "closure":
            why = "closed on the trip dates"
        elif any((r["check_in"], r["check_out"]) == dates for r in reads["reads"].get(cid, [])):
            why = "already read for these dates"
        elif not urls.get(cid):
            why = "no official site found"
        elif skipped_reader:
            why = NO_BROWSER
        fixture = _fixture_for(reader_fixtures, cid, trip["check_in"]) if reader_fixtures and not why else None
        if reader_fixtures and not why and fixture is None:
            why = "no saved page (fixture mode)"
        if why:
            not_read.append({"name": c["name"], "why": why})
            continue
        command = (reader or READER) + [
            "--candidate", c["name"], "--url", urls[cid], "--check-in", trip["check_in"],
            "--check-out", trip["check_out"], "--guests", str(trip["guests"]),
            "--out", str(run / runfiles.READER_EVIDENCE),
            "--page-timeout-s", str(PAGE_TIMEOUT_S), "--give-up-after-s", str(GIVE_UP_AFTER_S)]
        if fixture:
            command += ["--fixture", str(fixture)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=HUNG_READER_S)
            code, out = result.returncode, result.stdout
        except subprocess.TimeoutExpired:
            code, out = -1, ""
        if code == EXIT_SKIPPED:
            skipped_reader = True
            not_read.append({"name": c["name"], "why": NO_BROWSER})
            continue
        if code in (EXIT_OK, EXIT_REFUSED):
            kind = json.loads(out.strip().splitlines()[-1]).get("kind", "") if out.strip() else ""
            kinds[kind] += 1
            reads["reads"].setdefault(cid, []).append({"check_in": dates[0], "check_out": dates[1], "exit": code,
                                                       "url": urls[cid], "at": ledger.now()})
            read.append({"name": c["name"], "kind": kind})
        else:
            not_read.append({"name": c["name"], "why": f"reader error (exit {code})"})
    runfiles.write_json(run / runfiles.READS, reads)
    evidence = runfiles.merge_evidence(run)
    table = status_table.status_run(run)
    status = table["candidates"]
    modules = runfiles.optional_json(run, runfiles.MODULES, {}).get("modules") or {}
    if skipped_reader:
        reader_module = set_module(run, "reader", "skipped", why=[{"code": "reader_missing"}])
    elif read:
        reader_module = set_module(run, "reader", "ran")
    elif modules.get("reader"):
        reader_module = modules["reader"]
    else:
        reader_module = set_module(run, "reader", "skipped", why=[{"code": "nothing_to_read"}])
    count = len(render.shown(render.build_view(run)))
    if count:
        _set_stage(run, "shortlist")
    else:
        set_module(run, "final_check", "skipped", why=[{"code": "nothing_passed"}])
        _set_stage(run, "answer")
    return {"read": read, "read_kinds": kinds, "not_read": not_read, "reader": reader_module, "status": table["counts"],
            "rejected_evidence": evidence["rejected"], "entries": count,
            "over_budget": _over_budget(run, trip, fit, status, struck, merged),
            "next": "shortlist" if count else "answer"}


# ---------------------------------------------------------------- stage 6: the checkpoint

def ask(run: Path, lang: str | None = None) -> dict:
    run = Path(run)
    return render.question_payload(run, lang or runfiles.load_trip(run).get("lang") or "en")


def checkpoint(run: Path, reply: dict, reader_fixtures: Path | None = None, reader: list | None = None,
               today: date | None = None) -> dict:
    """Apply one reply: strike-outs first (R15, into the city cache), then a change re-runs the checks (R24)."""
    run = Path(run)
    applied = apply_reply.apply(run, reply)
    write_cache(run, final=False, today=today)
    checked = availability(run, reader_fixtures, reader) if applied["changed"] else None
    # After a change, availability has just counted the entries and built the over-budget pool from these
    # same files; what it wrote since (stage, modules) changes neither.
    count = checked["entries"] if checked else len(render.shown(render.build_view(run)))
    if not count:
        nxt = "answer"
        set_module(run, "final_check", "skipped", why=[{"code": "kept_nothing" if applied["struck"] else "nothing_passed"}])
    else:
        nxt = "shortlist" if applied["changed"] else "final"
    _set_stage(run, nxt)
    if checked:
        over_budget = checked["over_budget"]
    else:
        trip = runfiles.load_trip(run)
        fit = runfiles.load_json(run, runfiles.FIT, "run orchestrate.py filter first")
        status = runfiles.load_json(run, runfiles.STATUS, "run orchestrate.py availability first")["candidates"]
        over_budget = _over_budget(run, trip, fit, status, runfiles.active_strikes(runfiles.read_checkpoints(run)),
                                   runfiles.load_merged(run))
    return {"apply": applied, "availability": checked, "entries": count, "next": nxt, "over_budget": over_budget}


# ---------------------------------------------------------------- stage 7: final check

def finalized(run: Path) -> dict:
    """Stage 7: the final check's rates and evidence; removal only on R12 evidence."""
    run = Path(run)
    before = runfiles.load_json(run, runfiles.STATUS, "run orchestrate.py availability first")["candidates"]
    lines, rejected, missing = _agent_files(run, "final", runfiles.FINAL_PART, "final")
    plan = runfiles.optional_json(run, runfiles.BATCHES, {}).get("final") or {}
    runfiles.write_json(run / runfiles.FINAL, {"final": lines, "rejected": rejected})
    evidence = runfiles.merge_evidence(run)
    fit_filter.filter_run(run)
    after = status_table.status_run(run)["candidates"]
    merged = runfiles.load_merged(run)
    names = [n for batch in plan.values() for n in batch]
    ids, _ = runfiles.match_by_name(merged, [{"candidate": n} for n in names])
    checked = [cid for cid, hits in ids.items() if hits]
    removed, changed, unknown = [], [], []
    for cid in checked:
        old, new = before.get(cid, {}), after[cid]
        if new["status"] == "unavailable" and old.get("status") != "unavailable":
            removed.append({"name": new["name"], "reason": new["reason"], "quote": new["quote"]})
        elif new["status"] == "available" and old.get("status") == "available" and new["price_eur"] != old.get("price_eur"):
            changed.append({"name": new["name"], "before": old["price_eur"], "after": new["price_eur"]})
        elif new["status"] == "unknown":
            unknown.append({"name": new["name"], "reason": new["reason"]})
    module = set_module(run, "final_check", *_module_status(missing, rejected + evidence["rejected"], len(plan)))
    _set_stage(run, "answer")
    return {"module": module, "removed": removed, "price_changed": changed, "unknown": unknown, "rejected": rejected}


# ---------------------------------------------------------------- modules, answer and city cache

def set_module(run: Path, name: str, status: str, reason: str = "", why: list | None = None) -> dict:
    """Record a module's status (R22). Scripts pass reason codes (why), which the answer shows in the
    request language; the model passes a reason written in the request language."""
    if name not in runfiles.MODULES_ORDER:
        raise runfiles.RunError(f"module must be one of {', '.join(runfiles.MODULES_ORDER)}")
    if status not in runfiles.STATUSES:
        raise runfiles.RunError(f"status must be one of {', '.join(runfiles.STATUSES)}")
    record = {"status": status, "reason": _english(why) if why else reason}
    if why:
        record["why"] = why
    doc = runfiles.optional_json(run, runfiles.MODULES, {"modules": {}})
    doc.setdefault("modules", {})[name] = record
    runfiles.write_json(Path(run) / runfiles.MODULES, doc)
    return record


def write_cache(run: Path, final: bool, today: date | None = None, view: dict | None = None) -> Path:
    """Write this run into the city cache: sources (R3), strike-outs with reasons (R15) and, at the end, picks.
    A final write takes the answer's view when the caller has one."""
    run = Path(run)
    trip = runfiles.load_trip(run)
    run_id = runfiles.trip_dir(run).name
    research = runfiles.optional_json(run, runfiles.RESEARCH, {})
    sources = [{"family": s.get("family", ""), "outlet": s.get("outlet", ""), "kind": s.get("kind", ""),
                "language": s.get("language", ""), "where": s.get("url") or s.get("query") or s.get("outlet", ""),
                "yield": s.get("yield", "")} for s in research.get("source_map") or []]
    checkpoints = runfiles.read_checkpoints(run)
    dates = {c["n"]: c.get("at", "")[:10] for c in checkpoints}
    struck = [{"name": s["name"], "reason": s.get("reason", ""), "date": dates.get(s["checkpoint"], ""), "trip": run_id}
              for s in runfiles.active_strikes(checkpoints).values()]
    picks, summary = [], f"checkpoint {len(checkpoints)}: {len(struck)} struck out"
    if final:
        view = render.build_view(run) if view is None else view
        by_id = {c["id"]: c for c in runfiles.load_merged(run)}
        for entry in view["hotels"] + view["beyond"]:
            score = by_id[entry["id"]].get("score") or {}
            price = f"€{entry['price']:g}/night" if entry["price"] is not None else "price ❓"
            picks.append({"name": entry["name"], "type": by_id[entry["id"]]["kind"], "area": entry["area"],
                          "rating": f"{score['value']:.1f}" if score.get("verified") else "",
                          "notes": f"{trip['check_in'][:7]}: {price} ({run_id})"})
        summary = (f"kept {len(picks)}: " + ", ".join(p["name"] for p in picks)) if picks else "nothing fits"
    searched = (f"{_iso(today)} {run_id}: {trip['check_in']} → {trip['check_out']} · {trip['guests']} guests · "
                f"up to €{trip['budget']['max']:g} · {'with' if trip['dog'] else 'without'} the dog → {summary}")
    return citycache.write(runfiles.data_dir(run) / "cities" / f"{trip['city_slug']}.md", city=trip["city"],
                           today=_iso(today), run_id=run_id, searched=searched, sources=sources,
                           recommended=picks, struck=struck)


def _check_advice(run: Path) -> None:
    advice = runfiles.optional_json(run, runfiles.ADVICE, None)
    if advice is None:
        return
    if not isinstance(advice, dict) or not isinstance(advice.get("entries", []), list):
        raise runfiles.RunError('advice.json must be {"overview", "entries": [{"candidate", "why", "vibe"}], '
                                '"districts": [...], "tips": [...]}')
    merged = runfiles.load_merged(run)
    _, unknown = runfiles.match_by_name(merged, advice.get("entries") or [])
    if unknown:
        raise runfiles.RunError(f"advice.json names hotels this run does not hold: {', '.join(unknown)}")


def answer(run: Path, lang: str | None = None, today: date | None = None) -> dict:
    """Stage 8: render the answer, check it against the ledger, save it, write the city cache, close the run."""
    run = Path(run)
    _check_advice(run)
    trip = runfiles.load_trip(run)
    view = render.build_view(run)
    text = render.render_answer(run, lang or trip.get("lang") or "en", view)
    path = runfiles.trip_dir(run) / runfiles.ANSWER_FILE
    path.write_text(text, encoding="utf-8")
    failures = check_output.check(run, text)
    if failures:
        return {"status": "fail", "failures": failures, "answer_file": str(path)}
    cache = write_cache(run, final=True, today=today, view=view)
    _set_stage(run, "done")
    return {"status": "ok", "answer_file": str(path), "cache_file": str(cache)}


# ---------------------------------------------------------------- command line

def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="find-hotel stage transitions")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("caps").add_argument("--contract", default=str(CONTRACT))
    p = sub.add_parser("resume")
    p.add_argument("--data", required=True)
    p.add_argument("--city")
    p = sub.add_parser("start")
    for name in ("--data", "--city", "--country", "--languages", "--lang", "--check-in", "--check-out"):
        p.add_argument(name, required=True)
    p.add_argument("--guests", type=int, required=True)
    p.add_argument("--budget-max", type=float, required=True)
    p.add_argument("--budget-min", type=float, default=0)
    p.add_argument("--dog", choices=("yes", "no"), required=True)
    p.add_argument("--occasion", default="")
    p.add_argument("--new", action="store_true")
    for name in ("context", "filter", "resolved", "finalized"):
        sub.add_parser(name).add_argument("run")
    p = sub.add_parser("fanout")
    p.add_argument("run")
    p.add_argument("step", choices=("research", "resolver", "final"))
    p.add_argument("--batches", type=int)
    p.add_argument("--contract", default=str(CONTRACT))
    p = sub.add_parser("collect")
    p.add_argument("run")
    p.add_argument("--returned", nargs="*", default=[], choices=FAMILIES)
    p.add_argument("--reprompted", nargs="*", default=[], choices=FAMILIES)
    p = sub.add_parser("availability")
    p.add_argument("run")
    p.add_argument("--reader-fixtures")
    p = sub.add_parser("ask")
    p.add_argument("run")
    p.add_argument("--lang")
    p = sub.add_parser("checkpoint")
    p.add_argument("run")
    p.add_argument("reply_file")
    p.add_argument("--reader-fixtures")
    p = sub.add_parser("module")
    p.add_argument("run")
    p.add_argument("name")
    p.add_argument("status")
    p.add_argument("--reason", default="")
    p = sub.add_parser("answer")
    p.add_argument("run")
    p.add_argument("--lang")
    p = sub.add_parser("close")
    p.add_argument("run")
    p.add_argument("--reason", required=True)
    args = parser.parse_args(argv[1:])

    run = Path(args.run).expanduser() if getattr(args, "run", None) else None
    fixtures = Path(args.reader_fixtures).expanduser() if getattr(args, "reader_fixtures", None) else None
    try:
        if args.cmd == "caps":
            out = caps(Path(args.contract).expanduser())
        elif args.cmd == "resume":
            out = resume(Path(args.data).expanduser(), args.city)
        elif args.cmd == "start":
            out = start(Path(args.data).expanduser(), city=args.city, country=args.country, languages=args.languages,
                        lang=args.lang, check_in=args.check_in, check_out=args.check_out, guests=args.guests,
                        budget_max=args.budget_max, budget_min=args.budget_min, dog=args.dog == "yes",
                        occasion=args.occasion, new=args.new)
        elif args.cmd == "context":
            out = context(run)
        elif args.cmd == "fanout":
            out = fanout(run, args.step, args.batches, Path(args.contract).expanduser())
        elif args.cmd == "collect":
            out = collect(run, args.returned, args.reprompted)
        elif args.cmd == "filter":
            out = filter_stage(run)
        elif args.cmd == "resolved":
            out = resolved(run)
        elif args.cmd == "availability":
            out = availability(run, fixtures)
        elif args.cmd == "ask":
            out = ask(run, args.lang)
        elif args.cmd == "checkpoint":
            out = checkpoint(run, apply_reply.read_reply(args.reply_file), fixtures)
        elif args.cmd == "finalized":
            out = finalized(run)
        elif args.cmd == "module":
            out = set_module(run, args.name, args.status, args.reason)
        elif args.cmd == "close":
            out = close(run, args.reason)
        else:
            out = answer(run, args.lang)
    except Stop as stop:
        print(json.dumps(stop.payload, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if args.cmd == "answer" and out.get("status") != "ok" else 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
