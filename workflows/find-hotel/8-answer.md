# Stage 8: answer

Goal: the answer the user acts on: every kept hotel with its checked price or ❓, dated Booking and Google Maps links, the "beyond budget" group, the Airbnb block, district advice and tips, and what ran (R16–R20, R22, R25). When nothing is left, it says what removed the candidates and what to relax (F2).

```
answer progress:
- [ ] 1. advice.json
- [ ] 2. Render, check, save
- [ ] 3. Show it
- [ ] 4. A reply to "Nothing fits" (F2 only)
```

**1. `RUN/advice.json`**, in the request language. Every claim traces to the run's records (mentions, evidence, district notes, negative reports in `research.json`); what cannot be traced is left out or marked ❓ (SKILL.md, No Fabrication). For F2 write only `districts` and `tips`.

```json
{"overview": "City-break pick in {City} — {one line with the closest anchor}",
 "entries": [{"candidate": "Hotel Name", "why": "why it fits this user and this trip", "vibe": "like {anchor} but …"}],
 "districts": ["{area}: where to stay and why, from the district notes"],
 "tips": ["practical tips for the trip: the festivo warning below, cancellation deadlines, negative reports worth repeating"]}
```

`overview`, `why` and `vibe` follow `references/format-guide.md`. Give an entry to every hotel and Airbnb entry in the answer.

**2. Render, check, save.**

```bash
python3 {skill}/bin/orchestrate.py answer RUN
```

- `ok`: the answer is saved as `answer_file` (the trip folder's `hotels-shortlist.md`), it passed `bin/check_output.py`, the city cache has this run's sources, picks and strike-outs, and the run is closed.
- `fail`: each failure names what is wrong; most often a module without a status (record it with `orchestrate.py module`, stage 2 or 7). Fix the input and run again. Never edit the answer file.

**3. Show it.** Show the saved answer to the user as is, in the request language, then end with a clickable link to `answer_file`.

**4. A reply to "Nothing fits" (F2).** When the answer said nothing fits and the user replies with a new budget, new dates or a new dog answer, write `RUN/reply.json` with only `change` (the keys as in stage 6, step 3):

```json
{"change": {"budget_max": 350}}
```

```bash
python3 {skill}/bin/orchestrate.py checkpoint RUN RUN/reply.json
```

It re-runs the fit filter and the availability check on the saved research, never new research (R24), and reopens the run. When the dates change, it reads the engines again, so run it in the background as in stage 5. Then follow `next`:
- `shortlist`: add verdicts for any new `over_budget` hotels (stage 5, step 4), then `workflows/find-hotel/6-shortlist.md`.
- `answer`: still nothing fits; go back to step 1 of this stage.

Another district is new research: offer a new run (`start --new`).

## Spain festivos and puente risk (Spain trips)

Before writing `tips`, check the trip dates against this table. When the dates are within ±2 days of a row, add the warning below to `tips`.

| Date | Name | Risk |
|---|---|---|
| variable (Mar–Apr) | Semana Santa | peak premium, non-refund rates common, 7+ day cancel windows |
| 1 May | Día del Trabajo | puente risk if Mon/Fri, refund deadlines tighten |
| 15 Aug | Asunción de la Virgen | nationwide, peak prices |
| 12 Oct | Día de la Hispanidad | puente risk if Mon/Fri |
| 1 Nov | Todos los Santos | puente risk |
| 6 Dec | Día de la Constitución | double puente with 8 Dec, peak |
| 8 Dec | Inmaculada Concepción | double puente with 6 Dec, peak |
| 25 Dec | Navidad | peak, limited availability |
| 6 Jan | Reyes | peak, family-travel surge |

Warning, in the request language: **Festivo: {name} ({date}).** Expect a price premium of +20–40%, non-refundable promo rates are common, and cancellation windows often tighten to 7+ days. Book earlier than usual and check the cancellation terms of the room type.

**Staleness guard:** this table was last verified in **2026-01**. Semana Santa moves every year: for trips 6+ months out or any March–April Spain trip, check the year's dates against **BOE.es** before warning.
