## Contents
- File-mode rule (decide before writing the response) — path convention, terminal response in file mode, when not to use it
- Format per hotel — mandatory and optional elements, Overview line
- References for vibe comparisons
- Calibration anchors — tiers and how they are used
- Number of recommendations (5 main + 2 premium)
- Summary table

<overview>
Response format when recommending hotels. Each hotel — structured, with mandatory elements.
</overview>

<file_mode_rule>
## File-Mode Rule — decide before writing the response

**When the full result set has ≥5 hotels OR any URL is longer than ~60 characters → use file mode.**

File mode means: save the complete, structured list to a markdown file in the trip folder, then respond in the terminal with only the **top-3** plus a pointer to the file.

### Path convention

`{skill}/data/trips/{city-slug}-{YYYY-MM}/hotels-shortlist.md`

Where:
- `{city-slug}` — City-slug rule: see `data/cities/README.md` `## Slug rule` (created by `install.sh`).
- `{YYYY-MM}` = year and month of arrival. `15 Jun 2027` → `2027-06`.
- Same slug convention is used for `booking-details.md` (Phase 1 of `rate-stay.md`) so one trip folder holds the shortlist and the booking artifact side by side.

### Why file mode exists

Long markdown tables in the terminal break in three ways: (1) URL wrap mangles clickable links, (2) narrow columns hide pet / collection flags, (3) format drift under context pressure past 100k tokens. A file on disk is immune to all three, stays clickable in Obsidian / VS Code, and persists as a trip artifact.

### Terminal response in file mode

1. `Saved full shortlist to {absolute path}` — clickable file reference
2. **Top 3 hotels** in short form (name, 1-line "why you", Booking link, Maps link)
3. Any red flags (blacklist skips, pet-paradox warning, festivo warning)

### When NOT to use file mode

≤4 hotels AND all URLs short — respond inline with full format per `<response_format>`.
</file_mode_rule>

<response_format>
## Format Per Hotel

```
### N. {Hotel Name} — {X rooms}, {collection if any}

**Why you:** {1-2 sentences — connection to profile and request. Not generic "nice hotel", but specifically why THIS user.}

**What's special:** {Architecture, design, signature feature, neighborhood}

~EUR XXX-YYY/night

- [Booking.com]({link})
- [Google Maps]({link})

**Vibe:** {comparison with profile reference}
```

### Mandatory elements:
1. Hotel name + room count + collection
2. "Why you" — personal reason
3. What's special
4. Price range per night
5. Booking.com link
6. Google Maps link
7. Vibe comparison

### Optional elements:
- Genius discount info (if available)
- Lobby bar / rooftop / spa
- Best room type to book
- Seasonality notes (best time to visit)
- Renovation date (if recent = bonus)

### Overview line

The Overview line **must include the inferred occasion-tag** (from Step 1a of `workflows/find-hotel.md`, defined in `references/occasion-taxonomy.md`) and **should** reference the closest calibration anchor (see `## Calibration Anchors` below).

Format:

> **{Occasion} pick in {City} — {one-line characterization with anchor reference}.**

Where `{Occasion}` is one of the six occasion tags (`city-break`, `ski`, `beach`, `anniversary`, `concert`, `new-country-exploration`). Capitalize the first letter for the line ("City-break pick in Lisbon — …").

Worked examples (structure-only — substitute the user's own anchors from `taste-profile.md`):

- "**Concert pick in {City}** — like {your-anchor-7} but with venue 5-min walk."
- "**Ski pick in {Resort}** — strictly better than {your-anchor-8}-tier execution, ski-in/ski-out."
- "**Anniversary pick in {Region}** — {your-anchor-9.5-10}-tier execution, romantic touches."
- "**City-break pick in {City}** — solid {your-anchor-7} territory, walkable neighborhood."
- "**New-country-exploration pick in {City}** — central location for first-time orientation, {your-anchor-8}-tier."

If multi-occasion (e.g., anniversary + new-country-exploration), surface both tags joined by `+`:

- "**Anniversary + new-country-exploration pick in {City}** — …"

If the user corrects the occasion in the Step 1c echo, regenerate the Overview line with the corrected tag before saving.
</response_format>

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

- In Vibe sections of every hotel recommendation: pick whichever anchor is closest, e.g. "Like {your-anchor-8} but in a Renaissance palazzo".
- In rating gates (`/hotel rate-stay` Phase 2): before assigning 9+, the question "strictly better than {your-anchor-8}?" must be explicit.
- In response Overview line: when comparing to your lifetime best, refer to your anchors by name.

If your `taste-profile.md` is empty/new, the skill will ask you to nominate three anchors during onboarding.
</vibe_comparisons>

<quantity>
## Number of Recommendations

**Standard:** 5 main + 2 premium (stretch budget)
**Minimum:** 3 main (if < 3 worthy — say so honestly)
**Maximum:** 5+2 (more = dilutes quality)

### Premium options:
- 2 hotels that are above stated budget but worth the splurge
- Flag as "PREMIUM" clearly
- Explain why the premium is justified

### If city is the user's home city or well-known:
- Focus on NEW openings or overlooked gems
- Can give fewer if only a few are genuinely new

### If city is "problematic" (per `taste-profile.md` `## Problematic cities`):
- Mention the track record
- Double the search effort
- Consider adjacent cities/areas
</quantity>

<summary_table>
## Summary Table (at end of response)

```markdown
| # | Hotel | Rooms | ~EUR/night | Collection | Key Feature |
|---|---|---|---|---|---|
| 1 | [Name](booking-link) | XX | XXX-YYY | SLH | architecture |
| 2 | [Name](booking-link) | XX | XXX-YYY | — | rooftop bar |
| ... | | | | | |
| P1 | [Name](booking-link) | XX | XXX-YYY | LHW | PREMIUM |
| P2 | [Name](booking-link) | XX | XXX-YYY | Design Hotels | PREMIUM |
```
</summary_table>
