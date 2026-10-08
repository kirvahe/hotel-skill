# Workflow: Find a Hotel

## Contents
- Required reading (load before searching)
- Process state (`continuation_state`)
- Step 0: Pre-search continuation check (city cache)
- Step 1: Parse the request — 1a occasion inference, 1b pet filter parsing, 1c echo inferred state
- Step 2: Check existing data — 2a booking history, 2b problematic cities, 2c taste-profile references, 2d blacklist cross-check, 2e Spain festivo + puente-risk check
- Step 3: Search sources (minimum 6 parallel queries)
- Step 4: Filter results
- Step 5: Operational verification (top-3 finalists)
- Step 6: Format response (5 main + 2 premium)
- Step 7: Summary table
- Step 8: Save output and update city cache
- Anti-patterns
- Success criteria
- Output contract (final check, read last before replying)

<required_reading>
**Read BEFORE searching:**
1. `{skill}/data/taste-profile.md` — full profile
2. `references/search-sources.md` — query patterns and source reliability tiers
3. `references/format-guide.md` — response format and file-mode rule
4. `references/pet-search.md` — pet-friendly protocol (apply when a pet is set in `taste-profile.md`)
5. `{skill}/data/booking-history.md` — past bookings
6. **Blacklist:** run `python3 {skill}/bin/blacklist.py {skill}/data/feedback`. It reads every `feedback_*_hotels.md` and prints the blacklist as JSON for Step 2d. Report any file it lists under `skipped`. Do not glob this folder yourself (see SKILL.md, Data layout).
</required_reading>

<process>
## Process state

`continuation_state` is built incrementally:
- Step 0 populates: `exclusion_list`, `mentioned_candidates`, `prior_criteria` (from city cache; empty on cold-start).
- Step 1 populates: `occasion`, `pet` (from request parsing).
- Steps 4, 6, and 8 consume the full state.

Final shape: `continuation_state = { exclusion_list, mentioned_candidates, prior_criteria, occasion, pet }`. `occasion` and `pet` are used in Step 4 ranking, Step 6 Overview line, and Step 8's continuation-aware write.

## Step 0: Pre-search continuation check

**Run AFTER the city is identified in Step 1's parse, but BEFORE Step 2a (booking-history load). Step 0 reads only the city slug from Step 1's parse; full `continuation_state` is completed in Step 1.** This step deals exclusively with the city cache — it does not touch booking-history, blacklists, or taste-profile (those are loaded later by Steps 2a–2d).

1. **Consume the city slug** resolved in Step 1's parse. City-slug rule: see `{skill}/data/cities/README.md` `## Slug rule` (created by `install.sh`).
2. **Check existence** of `{skill}/data/cities/{city-slug}.md`.
3. **If file does NOT exist:** log internally "cold-start for {city}" and continue to Step 1 / Step 2a normally. The cache file will be created later when results are saved (see Step 8). No echo to user needed for cold start.
4. **If file exists:** load it and parse the canonical sections:
   - `## Searched` — places already researched (informational only; do not block on duplicates)
   - `## Recommended` — hotels already recommended in prior rounds. These are **hard excludes** for the new round unless the user explicitly reinstates one
   - `## Mentioned section (researched, not selected)` — candidates surfaced before but not recommended. Mentioned candidates are re-evaluated against current criteria. Three outcomes:
     1. Fits current criteria → promote to Recommended for this round.
     2. Doesn't fit, and reason is durable (vibe mismatch, wrong city quarter, hard mismatch with taste profile) → move to Excluded with causal reason.
     3. Doesn't fit, only because current criteria narrowed temporarily (e.g., this trip wants ski-in/ski-out, but candidate is great for a city break) → stays in Mentioned with note "still plausible, narrow this round".
     Never silently re-drop them.
   - `## Excluded (with reason)` — hard exclusions; never re-recommend, never re-research
   - `## Round N — {outcome}` — archived prior rounds (read for context on what shifted)
   - `## Criteria changes` — tracks shifts between rounds (read to anchor R(N+1) framing)
5. **Build internal state** for downstream steps:
   - `exclusion_list` = union of `## Recommended` names + `## Excluded (with reason)` names. Pass to Step 4 filter so these are auto-rejected
   - `mentioned_candidates` = parsed list from `## Mentioned section (researched, not selected)`. Cross-check against current criteria during Step 4 — if a Mentioned candidate now fits, promote it instead of researching from scratch
   - `prior_criteria` = the most recent `## Criteria changes` entry, used in Step 6 Overview framing and Step 1c echo correction logic
