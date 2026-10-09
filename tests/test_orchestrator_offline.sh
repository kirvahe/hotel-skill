#!/usr/bin/env bash
# test_orchestrator_offline.sh — one whole find-hotel run through bin/orchestrate.py, offline (U12).
#
# Every hotel, city, dog and trip is made up. Nothing touches the network: the engine
# reader reads saved pages (tests/fixtures/orchestrator/engines), and the files the
# research, resolver and final-check agents would write are copied from
# tests/fixtures/orchestrator/agents. The steps the model does itself (asking the
# question, spawning agents, writing judgment files) are stood in for by those copies.
# Each run works in a fresh temporary folder. Exit code is non-zero on any failure.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX="$REPO/tests/fixtures/orchestrator"
PIPE="$REPO/tests/fixtures/pipeline"
FAILS=0

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }

orch() { python3 "$REPO/bin/orchestrate.py" "$@"; }

# expect NAME PYTHON_EXPRESSION: true when the expression holds. In the expression,
# J(path) reads JSON, T(path) reads text, L(path) reads JSON lines, RUN and DATA are paths.
expect() {
  local name="$1" expr="$2"
  if RUN="${RUN:-}" DATA="$DATA" python3 - "$expr" <<'EOF'
import json, os, sys
from pathlib import Path
RUN, DATA = Path(os.environ["RUN"] or "."), Path(os.environ["DATA"])
J = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
T = lambda p: Path(p).read_text(encoding="utf-8")
L = lambda p: [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
sys.exit(0 if eval(sys.argv[1]) else 1)
EOF
  then pass "$name"; else fail "$name"; fi
}

ROOT="$(mktemp -d)"
DATA="$ROOT/data"
OUT="$ROOT/out"
CONTRACT="$ROOT/contract-approved.md"
mkdir -p "$OUT"
# The same set-up as the unit tests (tests/fixtures/orchestrator/orchkit.py): DATA/ with the profile,
# the booking history, the feedback files and a warm Testgrad cache, and the real contract with every
# "set at approval" placeholder filled with a synthetic test value (not a proposal: the real caps
# await the user's approval).
python3 - "$FIX" "$ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import orchkit
orchkit.make_data(sys.argv[2])
orchkit.approved_contract(sys.argv[2])
EOF

# ---- Stage 1: intake (the model asked the R1 question; the answers go into start)
orch start --data "$DATA" --city Testgrad --country Testland --languages "A = Spanish, B = English, C = none" \
  --lang en --check-in 2026-11-20 --check-out 2026-11-22 --guests 2 --budget-max 200 --dog no \
  --occasion city-break >"$OUT/start.json"
RUN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_dir"])' "$OUT/start.json")"
expect "start opens the run at stage 2" 'J(RUN/"state.json")["stage"] == "context"'

# ---- Stage 2: context; Gmail tools are absent in this session
orch context "$RUN" >"$OUT/context.json"
cp "$PIPE/run/fit-rules.json" "$RUN/fit-rules.json"
printf '%s' '{"taste_summary": "small hotels with character in historic buildings; no large chains", "judgment_rules": ["large or mainstream hotel (over about 60 rooms)"]}' >"$RUN/taste.json"
orch module "$RUN" gmail skipped --reason "no Gmail tools in this session" >/dev/null
expect "context adds the city cache exclusions to the blacklist" \
  '"Hotel Niebla" in [r["hotel"] for r in J(RUN/"blacklist.json")["blacklist"]]'

# ---- Stage 3: research; caps not approved means no agent starts
orch fanout "$RUN" research >"$OUT/caps.json"; code=$?
expect "with caps still awaiting approval, the fan-out stops (exit 3)" \
  "$code == 3 and J('$OUT/caps.json')['status'] == 'caps_pending' and J(RUN/'state.json')['waiting_for'] == []"
orch fanout "$RUN" research --contract "$CONTRACT" >"$OUT/research.json"
expect "approved caps: three family prompts, waiting for all three" \
  'len(J("'"$OUT"'/research.json")["agents"]) == 3 and J(RUN/"state.json")["waiting_for"] == ["curated-press", "reddit", "booking-search"]'
for family in curated-press reddit booking-search; do
  cp "$PIPE/run/candidates-$family.jsonl" "$RUN/"
  cp "$FIX/agents/envelope-$family.json" "$RUN/"
done
cat "$FIX/agents/invalid-reddit-line.jsonl" >>"$RUN/candidates-reddit.jsonl"
orch collect "$RUN" --returned curated-press reddit booking-search >"$OUT/collect1.json"
expect "a family that wrote an invalid line is re-prompted once" \
  'J("'"$OUT"'/collect1.json")["status"] == "reprompt" and [r["family"] for r in J("'"$OUT"'/collect1.json")["reprompt"]] == ["reddit"]'
orch collect "$RUN" --reprompted reddit >/dev/null
orch collect "$RUN" --returned reddit >"$OUT/collect2.json"   # the re-prompted agent fixed nothing
expect "after one re-prompt the family is reported as partial" \
  'J(RUN/"families.json")["families"]["reddit"]["status"] == "partial" and J(RUN/"state.json")["stage"] == "filter"'

# ---- Stage 4: merge and fit filter
orch filter "$RUN" >"$OUT/filter.json"
expect "the fit filter removes the blacklisted hotel with a skip line" \
  '"Skipped: blacklist — Hotel Ceniza — no soul, like an office" in J("'"$OUT"'/filter.json")["fit"]["skip_lines"]'

# ---- Stage 5: resolver agents, then the engine reader and the status table
orch fanout "$RUN" resolver --batches 2 --contract "$CONTRACT" >/dev/null
cp "$FIX"/agents/resolved-*.jsonl "$FIX"/agents/evidence-resolver-*.jsonl "$RUN/"
orch resolved "$RUN" >/dev/null
orch availability "$RUN" --reader-fixtures "$FIX/engines" >"$OUT/availability.json"
expect "AE2: a closure from the hotel's own site reaches the status table and removes the hotel" \
  'any(s["name"] == "Hotel Invierno" and s["status"] == "unavailable" and s["reason"] == "closure" for s in J(RUN/"status.json")["candidates"].values())'
expect "the engine price for the dates makes a hotel available" \
  'any(s["name"] == "Casa Velarta" and s["price_eur"] == 160 for s in J(RUN/"status.json")["candidates"].values())'
printf '%s' '{"clearly_better": [{"candidate": "Hotel Torre Alta", "reason": "the only valley view in town"}], "not_better": []}' >"$RUN/verdicts.json"

# ---- Stage 6: the shortlist, then a fresh session at the checkpoint
orch ask "$RUN" >"$OUT/ask1.json"
expect "the shortlist is ready for the question tool" 'J("'"$OUT"'/ask1.json")["mode"] == "question"'
orch resume --data "$DATA" >"$OUT/resume.json"
expect "resume finds the run at the checkpoint and names its stage file" \
  'J("'"$OUT"'/resume.json")["open_runs"][0]["stage_file"] == "workflows/find-hotel/6-shortlist.md"'
orch ask "$RUN" >"$OUT/ask2.json"
expect "a fresh session renders the same shortlist" 'J("'"$OUT"'/ask1.json")["text"] == J("'"$OUT"'/ask2.json")["text"]'

number() { # number NAME: the shortlist entry number of a hotel
  python3 - "$OUT/ask2.json" "$1" <<'EOF'
import json, re, sys
text = json.load(open(sys.argv[1]))["text"]
print(next(n for n, name in re.findall(r"^(\d+)\. \*\*(.+?)\*\*", text, re.M) if name == sys.argv[2]))
EOF
}
SOMBRA="$(number "Hotel Sombra")"
PALACIO="$(number "Palacio Ñandú")"
sha() { cat "$@" | shasum | cut -d" " -f1; }
MERGED_BEFORE="$(sha "$RUN/merged.jsonl")"
CANDIDATES_BEFORE="$(sha "$RUN"/candidates-*.jsonl)"

# AE8 with a mixed reply: a strike-out with a reason and new dates
printf '{"strike": [{"number": %s, "reason": "dark rooms"}], "change": {"check_in": "2026-11-27", "check_out": "2026-11-29"}}' "$SOMBRA" >"$OUT/reply1.json"
orch checkpoint "$RUN" "$OUT/reply1.json" --reader-fixtures "$FIX/engines" >"$OUT/checkpoint1.json"
if [[ "$(sha "$RUN/merged.jsonl")" == "$MERGED_BEFORE" && "$(sha "$RUN"/candidates-*.jsonl)" == "$CANDIDATES_BEFORE" ]]; then
  pass "AE8: no new research (merged candidates and family files unchanged)"
else
  fail "AE8: no new research (merged candidates and family files unchanged)"
fi
expect "AE8: only the availability stage re-ran, for the hotels still in play" \
  'sorted(cid for cid, reads in J(RUN/"reads.json")["reads"].items() if any(r["check_in"] == "2026-11-27" for r in reads)) == ["casa-velarta", "el-patio-lunar", "marquesa-vieja", "palacio-nandu", "torre-alta"] and "research" not in [h["stage"] for h in J(RUN/"state.json")["history"][-3:]]'
orch ask "$RUN" >"$OUT/ask3.json"
expect "the hotel struck in the same reply stays off the new shortlist" \
  '"**Hotel Sombra**" not in J("'"$OUT"'/ask3.json")["text"] and "2026-11-27" in J("'"$OUT"'/ask3.json")["text"]'
expect "R15: the strike-out and its reason are in the city cache" \
  '"| Hotel Sombra | dark rooms |" in T(DATA/"cities"/"testgrad.md")'

# R24: the struck hotel returns after a budget raise
printf '%s' '{"change": {"budget_max": 300}}' >"$OUT/reply2.json"
orch checkpoint "$RUN" "$OUT/reply2.json" --reader-fixtures "$FIX/engines" >"$OUT/checkpoint2.json"
orch ask "$RUN" >"$OUT/ask4.json"
expect "R24: the struck hotel is back, read for the new dates" \
  '"**Hotel Sombra**" in J("'"$OUT"'/ask4.json")["text"] and "€165" in J("'"$OUT"'/ask4.json")["text"]'

# The user keeps the rest
printf '{"strike": [{"number": %s, "reason": "no online booking"}]}' "$PALACIO" >"$OUT/reply3.json"
orch checkpoint "$RUN" "$OUT/reply3.json" >"$OUT/checkpoint3.json"
expect "a reply without a change moves to the final check" 'J("'"$OUT"'/checkpoint3.json")["next"] == "final"'

# ---- Stage 7: final check
orch fanout "$RUN" final --batches 1 --contract "$CONTRACT" >"$OUT/final.json"
cp "$FIX/agents/final-1.jsonl" "$RUN/"
# the final check reads after the availability stage, so its records carry a later read time
python3 - "$FIX/agents/evidence-final-1.jsonl" "$RUN/evidence-final-1.jsonl" <<'EOF'
import json, sys
from datetime import datetime, timedelta, timezone
later = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")
lines = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
open(sys.argv[2], "w", encoding="utf-8").write("".join(json.dumps(dict(r, read_at=later), ensure_ascii=False) + "\n" for r in lines))
EOF
orch finalized "$RUN" >"$OUT/finalized.json"
expect "the final check removes a hotel whose engine now says no rooms, with the reason" \
  '[r["name"] for r in J("'"$OUT"'/finalized.json")["removed"]] == ["Hotel Marquesa Vieja"]'
expect "a changed price shows the final-check price" \
  '[(r["name"], r["after"]) for r in J("'"$OUT"'/finalized.json")["price_changed"]] == [("Casa Velarta", 185)]'
expect "a hotel the final check cannot read keeps its ❓" \
  '"El Patio Lunar" in [r["name"] for r in J("'"$OUT"'/finalized.json")["unknown"]]'

# ---- Stage 8: the answer
printf '%s' '{"overview": "City-break pick in Testgrad — quiet old-town houses.", "entries": [{"candidate": "Casa Velarta", "why": "a restored merchant house with twelve rooms", "vibe": "like your 8 anchor"}], "districts": ["Old Quarter: quiet lanes, ten minutes on foot to everything"], "tips": []}' >"$RUN/advice.json"
orch answer "$RUN" >"$OUT/answer.json"; code=$?
ANSWER="$DATA/trips/testgrad-2026-11/hotels-shortlist.md"
expect "the answer is saved in the trip folder and passes the output check" \
  "$code == 0 and J('$OUT/answer.json')['status'] == 'ok' and Path('$ANSWER').is_file()"
python3 "$REPO/bin/check_output.py" "$RUN" "$ANSWER" >"$OUT/check.txt"; code=$?
expect "check_output.py passes the saved answer" "$code == 0 and T('$OUT/check.txt').strip() == 'OK'"
expect "R22: Gmail absent, the answer says the history check was skipped" \
  '"Booking history in Gmail: skipped — history check skipped" in T("'"$ANSWER"'")'
expect "R22: the re-prompted family shows as partial" '"- Reddit: partial" in T("'"$ANSWER"'")'
expect "AE7: the carmen from local press is in the Airbnb block, not in the hotels" \
  '"Carmen del Aljibe Rojo" in T("'"$ANSWER"'").split("### Airbnb")[1] and "Carmen del Aljibe Rojo" not in T("'"$ANSWER"'").split("### Airbnb")[0]'
expect "the answer names the hotel the final check removed, with the reason" \
  '"Skipped: not available for the dates — Hotel Marquesa Vieja — No hay disponibilidad" in T("'"$ANSWER"'")'
expect "the city cache gains this run's sources and picks" \
  '"| curated-press | Revista Ejemplo |" in T(DATA/"cities"/"testgrad.md") and "| Casa Velarta | hotel |" in T(DATA/"cities"/"testgrad.md")'
orch resume --data "$DATA" >"$OUT/resume-end.json"
expect "the finished run is closed" 'J(RUN/"state.json")["stage"] == "done" and J("'"$OUT"'/resume-end.json")["open_runs"] == []'

echo
if [[ "$FAILS" -gt 0 ]]; then
  echo "$FAILS check(s) failed (work folder: $ROOT)"
  exit 1
fi
echo "All checks passed (work folder: $ROOT)"
