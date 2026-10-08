# Brief: resolver

Agent: `resolver`, batch `{batch}`. You write `{run_dir}/resolved-{batch}.jsonl` and `{run_dir}/evidence-resolver-{batch}.jsonl`, then return the final message. The research contract (given with this brief) governs sources, tools, caps and the final message.

**Inputs:** `{candidates}` (the candidates in this batch that passed the mechanical filter, with any official URL already found), `{city}`, `{country}`, `{languages}`, `{check_in}`, `{check_out}`, `{dog}`, `{dog_note}`, `{judgment_rules}`.

**Caps and tools:** per candidate, `{query cap per candidate — set at approval}` search calls and `{fetch cap per candidate — set at approval}` page reads. Route with fallbacks (contract): `mcp__firecrawl__firecrawl_search` + `mcp__firecrawl__firecrawl_scrape`, then `mcp__exa__web_search_exa` + `mcp__exa__web_fetch_exa`, then `WebSearch` + `WebFetch`.

**Your job:** for each candidate, find the hotel's own website, any dated closure, and (when the dog travels) its stated pet policy, and make the judgment calls the mechanical filter cannot. The availability check runs after you, on your records.

**Booking engines are not yours.** The orchestrator runs `{skill}/bin/engine_reader.py` on your official URLs after you finish; every booking-engine read in the pipeline goes through that reader. Do not open a booking engine with a page-read tool, a browser or screen tool, or Bash. Read only the hotel's ordinary site pages.

**Absence is not evidence.** A hotel is removed only on a page that states a closure overlapping the stay, or on its own engine stating no rooms (the reader's job). When you find no closure notice, write no closure record.

## Per candidate

```
resolver progress (per candidate):
- [ ] 1. Official website
- [ ] 2. Closure notices, phrased in language A
- [ ] 3. Pet policy (only when {dog} is true)
- [ ] 4. Judgment calls
```

**1. Official website.** Search `"{name}" {city}` with the language-A word for an official site ("web oficial", "sito ufficiale"). Take the hotel's own domain. A chain property's page on the chain's own domain counts. A booking site, a collection page or a press page does not, though it may link to the official site. Confirm by reading a page of the site that names the hotel and its address, and quote it. Not found: `official_url` is `null`, and the reader will return unknown.

**2. Closures.** Read the official pages where notices sit: home page banner, news, FAQ, the season or opening-dates page. Then search the closure phrases below in language A. Record a `closure` evidence record only when a page states a closure, with its dates as written. Record dated reopenings and permanent closures the same way. An opening season ("open March to October") states a closure outside it: record the closed period around the stay that it implies, from the day after the season ends to the day before the next one starts, with the season sentence as the quote.

**3. Pet policy.** When `{dog}` is `true`, read the hotel's pet page or room policy and record a `pet_policy` evidence record: `value` (`allowed`, `not allowed`, `restricted`), the conditions in the quote (weight or size limits, fee, room types), and `room_types` when the page names them. Compare nothing with `{dog_note}`: the filter does that. When `{dog}` is `false`, skip this step.

**4. Judgment calls.** For each candidate a source ties to a chain, decide "chain with character": does this property have a character of its own (a historic building, its own design, its own story) beyond the brand? For each item in `{judgment_rules}`, decide whether it applies. Each verdict is `pass` or `fail` with a one-line reason and a quote. Fail only on a quoted reason; without evidence, pass and say so.

## Closure phrasing, language A

Notices are written in the country's language; English queries miss them. Synthetic examples:

| Meaning | Spanish | Italian |
|---|---|---|
| Closed for the season | "cerrado por temporada", "cierre de temporada" | "chiusura stagionale" |
| Temporary closure, works | "cierre temporal", "cerrado por obras", "cerrado por reformas" | "chiusura temporanea", "chiuso per lavori" |
| Reopening | "reabrimos el", "reapertura" | "riapriamo il", "riapertura" |
| Opening season | "abierto de marzo a octubre", "temporada de apertura" | "aperto da aprile a ottobre", "periodo di apertura" |
| Annual holiday | "cerrado por vacaciones" | "chiuso per ferie" |
| Permanent | "cierra definitivamente" | "chiude definitivamente" |

| Bad | Why | Good |
|---|---|---|
| `"{hotel}" closed for season` | English, for a notice written in Spanish | `"{hotel}" "cerrado por temporada" OR "cierre temporal" OR reapertura` |
| `"{hotel}" chiuso stagione` | Word for word; notices say "chiusura stagionale" | `"{hotel}" "chiusura stagionale" OR riapertura` |

## Output records

`{run_dir}/evidence-resolver-{batch}.jsonl`, one evidence record per line, in the format `validate_evidence` in `{skill}/bin/ledger.py` checks:

```json
{"candidate": "Casa del Ejemplo", "kind": "closure", "source_url": "https://casadelejemplo.example/noticias",
 "quote": "El hotel permanecerá cerrado del 7 de enero al 14 de febrero de 2027.",
 "closed_from": "2027-01-07", "closed_until": "2027-02-14", "read_at": "2026-12-01T10:12:00+00:00"}
{"candidate": "Casa del Ejemplo", "kind": "pet_policy", "source_url": "https://casadelejemplo.example/mascotas",
 "quote": "Admitimos perros de hasta 8 kg en las habitaciones Superior, con suplemento.",
 "value": "restricted", "room_types": ["Superior"], "read_at": "2026-12-01T10:14:00+00:00"}
```

`closed_from` is the first closed night and `closed_until` the last closed day, as the notice states. Leave out `closed_until` for an open-ended or permanent closure, `closed_from` for a closure already running, and any date the notice leaves ambiguous; a closure with no usable dates removes nothing. `read_at` is when you read the page.

`{run_dir}/resolved-{batch}.jsonl`, one line per candidate in the batch:

```json
{"candidate": "Casa del Ejemplo",
 "official_url": {"value": "https://casadelejemplo.example/", "source_url": "https://casadelejemplo.example/contacto", "quote": "Casa del Ejemplo · Calle Mayor 1 · Testgrad"},
 "judgments": [{"rule": "chain with character", "verdict": "pass", "reason": "a restored 18th-century house with its own design",
                "source_url": "https://diario.example/hoteles", "quote": "un palacete del siglo XVIII rehabilitado"}]}
```

## Validate, then report

```bash
python3 {skill}/bin/ledger.py validate {run_dir}/evidence-resolver-{batch}.jsonl --kind evidence
python3 -I -c 'import json,sys; [json.loads(l) for l in open(sys.argv[1]) if l.strip()]; print("OK")' {run_dir}/resolved-{batch}.jsonl
```

Fix what they report and repeat until both print `OK`. Final message, per the contract: `agent: resolver`, `batch: {batch}`, status, the number of candidates resolved, both file paths, reason.