6. **Echo to user, single line:**

   > Continuation detected for {City}: {N} recommended before, {M} mentioned candidates to re-evaluate, {K} excluded.

   Replace `{N}`, `{M}`, `{K}` with the actual counts. Do not list names in this echo — names appear later via Step 4 filter logs (`Skipped: blacklist — …`) and Step 4 Mentioned-candidate promotions.

**Important boundaries:**
- Step 0 does NOT load booking-history (that is Step 2a's job)
- Step 0 does NOT load blacklist feedback files (that is Step 2d's job)
- Step 0 only reads `cities/{city-slug}.md` and only if it exists
- Use the term **Mentioned section** consistently. Never call it "Mentioned cache"

## Step 1: Parse the Request

From arguments, determine:
- **City** (required)
- **Budget** (required — if not specified, ask)
- **Dates/season** (optional but affects search)
- **Occasion** (inferred — see below)
- **Pet presence** (boolean — see below)
- **Special needs** (spa, pool, rooftop)

If city not specified — ask. If budget not specified — ask (no default).

### Step 1a: Occasion inference

Read `references/occasion-taxonomy.md` for the full table. Infer the occasion from the user's wording — do not ask first. Mapping examples:

- "concert in Lisbon" → **concert**
- "ski in Andermatt" → **ski**
- "anniversary in Tuscany" → **anniversary**
- "first time in Japan" / "never been to Vietnam" → **new-country-exploration**
- "beach week in Sardinia" → **beach**
- Default (no clear signal) → **city-break**

The inferred occasion drives ranking modifiers in Step 4 (composed into the candidate score, not used as a hard filter).

### Step 1b: Pet filter parsing

Detect pet-presence signal. **Default:** read `## Pet` section in `{skill}/data/taste-profile.md`. If a pet is set, `pet=true` is the baseline; most trips include the pet. Set `pet=false` ONLY on explicit signals:

- "without the pet", "trip without [name]", "couple-only", "leaving the pet with [sitter]"
- Destination operationally hostile to the user's pet (e.g., a strictly no-pets resort the user named)

If no pet is set in `taste-profile.md`, `pet=false` is the baseline and the Step 1c echo omits the pet line.

When `pet=true`, the Step 2d / pet-search overhead runs as usual. When `pet=false`, pet filters are skipped for this trip.

### Step 1c: Echo inferred state (non-blocking, declarative)

Emit a single declarative line before proceeding to Step 2:

> Proceeding as **{occasion}** trip with pet=**{true|false}**. Correct me before Step 4 if wrong.

This is **NOT a question**; the workflow proceeds. The user can interject between Step 1c and Step 4 (Search Sources) if the inference is wrong — in that case, update `continuation_state` and restart from Step 2a.

The inferred `occasion` and `pet` flags are added to `continuation_state` from Step 0 and propagate downstream (Step 4 ranking, Step 6 Overview line, Step 8 cache write).

## Step 2: Check Existing Data

### 2a. Booking History
Check `{skill}/data/booking-history.md`.
Find entries for this city. Consider:
- High-rated hotels in this city -> note what worked
- Low-rated hotels -> avoid similar patterns
- Don't recommend already stayed hotels (unless asked)

### 2b. Problematic Cities
Read `{skill}/data/taste-profile.md` `## Problematic cities` section (if populated). Any city where the user's historical hit rate is poor gets flagged here — mention it in the response, dig deeper (minimum 8 queries), and avoid mainstream picks.

Cities with no history -> full exploration mode.

### 2c. Taste Profile References
Check if any TOP-3 or Strong hotels are in this city.
If user has aspirational references in the area — factor in.

### 2d. Blacklist cross-check (required)
From the feedback files loaded in `<required_reading>` step 6, build a working list of hotel names to exclude for this city. Include:
- Exact matches in `feedback_{city}_hotels.md` "Blacklist" tables
- Principle-level rejections that obviously apply (e.g., a "no soulless hotels" style principle from your blacklist, if the user has added principles to `data/feedback/`)

For every search result in later steps:
- If name matches the blacklist → **do not include in the shortlist**
- Print it in the response as `Skipped: blacklist — {hotel} — {reason from feedback file}`
- Never silently drop a blacklisted hotel; the user must see it was considered and rejected

If a blacklist file does not exist for this city → note it and proceed. The blacklist auto-append step in `rate-stay.md` (Phase 2, Step 2.5) will create the file on the first rating ≤4 or negative keyword.

### 2e. Spain festivos + puente-risk check (required for Spain trips)

Before searching, cross-check the trip dates against this table. If the requested dates intersect **±2 days** of any row, **flag it in the response** before listing hotels — the user needs to know about price premiums and non-refundable promo rates *before* clicking book.

| Date | Name | Risk |
|---|---|---|
| variable (Mar–Apr) | Semana Santa | peak premium, non-refund rates common, 7+ day cancel windows |
| 1 May | Día del Trabajo | puente risk if Mon/Fri, refund deadlines tighten |
| 15 Aug | Asunción de la Virgen | nationwide, peak prices |
| 12 Oct | Día de la Hispanidad | puente risk if Mon/Fri |
| 1 Nov | Todos los Santos | puente risk |
| 6 Dec | Día de la Constitución | double puente with 8 Dec, peak |
| 8 Dec | Inmaculada Concepción | double puente with 6 Dec, peak |
| 25 Dec | Navidad | peak, limited availability |
| 6 Jan | Reyes | peak, family-travel surge |

**Flag format when a festivo intersects:**

> ⚠️ **Festivo detected: {name} ({date}).** Expect a price premium of +20–40%, non-refundable promo rates are common, and cancellation windows typically tighten to 7+ days (not the usual 24h). Book earlier than normal, and verify cancellation terms on the room-type page carefully.

**Staleness guard:** This table was last verified in **2026-01**. Semana Santa dates shift every year — for trips 6+ months out or for any Mar–Apr Spain trip, verify the exact Semana Santa dates against **BOE.es** (Boletín Oficial del Estado, canonical source) for the target year before flagging.

**Scope:** Spain only. European events (Fashion Week, F1, Salone del Mobile) are out of scope — add city-specific notes to `feedback_{city}_hotels.md` if a recurring event bites on a given trip.

## Step 3: Search Sources

Run **parallel** WebSearch queries. Minimum 6 queries, adapted to city and occasion. Exception: `site:reddit.com` queries go to `firecrawl_search` and the threads are read per the `reddit-research` skill. WebSearch returns no Reddit threads.

**Search languages — every search, no exceptions:** **A.** the country's language (plus the regional language where one exists: Catalan, Euskara, Galego…), **B.** English, **C.** the language of the subject's origin or community, if any (e.g. a Japanese-run inn in Paris → also Japanese). The language the user typed the request in is never C on its own (Russian-typed request for Seville → Spanish + English, no Russian). Write the A query set first, then B, then C, in every query block, Reddit patterns and subreddit queries included — running them in parallel doesn't change that order. The queries below are English templates: for A and C, rewrite each one the way a native speaker would type it — grammatical, translating the meaning rather than the words, with native compounds (German "Boutiquehotel", not "Hotel Boutique"); keep operators (`site:`, `OR`, `NOT`) and brand/collection names unchanged. Example: Granada → Spanish + English. Country and regional Reddit subs: `references/search-sources.md` → "Multi-language Reddit subs".

### Standard queries:
1. `site:reddit.com r/travel {city} boutique hotel hidden gem`
2. `site:reddit.com {city} best hotel NOT chain NOT tourist`
3. `{city} boutique hotel condé nast traveller 2025 2026`
4. `{city} design hotels OR slh OR leading hotels of the world`
5. `{city} best small hotel mr mrs smith OR tablet hotels`
6. `{city} boutique hotel architectural renovation 2024 2025 2026`

### For special occasions (birthday, anniversary):
7. `{city} romantic boutique hotel special occasion`
8. `{city} hotel with spa pool rooftop`

### For ski/mountain:
7. `{city} ski boutique hotel chalet NOT chain`
8. `{city} boutique hotel mountain view`

### For beach:
7. `{city} boutique beach hotel NOT resort NOT all-inclusive`
8. `{city} design hotel coast mediterranean`

## Step 4: Filter Results

Apply filters from taste-profile:

**Must have (at least 3 of 5):**
- Architecturally beautiful building
- Compact (up to ~60 rooms)
- Fresh / recently renovated
- Hidden gem — not in every tourist guide
- Interesting neighborhood (not necessarily center)

**Auto-reject:**
- Large chain hotels (NH, Occidental, Catalonia, Ibis, Novotel, Hilton, Marriott mainstream)
- Mainstream hyped — in every guide
- Overrated boutiques with no substance
- Apartments, B&Bs, hostels
- Mass beach resort chains
- All-inclusive

**Bonuses:**
- Member of a collection (LHW, SLH, Design Hotels, Autograph Collection)
- Quality bathroom
- Good lobby bar / rooftop
- Spa / pool
- Recently opened (2023-2026)
- Personal approach, professional but not formal

Top-3 finalists proceed to Step 5 operational verification before output.

## Step 5 — Operational verification (top-3 finalists only)

Before finalizing recommendations, verify each top-3 finalist is actually operational on the user's dates. This catches renovation closures, seasonal closures, ownership transitions that left the property in limbo, and silent permanent closures.

For each top-3 finalist:

### 5a — Booking.com availability check

Hit Booking.com with the user's dates. Two possible signals:

- **"No rooms available for these dates"** across the entire calendar window (not just user's exact dates) → strong signal of renovation closure or operational pause. Flag as `⚠ availability check failed`.
- **Available**, even for partial-date matches → operational. Flag as `✓ verified open`.
- **Listing missing entirely** (404 or removed) → flag as `❌ listing not found — possible permanent closure`.

Do NOT scrape Booking.com — use a single search/availability check API call or the listing URL directly. JS-rendered booking widgets on hotel sites are NOT a reliable signal (rescoped per feasibility review).

### 5b — Press scan (last 6 months)

Run a web search for `"{hotel name}" renovation OR closed OR reopening OR "under construction"` filtered to the last 6 months. Two possible signals:

- **Recent renovation announcement** ("opening in 2027 after renovation") → flag as `⚠ press mentions renovation`.
- **Permanent-closure article** ("hotel announces closure") → flag as `❌ press confirms closure`.
- **Nothing relevant** → clean.

### 5c — Apply verification result to output

For each top-3 finalist, append the verification flag to the recommendation card:

- `✓ verified open` — no annotation needed in main card; just a small footnote "Operational status verified for dates {YYYY-MM-DD}–{YYYY-MM-DD}."
- `⚠ availability check failed` — annotate the card with: "**Availability check failed** — Booking shows no rooms in calendar window. Recommend manual phone check before booking."
- `⚠ press mentions renovation` — annotate: "**Press mentions renovation** — verify operational dates with hotel directly before booking."
- `❌ listing not found / press confirms closure` — REMOVE from top-3, promote a backup candidate, log to Excluded with reason.

### 5d — Skip operational verification when

- User explicitly states this is hypothetical / no dates yet → skip the dates-specific Booking check; press scan can still run.

## Step 6: Format Response

Deliver **5 main + 2 premium** options per format from `references/format-guide.md`.

For each hotel:
1. Name + room count + collection (if any)
2. Why it fits (connection to request AND profile)
3. What's special (architecture, design, signature feature)
4. Price range per night
5. Booking.com link
6. Google Maps link
7. Vibe comparison with profile reference

**If a city is flagged in your taste-profile.md `## Problematic cities` section**: mention it and dig deeper.
**If found collection hotels** (SLH, Design Hotels, LHW): flag them.

## Step 7: Summary Table

After individual descriptions, provide a summary table. Each top-3 finalist row must include the operational-verification flag from Step 5 (✓ / ⚠ / ❌) — render it as a dedicated `Status` column so the user can spot verification issues at a glance. Non-top-3 rows leave `Status` blank.

```markdown
| # | Hotel | Rooms | ~Price | Collection | Status | Fit |
|---|---|---|---|---|---|---|
| 1 | Name | XX | €XXX | SLH | ✓ | architecture + design |
| 2 | Name | XX | €XXX | — | ⚠ | renovation press mention |
| 3 | Name | XX | €XXX | LHW | ✓ | hidden-gem vibe |
```

## Step 8: Save Output and Update City Cache

Save the recommendation file and update `cities/{city-slug}.md`. Follow `references/format-guide.md` for file naming and structure.

**Continuation-aware write (only when Step 0 found an existing city cache):**

Reads `continuation_state` from Step 0.

If Step 0 detected a continuation, before writing the fresh `## Recommended` table in `cities/{city-slug}.md`:

1. **Archive the prior round.** Take the existing `## Recommended` block and move it under a new heading `## Round N — {outcome}`. `N` increments from the highest existing Round heading (or starts at `1` if there are no prior round archives yet). `{outcome}` is a short causal phrase from the user's feedback or your inference (e.g., "partner rejected for vibe", "budget shifted up", "dates moved off-season"). Immediately below the heading, add a single line capturing the criteria that round operated under: `Occasion: {x}, Pet: {true|false}`. A future R3 reading the cache needs to know each prior round's criteria.
2. **Update `## Excluded (with reason)`.** Append every rejected candidate from the prior round with a one-line causal reason. Use the user's or companion's verbatim words when available, preserving original language. Never re-drop a `## Mentioned section` candidate silently — if you rejected it again this round, log it here with the new reason.
3. **Document `## Criteria changes`.** Append a line in this format:

   ```
   R{N}→R{N+1}: occasion {old}→{new}, pet {old}→{new}, {prose summary of other criteria shifts}
   ```

   Always include occasion and pet deltas, even when unchanged (write `occasion city-break→city-break` to make the no-shift explicit). Example: if R1 had `occasion=concert, pet=false` and R2 has `occasion=city-break, pet=true`, this becomes: `R1→R2: occasion concert→city-break, pet false→true, narrowed to walkable neighborhoods`. Anchor on the `prior_criteria` captured in Step 0.
4. **Write the fresh `## Recommended` table** with this round's picks.
5. **Update `## Mentioned section (researched, not selected)`.** Add any new candidates surfaced during this round's research that did NOT make the final cut. Preserve Mentioned entries that were re-evaluated and decided to stay in Mentioned per the 3-state rule from Step 0 (outcome 3: doesn't fit only because criteria narrowed temporarily). Remove (or move to `## Excluded`) those that were re-evaluated and decided as durable mismatches.

**Cold-start write (Step 0 found no existing cache):**

Create `cities/{city-slug}.md` with the standard sections — `## Searched`, `## Recommended`, `## Mentioned section (researched, not selected)`, `## Excluded (with reason)`. Round-archive and `## Criteria changes` sections are omitted on cold start; they appear automatically on the first Round 2.

Always end the chat response with a clickable absolute-path link to the saved recommendation file.
</process>

<anti_patterns>
Avoid:
- Recommending top Google results without cross-referencing multiple sources
- Giving chain hotels (even boutique chains like Moxy or citizenM)
- Forgetting Booking.com AND Google Maps links
- Recommending without explaining why it fits THIS user's profile
- Ignoring booking history (if user rated a hotel 4/10 — don't suggest similar)
- Not mentioning room count (compact = key criterion)
- Recommending apartments or B&Bs
</anti_patterns>

<success_criteria>
Search is successful when:
- [ ] Profile read
- [ ] Booking history checked
- [ ] Minimum 6 sources queried
- [ ] 5 main + 2 premium options with links
- [ ] Each hotel: Booking.com + Google Maps link
- [ ] Each hotel: room count + collection flag
- [ ] Vibe comparison with profile references
- [ ] Summary table at the end
- [ ] No chain / tourist trap hotels
</success_criteria>

<output_contract>
## Output Contract — final check before writing the response

Read this block **last**, immediately before producing the response. It is a reminder, not a gate — the structural guarantee is the **file-mode rule** in `references/format-guide.md`. If anything below is missing, fix it before replying.

### Per hotel (whether in the file or inline)
- [ ] Booking.com link **and** Google Maps link — both present, not wrapped mid-URL
- [ ] "Why you" line **and** "Vibe:" comparison line — both filled in (no "nice hotel" placeholder prose)
- [ ] Pet notation consistent across all rows: ✅ / ⚠️ / ❓ / ❌
- [ ] Room count + collection flag (LHW / SLH / Design Hotels / Autograph / Independent / —)

### Per response
- [ ] Blacklisted hotels visible as `Skipped: blacklist — {reason}` — never silently dropped
- [ ] Festivo warning present if dates intersect ±2 days of a Spain festivo (see Step 2e)
- [ ] Pet-paradox warning present if pet-friendly hit rate <20% after 5 candidates (see `references/pet-search.md`)
- [ ] If ≥5 hotels OR any URL > ~60 chars → file-mode triggered, terminal shows top-3 + file pointer

### Honesty clause
This checklist can slip under context pressure. The **file-mode rule** in `references/format-guide.md` is the structural guarantee. If you catch yourself writing a 6-row markdown table directly in the terminal, **stop** and switch to file mode instead.
</output_contract>
