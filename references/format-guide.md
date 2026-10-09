## Contents
- Trip folder and the saved answer — path convention
- The answer's layout — what the renderer writes, what the model writes
- Overview line
- "Why you" and vibe lines
- References for vibe comparisons
- Calibration anchors — tiers and how they are used

<overview>
How a find-hotel answer is laid out, and what the model contributes to it. The layout is fixed: `bin/render.py` writes the shortlist and the answer from the run folder, the same way every run, with labels in the request language. The model writes only the text that needs judgment, into `advice.json` and `verdicts.json`.
</overview>

<trip_folder>
## Trip folder and the saved answer

`{skill}/data/trips/{city-slug}-{YYYY-MM}/`

- `{city-slug}`: see `data/cities/README.md` `## Slug rule` (created by `install.sh`); `bin/ledger.py slug "City"` prints it.
- `{YYYY-MM}`: year and month of arrival. `15 Jun 2027` → `2027-06`.
- The folder holds the find-hotel run (`run/`), the saved answer (`hotels-shortlist.md`) and, after booking, `booking-details.md` and the confirmation (rate-stay Phase 1).

The answer is always saved to the file, then shown in the chat as is, ending with a clickable link to the file.
</trip_folder>

<answer_layout>
## The answer's layout

`render.py` writes, in this order:

1. Title (city and dates) and the trip line (guests, budget, dog).
2. The overview line (from `advice.json`).
3. **Hotels**: every kept hotel, numbered as on the shortlist. Each entry: name, area, the checked price per night or ❓; flags (Booking only, score unverified ❓, pet policy, below your floor); "why you" and vibe lines (from `advice.json`); the rate and cancellation the final check found; negative reports; earlier strike-outs; past stays with their rating; a dated Booking link and a Google Maps link.
4. **Beyond budget**: only hotels with a "clearly better" verdict (R25), each with its reason.
5. **Airbnb — special formats**: whole houses, carmens, fincas the sources present as stays, with a dated Airbnb search link and "dates not verified" (R19).
6. **Where to stay** and **Tips** (from `advice.json`).
7. **Skipped**: every removal with its reason (blacklist, floor, chain, judgment, dogs, closed or full on the dates).
8. **Checks**: each research family and module as ran, partial, skipped or failed (R22).

When no hotel is left, the Hotels section becomes "Nothing fits", with what removed the candidates and what to change: budget, district or dates (F2, R17).

There is no fixed number of options: the answer holds every hotel the user kept (R17).

What the model writes, in the request language:

| File | Field | Content |
|---|---|---|
| `verdicts.json` | `clearly_better`, `not_better` | One verdict per over-budget hotel, each with a one-line reason |
| `advice.json` | `overview` | The overview line |
| `advice.json` | `entries` | `{"candidate", "why", "vibe"}` for each hotel and Airbnb entry in the answer |
| `advice.json` | `districts`, `tips` | District advice from the research's district notes; practical tips for the trip |
</answer_layout>

<overview_line>
## Overview line

The overview line names the inferred occasion (`references/occasion-taxonomy.md`) and, when one fits, the closest calibration anchor:

> {Occasion} pick in {City} — {one-line characterization with anchor reference}.

Worked examples (structure only — use the user's own anchors from `taste-profile.md`):

- "Concert pick in {City} — like {your-anchor-7} but with the venue a 5-minute walk away."
- "Anniversary pick in {Region} — {your-anchor-9.5-10}-tier execution, romantic touches."
- "City-break pick in {City} — solid {your-anchor-7} territory, walkable neighbourhood."

Two occasions join with `+`: "Anniversary + new-country-exploration pick in {City} — …".
</overview_line>

<why_and_vibe>
## "Why you" and vibe lines

- **Why you:** one or two sentences on why this hotel fits this user and this trip: the profile's formula (building, size, freshness, neighbourhood, service) and the occasion. Not "nice hotel". Every fact in it comes from the run's sources; room count and collection (SLH, Design Hotels, LHW, Autograph, Michelin Key) when a source states them.
- **Vibe:** a comparison with one of the user's reference hotels (below).
</why_and_vibe>

<vibe_comparisons>
## References for Vibe Comparisons

Vibe references come from the user's `taste-profile.md` TOP-3, Strong, and Aspirational sections. Each entry there should describe the hotel's character in 1 line — e.g., "Art Deco palace, 48 rooms, historic grandeur" — so the skill has a stable vocabulary for vibe lines.

Typical character categories to look for in the user's profile:

- **Grand boutique with history** — palace conversions, Art Deco / Belle Époque
- **Estate / countryside** — medieval estates, vineyard properties, vast grounds
- **Design hotel in historic building** — design-forward inside heritage shell
- **Affordable cool** — budget boutique with personality and neighborhood
- **Location-driven / renovation gem** — clifftop, waterfront, recent renovation
- **Traditional luxury / grand hotels** — old money, formal service
- **Ski boutique** — compact chalet, ski-in/ski-out
- **Collection-curated** — SLH / LHW / Design Hotels / Autograph member, historic conversion
- **Mansion / heritage conversion** — Ottoman mansion, palazzo, etc.

### Comparison format:
- "Vibe: like {your-anchor-9.5-10} but in a Renaissance palazzo"
- "Vibe: {your-anchor-8} energy — design in a historic shell, great value"
- "Vibe: {your-anchor-7} meets {aspirational-reference} — clifftop estate with renovation"

DO NOT write:
- "Vibe: nice hotel" (meaningless)
- "Vibe: boutique hotel" (too generic)

## Calibration Anchors

Three reference hotels anchor the rating scale. These come from YOUR `taste-profile.md` `## TOP-3` section. Before assigning Booking-equivalent 9+, mentally compare candidate against your 8-anchor: "strictly better than {your-anchor-8}?". If no — rating ≤ 8.

| Tier | Source | What it represents |
|---|---|---|
| 9.5–10 | Your top-rated hotel from `taste-profile.md` | The top of your lifetime experience — must be near-perfect across architecture, service, room, location |
| 8 | Your second-strongest reference | Strong character + execution; everything works, real personality |
| 7 | Your "solid stay" reference | Good with personality but with one or two notable gaps |

### How anchors are used

- In vibe lines: pick whichever anchor is closest, e.g. "Like {your-anchor-8} but in a Renaissance palazzo".
- In rating gates (`/hotel rate-stay` Phase 2): before assigning 9+, the question "strictly better than {your-anchor-8}?" must be explicit.
- In the overview line: when comparing to your lifetime best, refer to your anchors by name.

If your `taste-profile.md` is empty/new, the skill will ask you to nominate three anchors during onboarding.
</vibe_comparisons>
