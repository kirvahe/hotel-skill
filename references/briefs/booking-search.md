# Brief: Booking listings in search results

Family: `booking-search`. You write `{run_dir}/candidates-booking-search.jsonl` and `{run_dir}/envelope-booking-search.json`, then return the final message. The research contract (given with this brief) governs records, sources, tools, caps and the final message.

**Inputs:** `{city}`, `{country}`, `{languages}`, `{taste_summary}`, `{source_map_slice}`.

**Caps and tools:** `{query cap — set at approval}` search calls, no page reads. Route with fallbacks (contract): `mcp__firecrawl__firecrawl_search`, then `mcp__exa__web_search_exa`, then `WebSearch`.

**Your job:** find hotels through their Booking listings as search results show them, with the guest score and review count quoted from the result text. These are the small, well-rated places that press and Reddit miss. Other families confirm candidates; the merge script flags a Booking-only find as "Booking only, unconfirmed".

**Search calls only.** This family reads no pages at all: not Booking, not hotel sites, not anything else. Every fact comes from a search result's own text (title, description or snippet).

## Workflow

```
booking-search progress:
- [ ] 1. Tool route (contract)
- [ ] 2. Listing queries: cached ones first on a warm city
- [ ] 3. Discovery queries: A, then B, then C
- [ ] 4. Record each listing from its result text
- [ ] 5. Score lookups for listings without a score
- [ ] 6. Write, validate, envelope file, final message
```

**2. Cached queries.** On a warm city, `{source_map_slice}` lists the queries that returned fitting listings last time (`kind: "booking-query"`). Run them first and do not search again for phrasings they already cover. On a cold city, skip this step.

**3. Discovery queries.** `site:booking.com` with `{city}` and terms from `{taste_summary}`: character, size, a historic building, a district. Booking keeps listing pages in many languages, so language-A queries can surface listings that English queries miss. On the Exa route, describe the page instead (`Booking.com listings of small historic hotels in {city}`) and keep only results on booking.com.

**4. Record each listing.**
- Keep a result only when it is one property's listing in `{city}`, not a list or search page.
- `name` as the listing shows it. `area` only when the result text names it.
- `kind` from the listing type in the text: an apartment, villa, guesthouse or country house is not `hotel` (contract).
- Mention: `family: "booking-search"`, `source_name: "Booking (search result)"`, `url` = the result URL as listed (never opened), `quote` = the result text you relied on.
- `booking_score` per the contract: from this result's text, with `query` set to the query that returned it.
- Do not record rooms, pet policy, official URL or prices: result text is too thin for them.

**5. Score lookups.** For a fitting listing whose result text shows no score, one `site:booking.com "{name}" {city}` search (contract). Different scores for one property: one record per score.

**Source map.** List the queries that returned fitting listings in `source_map` as `{"outlet": "Booking", "kind": "booking-query", "query": "…", "language": "…", "yield": n}`; on a warm city only new ones, with `"new": true`.

## Query pairs, language A

Synthetic examples:

| Bad | Why | Good |
|---|---|---|
| `booking {ciudad} mejores hoteles puntuación alta` | No `site:` operator: returns rankings, listicles and aggregators | `site:booking.com hotel con encanto casco antiguo {ciudad}` |
| `site:booking.com "{nombre del hotel}"` | No city: a namesake in another town can answer | `site:booking.com "{nombre del hotel}" {ciudad}` |
| `site:booking.com {città} hotel migliori recensioni 9+` | Scores cannot be searched for; "9+" only adds noise | `site:booking.com {città} hotel di charme centro storico` |
