# Stage 7: final check

Goal: for every hotel the user kept, the price for the trip dates on its own booking engine, the rate's cancellation terms and, when the dog travels, whether the priced room type takes a dog (R16).

```
final progress:
- [ ] 1. Final-check prompts
- [ ] 2. Spawn the agents, then record their files
```

**1. Prompts.**

```bash
python3 {skill}/bin/orchestrate.py fanout RUN final --batches 3
```

`nothing_to_check`: no kept hotel has its own website (or only Airbnb entries were kept); go to stage 8. `no_url` names kept hotels without a website: they keep their ❓. Exit 3: caps, as in stage 3.

**2. Final-check agents.** One message, one Agent call per printed agent: `model: "opus"`, `prompt` verbatim. Each runs the engine reader once per hotel, through `orchestrate.py read` with the hotel's id; the agents never type a hotel name or URL into a command. When every agent has returned:

```bash
python3 {skill}/bin/orchestrate.py finalized RUN
```

- `removed`: hotels whose own engine now says no rooms, or that a closure now covers (R12). The answer names each with the reason.
- `price_changed`: the answer shows the final-check price.
- `unknown`: the engine could not be read; the hotel stays with its ❓.
- An agent that reported `partial` with reason `engine reader skipped`: `python3 {skill}/bin/orchestrate.py module RUN final_check partial --reason "{the reason, in the request language}"`.

Next: `workflows/find-hotel/8-answer.md`.
