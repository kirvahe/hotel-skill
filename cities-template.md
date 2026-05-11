# {City Name}

*City slug: {city-slug}*
*Created: YYYY-MM-DD*
*Updated: YYYY-MM-DD*

---

## Slug rule (reference)

City slug = lowercase, ASCII-fold (strip diacritics, transliterate ñ→n, ß→ss, ü→u), spaces→hyphens.

Examples:
- "Bilbao" → bilbao.md
- "San Sebastián" → san-sebastian.md
- "Palma de Mallorca" → palma-de-mallorca.md
- "Nîmes" → nimes.md
- "New York" → new-york.md

One file per city. Files are created lazily — the first `/hotel` search for a city creates its cache. Do not pre-create empty stubs.

---

## Searched

<!-- One line per search/round: `YYYY-MM-DD R{N}: {query} → {outcome / file}` -->

---

## Recommended

<!-- Active picks. Table: Name | Type | Area | Rating | Notes
e.g.
| Hotel Foo Boutique | boutique | Old Town | 8.7 | LHW, anniversary anchor |
-->

| Name | Type | Area | Rating | Notes |
|---|---|---|---|---|
| | | | | |

---

## Mentioned section (researched, not selected)

<!-- Candidates surfaced during research but not picked. Re-evaluate here before re-researching in later rounds.
Table: Name | Type | Source/Context | Date -->

| Name | Type | Source/Context | Date |
|---|---|---|---|
| | | | |

---

## Excluded (with reason)

<!-- Definitive exclusions. One line per hotel with a causal reason.
Use the user's or companion's words verbatim, preserve original language.
e.g.
- Hotel Generic Chain — too corporate (wife: "no personality")
- Hotel Tired Boutique — обшарпанный, ремонт 2008 года
-->

---

<!-- Archived rounds appear here once Round 2+ happens. Example structure:

## Round 1 — wife rejected: too corporate

Searched: YYYY-MM-DD R1: "Bilbao boutique anniversary"
Picks: Hotel A, Hotel B, Hotel C
Outcome: All three rejected — too business-feel, wife wanted more character

## Criteria changes

R1→R2: dropped business hotels entirely, added "must have a story or unique building" filter

-->
