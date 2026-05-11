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
One line per search/round: `YYYY-MM-DD R{N}: {query} → {outcome / file}`

## Recommended
Active picks (table: Name, Type, Area, Rating, Notes).

## Mentioned section (researched, not selected)
Candidates surfaced during research but not picked. Table: Name, Type, Source/Context, Date. Re-evaluate here before re-researching in later rounds.

## Excluded (with reason)
Definitive exclusions. One line per hotel with a causal reason (use the user's or companion's words verbatim, preserve original language).

## Round N — {outcome}
Archived rounds (only present after Round 2+). Heading includes the outcome ("wife rejected — too corporate", "budget shifted", etc.).

## Criteria changes
Multi-round only. Format: `R{N}→R{N+1}: {what shifted and why}`.
```

## Reference

Round detection logic that reads/writes these files: see `<round_detection>` block in `~/.claude/skills/hotel/SKILL.md`.
