# Stage 5: resolver, availability and budget

Goal: for each hotel that passed the filter, its own website, closures, pet policy and the judgment calls; then availability and price for the trip dates from its own booking engine (R10, R11, R12, R13, R25).

```
availability progress:
- [ ] 1. Resolver prompts
- [ ] 2. Spawn the resolvers, then record their files
- [ ] 3. Engine reader and status table
- [ ] 4. Verdicts for over-budget hotels
```

**1. Resolver prompts.**

```bash
python3 {skill}/bin/orchestrate.py fanout RUN resolver --batches 3
```

Three batches mirror the three research agents; the caps are per candidate, so the batch count changes speed, not cost. `nothing_to_resolve`: go to step 3. Exit 3: caps, as in stage 3.

**2. Resolvers.** One message, one Agent call per printed agent: `model: "opus"`, `prompt` verbatim. When every resolver has returned:

```bash
python3 {skill}/bin/orchestrate.py resolved RUN
```

It merges their evidence (closures and pet policies from the hotels' own sites) into `evidence.jsonl`, applies their judgment calls, and runs the fit filter again; `skip_lines` now include judgment removals.

**3. Engine reader.** It reads each hotel's own booking engine for the trip dates, one hotel at a time (up to 45 s each), so run it with the Bash tool in the background and wait for it to finish:

```bash
python3 {skill}/bin/orchestrate.py availability RUN
```

- `reader.status` skipped: the background browser is not installed. Tell the user once that availability stays ❓ (README, "Background browser").
- `entries` 0: nothing survived (F2). Go to stage 8.

**4. Over-budget verdicts (R25).** `over_budget` lists hotels priced above the budget. For each, decide whether it clearly beats every in-budget option, from what its sources say, and write `RUN/verdicts.json` with one-line reasons in the request language:

```json
{"clearly_better": [{"candidate": "Hotel Name", "reason": "the only one with …"}],
 "not_better": [{"candidate": "Other Hotel", "reason": "pricier, nothing the in-budget ones lack"}]}
```

Only `clearly_better` hotels appear, in the "beyond budget" group.

Next: `workflows/find-hotel/6-shortlist.md`.
