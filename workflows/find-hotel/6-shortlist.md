# Stage 6: shortlist and strike-outs

Goal: the one checkpoint. The user sees every hotel still in play and strikes out what they don't want, or changes the dates, the budget or the dog answer (R14, R15, R24).

```
shortlist progress:
- [ ] 1. Show the shortlist
- [ ] 2. Get the reply
- [ ] 3. Apply it
```

**1. Show the shortlist.**

```bash
python3 {skill}/bin/orchestrate.py ask RUN
```

Show `text` to the user exactly as printed, plus the pet-paradox warning from stage 4 when it fired. The entry numbers stay the same for the whole run.

**2. Get the reply.**
- `mode` question: call AskUserQuestion with `questions` exactly as printed (multi-select; what the user does not pick is kept; Other carries reasons and changes).
- `mode` plain: end the turn and wait for the user's reply.

**3. Apply it.** Write the reply to `RUN/reply.json`; both parts are optional, reasons are the user's words verbatim:

```json
{"strike": [{"number": 3, "reason": "too far out"}, {"number": 5}],
 "change": {"check_in": "YYYY-MM-DD", "check_out": "YYYY-MM-DD", "budget_max": 300, "dog": true}}
```

```bash
python3 {skill}/bin/orchestrate.py checkpoint RUN RUN/reply.json
```

It records the strike-outs in the city cache first (R15). A change re-runs the fit filter and the availability check on the saved research, never new research (R24); hotels struck at an earlier checkpoint go through the checks again and can return. Hotels struck in this reply stay struck. When the dates change, it reads the engines again, so run it in the background as in stage 5.

- `next` shortlist: add verdicts for any new `over_budget` hotels (stage 5, step 4), then back to step 1.
- `next` final: `workflows/find-hotel/7-final.md`.
- `next` answer: nothing is left (F2): `workflows/find-hotel/8-answer.md`.

A request for more or other hotels is new research: offer a new run (`start --new`); never add hotels by hand.
