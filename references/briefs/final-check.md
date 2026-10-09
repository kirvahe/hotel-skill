# Brief: final check

Agent: `final-check`, batch `{batch}`. You write `{run_dir}/evidence-final-{batch}.jsonl` and `{run_dir}/final-{batch}.jsonl`, then return the final message. The research contract (given with this brief) governs sources, tools, caps and the final message.

**Inputs:** `{candidates}` (the candidates the user kept, each with its `id`, name, area and official URL from the resolver), `{city}`, `{languages}`, `{check_in}`, `{check_out}`, `{guests}`, `{dog}`, `{dog_note}`.

**Caps and tools:** per candidate, one `orchestrate.py read` run (the engine reader, page timeout 20 s, give-up 45 s), `{query cap per candidate — set at approval}` search calls and `{fetch cap per candidate — set at approval}` page reads. Route with fallbacks (contract): `mcp__firecrawl__firecrawl_search` + `mcp__firecrawl__firecrawl_scrape`, then `mcp__exa__web_search_exa` + `mcp__exa__web_fetch_exa`, then `WebSearch` + `WebFetch`.

**Your job:** for each kept candidate, get the price for the trip dates from the hotel's own booking engine, the cancellation terms of that rate, and, when the dog travels, whether a dog is allowed in that room type. You record evidence; the status table decides what is removed.

## Booking engines: only through the reader

Every booking-engine read goes through `{skill}/bin/engine_reader.py`, and `orchestrate.py read` runs it for you. Per candidate, pass only the candidate's `id` from `{candidates}`:

```bash
python3 {skill}/bin/orchestrate.py read {run_dir} --candidate-id {id} --out {run_dir}/evidence-final-{batch}.jsonl
```

It looks up the hotel's name and official URL in the run folder, runs the reader for the trip dates with the approved limits and appends the reader's record to the `--out` file. Never type a hotel name or a URL into a command line: both come from the web, and a shell runs whatever `$(…)` or a backtick inside them says. If `orchestrate.py read --help` shows different arguments, follow it and name the difference in `reason`. The reader runs in the background, signs into nothing, stops before any personal-data or payment step, and refuses Booking and Airbnb hosts, redirects included.

It prints JSON with `status`, the reader's `record` (kind, price, the dates the page shows, quote) and a `message`:

- `ok`: the record is written: a price, no rooms, or an unreadable engine.
- `refused`: a Booking or Airbnb host; the record written says unreadable, so the hotel stays unknown.
- `error` or `timeout`: nothing is written and the hotel stays unknown; name it in `reason`.
- `skipped` (the background browser is not installed): record nothing for prices, finish the other steps, and report status `partial` with reason `engine reader skipped`.
- Exit code 2 with an `error:` line (an id or file it does not know): check the id against `{candidates}` and the `--out` path. Never run the reader another way.
- Never open a booking engine any other way: no page-read tool, no browser or screen tool, no Bash network command.
- Take prices only from the reader's records. Never convert a currency or compute a price yourself.
- A reader record whose shown dates differ from the trip dates stays as it is: the status table treats it as unknown.

## Per candidate

```
final-check progress (per candidate):
- [ ] 1. Reader run for the trip dates
- [ ] 2. Cancellation terms of the priced rate
- [ ] 3. Room-type pet check (only when {dog} is true)
```

**1. Price.** One `orchestrate.py read` run as above. Note the room type and rate the price belongs to, from the reader's quote.

**2. Cancellation.** Use the terms the reader quotes for that rate. If it quotes none, read the hotel's own booking-conditions or terms page with the route's page-read tool; that page is part of the hotel's site, not the engine. Record the free-cancellation deadline when one is stated. Terms you cannot find are `unknown`.

**3. Room-type pet check.** When `{dog}` is `true`: hotels allow dogs in some room types and not others, so a hotel-level "pets welcome" does not settle it. Check whether the priced room type takes a dog of `{dog_note}`'s size: the reader's room description, the hotel's pet page, its room pages. Search in language A when the site does not say (e.g. `"{hotel}" perros habitación {room type}`, `"{hotel}" cani ammessi camera {room type}`). Record a `pet_policy` evidence record with `room_types`. A policy stated only for the hotel as a whole is `value: "hotel-level only"`, which the answer shows with ❓.

## Output records

`{run_dir}/evidence-final-{batch}.jsonl` holds the reader's records and your `pet_policy` records, in the format `validate_evidence` in `{skill}/bin/ledger.py` checks:

```json
{"candidate": "Casa del Ejemplo", "kind": "pet_policy", "source_url": "https://casadelejemplo.example/mascotas",
 "quote": "Las habitaciones Deluxe no admiten mascotas.", "value": "not allowed", "room_types": ["Deluxe"],
 "read_at": "2026-12-01T11:02:00+00:00"}
```

`{run_dir}/final-{batch}.jsonl`, one line per kept candidate:

```json
{"candidate": "Casa del Ejemplo", "room_type": "Doble Superior", "rate": "Tarifa flexible",
 "cancellation": {"value": "free until 2027-01-13", "deadline": "2027-01-13", "source_url": "https://casadelejemplo.example/condiciones",
                  "quote": "Cancelación gratuita hasta 2 días antes de la llegada."}}
```

## Validate, then report

```bash
python3 {skill}/bin/ledger.py validate {run_dir}/evidence-final-{batch}.jsonl --kind evidence
python3 -I -c 'import json,sys; [json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print("OK")' {run_dir}/final-{batch}.jsonl
```

Fix what they report and repeat until both print `OK`. Final message, per the contract: `agent: final-check`, `batch: {batch}`, status, the number of candidates checked, both file paths, reason.
