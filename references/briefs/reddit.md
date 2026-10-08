# Brief: Reddit

Family: `reddit`. You write `{run_dir}/candidates-reddit.jsonl` and `{run_dir}/envelope-reddit.json`, then return the final message. The research contract (given with this brief) governs records, sources, tools, caps and the final message.

**Inputs:** `{city}`, `{country}`, `{languages}`, `{taste_summary}`, `{source_map_slice}`.

**Caps and tools:** `{query cap — set at approval}` search calls, `{scan cap — set at approval}` sub scans of `{scan pages — set at approval}` pages each, `{thread cap — set at approval}` threads read in full. Thread discovery: `mcp__firecrawl__firecrawl_search` (no fallback finds Reddit threads) and sub scans. Thread reading: `{skill}/bin/reddit_fetch.py` only. Booking-score searches follow the contract's route: `mcp__firecrawl__firecrawl_search`, then `mcp__exa__web_search_exa`, then `WebSearch`.

**Your job:** find hotels that people recommend from their own stays, read in full threads. Search snippets are not Reddit data: a mention counts only with the permalink of the post or comment you read.

## Reddit adapter

All Reddit reading goes through `{skill}/bin/reddit_fetch.py`:

```bash
# posts in a city sub that match hotel terms (regex), or in a national or travel sub that name the city
python3 {skill}/bin/reddit_fetch.py scan {sub} --query "{terms regex}" --max-pages {scan pages — set at approval} --backend arctic --out {run_dir}/reddit-scan-{sub}.json
python3 {skill}/bin/reddit_fetch.py scan {sub} --city "{city}" --city "{local spelling}" --max-pages {scan pages — set at approval} --backend arctic --out {run_dir}/reddit-scan-{sub}.json
# full comment trees: thread IDs or URLs
python3 {skill}/bin/reddit_fetch.py tree {id} {id} --backend arctic --out {run_dir}/reddit-threads-{n}.json   # a new {n} per call
```

`--since YYYY-MM-DD` skips posts too old to describe a hotel as it is now. Each output JSON has `status` (`complete`, `partial`, `failed`) and a `reason`. If a command reports `failed` (backend unreachable or erroring), stop: status `failed`, the adapter's reason, no candidates. Never fall back to search snippets, reddit.com pages, or any page-read or browser tool on reddit.com.

## Workflow

```
reddit progress:
- [ ] 1. Tool route (contract): decides thread discovery
- [ ] 2. Pick subreddits
- [ ] 3. Discover threads: web search and sub scans
- [ ] 4. Read threads in full
- [ ] 5. Extract candidates from what you read
- [ ] 6. Booking score search per candidate
- [ ] 7. Kinds and district notes
- [ ] 8. Write, validate, envelope file, final message
```

**2. Pick subreddits.** Language A first: national, regional and city subs in the country's languages. Then English city and travel subs, then C-language community subs when C exists. On a warm city, `{source_map_slice}` lists the subs: start with them and do not search for subs again. List every sub you used in `source_map` (`kind: "subreddit"`; on a warm city only new ones).

**3. Discover threads.**
- **Web search, Firecrawl route only:** `mcp__firecrawl__firecrawl_search` with `site:reddit.com` queries, A, then B, then C. Take post IDs from `/comments/{id}/` in the result URLs. A `?tl=` URL is Reddit's machine translation of the same thread: dedupe by ID.
- **Sub scans:** `scan` on each picked sub, with filter terms in that sub's language. Skim the matched titles yourself.
- **No Firecrawl route:** Exa and WebSearch return no Reddit threads, so discover by sub scans only. Report status `partial`, reason `no Firecrawl: Reddit discovery by sub scans only`.

**4. Read threads.** `tree` on the threads whose titles fit the trip, within the thread cap. A thread with no archived comments does not count as read. For a very long thread, read the top-scored comments and every comment that names a place to stay, and say so in `notes`.

**5. Extract candidates.**
- Each mention: take `family`, `source_name`, `url` (the permalink) and `date` as the adapter output gives them for that comment or post, and add `language` and `quote`: a short excerpt of its `body`. The adapter already removes usernames; keep it that way.
- Prefer trip reports ("we stayed at…") over hearsay. A hotel named only in a question is not a mention.
- The same list pasted into several threads is one voice: record it once.
- A negative report ("avoid X, the street noise…") is not a mention. Add it to the envelope file's `negative_reports` as `{"candidate", "url", "quote"}`.

**6. Booking score.** As the contract says; these searches go to booking.com, not Reddit, so every route can run them.

**7. Kinds and district notes.** Tag special formats (contract). Locals' advice on where to stay goes to `district_notes`, with the permalink as `source_url`.

## Query pairs, language A

Synthetic examples, for web-search queries and scan filters:

| Bad | Why | Good |
|---|---|---|
| `site:reddit.com {ciudad} hotel boutique joya escondida` | "Joya escondida" is a calque; Spanish posters ask where to stay | `site:reddit.com dónde alojarse en {ciudad} hotel recomendado` |
| `site:reddit.com {città} hotel consigliato NON catena` | Operator translated: `NON` is not an operator | `site:reddit.com dove dormire a {città} hotel NOT ostello` |

Scan filter on a Spanish city sub. Bad: `--query "hotel"` (an English-only term misses most local posts). Good:

```bash
--query "hotel|alojamiento|alojarse|dormir|hospedaje|quedarse"
```
