# {City Name}

Updated: YYYY-MM-DD

<!-- City cache: one file per city, cities/{city-slug}.md. find-hotel creates and updates it
     (bin/orchestrate.py through bin/citycache.py); you can also edit it by hand.
     Slug rule: lowercase, ASCII-fold (ñ→n, ß→ss, ü→u), spaces→hyphens. "San Sebastián" → san-sebastian.md -->

## Searched

<!-- One line per find-hotel run: `- YYYY-MM-DD {trip}: {dates} · {guests} · {budget} · {dog} → {outcome}` -->

## Sources

<!-- The city's source map, reused by the research agents on the next trip (R3).
     Family: curated-press, reddit or booking-search. Where: the outlet's URL, or the Booking search query.
| curated-press | Diario Ejemplo | local press | es | https://diario.example/ | 5 | 2026-10-09 |
-->

| Family | Outlet | Kind | Language | Where | Yield | Last used |
|---|---|---|---|---|---|---|

## Recommended

<!-- Hotels kept in a final answer, with the price found for that trip. -->

| Name | Type | Area | Rating | Notes |
|---|---|---|---|---|

## Struck out

<!-- Hotels the user struck out at a checkpoint, with their reason verbatim (R15). They are shown,
     not removed, on later trips: "Struck out before (date): reason". -->

| Name | Reason | Date | Trip |
|---|---|---|---|

## Excluded (with reason)

<!-- Definitive exclusions: every later run removes these, like a blacklist. One line per hotel,
     the user's or companion's words verbatim, original language kept. e.g.
- Hotel Generic Chain — too corporate (partner: "no personality")
-->
