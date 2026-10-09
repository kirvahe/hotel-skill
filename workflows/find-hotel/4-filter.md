# Stage 4: merge and fit filter

Goal: one record per hotel, then the profile's hard rules applied mechanically (R8, R9, R10, R23).

```
filter progress:
- [ ] 1. Wait for the Gmail agent, if one runs
- [ ] 2. Filter
- [ ] 3. Close calls
```

**1.** When the stage 2 Gmail agent is still running, wait for it: its bookings join the past stays here.

**2. Filter.**

```bash
python3 {skill}/bin/orchestrate.py filter RUN
```

It adds Gmail bookings to the past stays, collects the families' source maps, district notes and negative reports into `research.json`, merges the candidates and runs the fit filter. `fit.skip_lines` lists every removal with its reason; the shortlist shows them.

**3. Close calls.** `merge.close_calls` lists name pairs that may be one hotel ("Patio Lunar" and "El Patio Lunar"). Decide each from the records' areas, streets and official sites; for each pair that is one hotel, add it to `RUN/merge-decisions.json` as `{"same": [["Patio Lunar", "El Patio Lunar"]]}` and run the filter again. Different hotels need nothing.

**Dog travels.** `pet` counts the pet policies of the hotels still in play. Apply the pet-paradox rule in `references/pet-search.md` with these counts, and when it fires, say so with the shortlist (stage 6).

Next: `workflows/find-hotel/5-availability.md`.
