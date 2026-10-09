# Hotel City Caches

One file per city, slug-cased: `bilbao.md`, `san-sebastian.md`, `lisbon.md`, `palma-de-mallorca.md`.

Files are created lazily — the first `/hotel` search for a city creates its cache. Do not pre-create empty stubs.

## Slug rule

City slug = lowercase, ASCII-fold (strip diacritics, transliterate ñ→n, ß→ss, ü→u), spaces→hyphens.

Examples:
- "Bilbao" → bilbao.md
- "San Sebastián" → san-sebastian.md
- "Palma de Mallorca" → palma-de-mallorca.md
- "Nîmes" → nimes.md
- "New York" → new-york.md

## Canonical section order

```markdown
# {City}

Updated: YYYY-MM-DD

## Searched
One line per find-hotel run: `- YYYY-MM-DD {trip}: {dates} · {guests} · {budget} · {dog} → {outcome}`

## Sources
The city's source map (R3), reused by the research agents on the next trip.
Table: Family | Outlet | Kind | Language | Where | Yield | Last used.

## Recommended
Hotels kept in a final answer. Table: Name | Type | Area | Rating | Notes.

## Struck out
Hotels the user struck out at a checkpoint, with the reason verbatim (R15).
Table: Name | Reason | Date | Trip. Later runs show them with that reason; they are not removed.

## Excluded (with reason)
Definitive exclusions: later runs remove them like blacklisted hotels.
One line per hotel: `- {Hotel} — {reason}` (the user's or companion's words verbatim, original language kept).
```

Sections from older versions (`## Mentioned section (researched, not selected)`, `## Round N — {outcome}`, `## Criteria changes`) are kept as they are; find-hotel no longer writes them.

## Reference

`bin/citycache.py` reads and writes these files; `bin/orchestrate.py` calls it after each checkpoint and after the answer. Rows merge by key, so a run written twice changes nothing.
