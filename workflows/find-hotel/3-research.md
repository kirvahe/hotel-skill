# Stage 3: research

Goal: candidates from three research families, written to `RUN` by three agents running in parallel (R6, R7).

```
research progress:
- [ ] 1. Prompts (caps check)
- [ ] 2. Spawn the three agents
- [ ] 3. Collect, re-prompt once if needed
```

**1. Prompts.**

```bash
python3 {skill}/bin/orchestrate.py fanout RUN research
```

- Exit 3, `caps_pending`: stop here. Tell the user that the search and fetch caps and the Firecrawl credit floor await their approval (name the `pending` items) and that the run continues from this stage once the numbers are written into `references/briefs/research-contract.md`. Start no agent, and do not research in the main conversation instead. The run stays open, which blocks Gmail tools that change mail; when the user does not want to wait, close it: `orchestrate.py close RUN --reason "caps await approval"`.
- Exit 2: a stage 2 file is missing or invalid; fix it and run again.

**2. Spawn the agents.** One message, three Agent calls: `model: "opus"`, each `prompt` exactly as printed, description `hotel research: {name}`. Tell the user the research is running (it takes several minutes).

**3. Collect.** As agents return:

```bash
python3 {skill}/bin/orchestrate.py collect RUN --returned {family} [{family} …]
```

- `waiting`: wait for the families it lists.
- `reprompt`: for each family listed, send its agent the `problems` and `message` (continue the same agent when you can, otherwise spawn a new one with the same prompt plus the problems), then run `collect RUN --reprompted {family}`; when that agent returns, `collect RUN --returned {family}`. A family gets one re-prompt; after it, `collect` reports the family as partial or failed and the run goes on.
- `ready`: every family is recorded in `families.json`.

Next: `workflows/find-hotel/4-filter.md`.
