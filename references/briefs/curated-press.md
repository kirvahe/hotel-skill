# Brief: curated lists and local press

Family: `curated-press`. You write `{run_dir}/candidates-curated-press.jsonl` and `{run_dir}/envelope-curated-press.json`, then return the final message. The research contract (given with this brief) governs records, sources, tools, caps and the final message.

**Inputs:** `{city}`, `{country}`, `{languages}`, `{taste_summary}`, `{source_map_slice}`.

**Caps and tools:** `{query cap — set at approval}` search calls, `{fetch cap — set at approval}` page reads. Route with fallbacks (contract): `mcp__firecrawl__firecrawl_search` + `mcp__firecrawl__firecrawl_scrape`, then `mcp__exa__web_search_exa` + `mcp__exa__web_fetch_exa`, then `WebSearch` + `WebFetch`.

**Your job:** find hotels that trusted editorial sources present as fitting `{taste_summary}`: curated lists and collections (Michelin Guide hotels and Michelin Keys, Condé Nast Traveller, Small Luxury Hotels, Design Hotels, Leading Hotels of the World, Mr & Mrs Smith, World's 50 Best Hotels), local press and local guides, and owner, architect or designer interviews in editorial magazines. Local press finds what international lists miss, so give it most of your queries.

## Workflow

```
curated-press progress:
- [ ] 1. Tool route (contract)
- [ ] 2. Source map: cached outlets, or discover outlets
- [ ] 3. Discovery queries: A, then B, then C
- [ ] 4. Read the strongest pages and extract candidates
- [ ] 5. Booking score search per candidate
- [ ] 6. Kinds and district notes
- [ ] 7. Write, validate, envelope file, final message
```

**2. Source map.**
- **Cold city** (`{source_map_slice}` is `none`): use language-A queries to find the outlets that write about where to stay in `{city}`: the city's and region's newspapers, city magazines, local guides, the national edition of travel magazines. Add the collection pages for the city (`site:guide.michelin.com`, `site:slh.com`, `site:designhotels.com`, `site:lhw.com`, `site:mrandmrssmith.com`). Record every outlet you used in `source_map`.
- **Warm city:** start with `site:` queries on each cached outlet's host. Run no queries whose aim is to find outlets the slice already lists. Run open discovery only to fill a gap the slice leaves (a language set or source kind with no outlet), and list any new outlet with `"new": true`.

**3. Discovery queries.** Language A first, then B, then C (contract). Aim at pages that name hotels and say why: "where to stay" features, new-opening news, hotel reviews, collection property pages, interviews.

**4. Read and extract.** Read the pages that name the most fitting hotels, within the fetch cap. Each candidate needs at least one mention with the sentence that names the hotel and says what makes it fit. Record rooms, pet policy, official URL and closure notices only when the page states them.

**5. Booking score.** One search per candidate, as the contract says.

**6. Kinds and district notes.** This family finds most special formats: a whole historic house, a farmhouse, a house with a walled garden that the press presents as a stay is `special-format`, never `hotel`. Add the press's advice on which areas to stay in to `district_notes`.

## Query pairs, language A

Synthetic examples of the contract's search-language rule:

| Bad | Why | Good |
|---|---|---|
| `{ciudad} hotel boutique mejor condé nast traveller` | English template translated word by word | `dónde dormir en {ciudad} hoteles con encanto` |
| `{ciudad} hotel nuevo apertura renovación arquitectura` | A pile of nouns no Spanish speaker types | `nuevo hotel en {ciudad} en un edificio histórico rehabilitado` |
| `{città} piccoli hotel di lusso` | Translates the collection name "Small Luxury Hotels" | `"Small Luxury Hotels" {città}` |
