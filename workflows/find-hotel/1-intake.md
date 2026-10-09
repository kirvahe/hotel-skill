# Stage 1: intake

Goal: the trip and the R1 answers, then the run folder. The resume rule (SKILL.md) already ran and found no open run for this trip.

```
intake progress:
- [ ] 0. Caps approved?
- [ ] 1. Read the request
- [ ] 2. Ask the one question
- [ ] 3. Start the run
```

**0. Caps.** `python3 {skill}/bin/orchestrate.py caps`. Exit 3 (`caps_pending`): the research agents cannot run until the user approves the search and fetch caps and the Firecrawl credit floor. Tell the user so, naming the `pending` items, and stop: ask nothing and start no run.

**1. Read the request.** Take from the request and the profile, without asking:
- City and country. An area or region: ask which town only when the request names none.
- Dates (YYYY-MM-DD), when the request gives them.
- Guests: from the request; otherwise the profile's travel companions (a couple is 2).
- Occasion: inferred with `references/occasion-taxonomy.md` (city-break by default). Never asked.
- The request language, as a code (`ru`, `en`, `es`…): labels and the answer use it.
- The language set for the agents (`workflows/find-hotel.md`, Search languages), written as one line: `A = Spanish, B = English, C = none`.

**2. Ask the one question (R1).** One message, in the request language, asking only what is missing among:
- the budget per night in EUR (always: there is no default);
- whether the dog travels on this trip (only when the profile's `## Pet` names one; otherwise the dog stays home without asking);
- the dates (only when the request has none).

When the dates are known, ask with AskUserQuestion: one question for the budget (two to four options taken from the profile's budget line, the user types any other amount under Other) and one for the dog (yes / no). When the dates are missing, ask all of it as one plain message and wait for the reply. Never ask about anything else here.

**3. Start the run.**

```bash
python3 {skill}/bin/orchestrate.py start --data {skill}/data --city "{city}" --country "{country}" \
  --languages "{A = …, B = English, C = …}" --lang {code} --check-in {YYYY-MM-DD} --check-out {YYYY-MM-DD} \
  --guests {n} --budget-max {eur} --dog yes|no --occasion {tag}
```

- It prints `run_dir`: that is `RUN` from here on.
- Exit 3 (`open_run`): an unfinished run for the same city and month is in the way. Show its `message` and ask: continue that run (read its stage file) or start again (add `--new`; the old run folder is archived, never deleted).

Next: `workflows/find-hotel/2-context.md`.
