---
name: hotel
description: Find hotels matching taste profile. This skill should be used when the user asks for hotel recommendations, wants to rate a hotel stay, or asks to analyze hotel preferences. Triggers on hotel search, "where to stay", accommodation, city names with hotel context.
argument-hint: [city budget/occasion]
version: "1.2"
---

## Before anything else

`{skill}` in every workflow and reference file means this skill's folder: `${CLAUDE_SKILL_DIR}`. User data lives in `{skill}/data/`; scripts live in `{skill}/bin/`.

Run `python3 ${CLAUDE_SKILL_DIR}/bin/preflight.py` first. If it prints `"status": "stop"`, show the user its `message` and stop. Otherwise continue.

<essential_principles>
## How This Skill Works

### 1. Taste Profile Is the Foundation
Before any recommendation, read the profile:
`${CLAUDE_SKILL_DIR}/data/taste-profile.md`

Key profile facts (always in context):
- **TOP-3:** loaded from `taste-profile.md` `## TOP-3` section — the user's three reference hotels that anchor the rating scale
- **Core formula:** architecturally beautiful + compact (up to ~60 rooms) + fresh/renovated + hidden gem + interesting neighborhood + personal service
- **Collections signal quality:** LHW, SLH, Design Hotels, Autograph Collection
- **Aspirational references:** loaded from `taste-profile.md` `## Aspirational tier` — hotels the user has not yet stayed at but considers benchmarks
- **Budget:** no default — always ask
- **Home city:** loaded from `taste-profile.md` `## Base` section — check before recommending hotels in the home city (don't recommend a hotel in the user's own city for a trip from that city; use home district context when assessing "interesting neighborhood")
- **Booking.com loyalty tier:** loaded from `taste-profile.md` if set — configure your Booking.com Genius level (if any) for discount/upgrade hints
- **Pet (default):** loaded from `taste-profile.md` `## Pet` section if set. If a pet is part of the profile, pet-friendly is a **baseline filter**, not a mode — never ask "do you need pet-friendly?", always assume yes unless the user says otherwise.
- **Pet protocol reference:** `references/pet-search.md` — room-type trap, welcome-vs-tolerate, cross-reference tiers, pet-paradox detection, ES + EN call scripts.

### 2. Sources — Strict Rules
**YES:** Reddit (r/travel, city subs), Conde Nast Traveller, Google Maps, Mr & Mrs Smith, Tablet Hotels, Design Hotels, SLH, LHW
**NO:** TripAdvisor, Yelp, mass tourist guides

### 3. Booking History Drives Accuracy
Booking data is stored in booking-history and taste-profile. Before recommending, check:
- What was already booked and how it was rated
- Patterns: what correlates with high ratings (8+)
- Anti-patterns: cities/types that consistently fail
- Problematic cities: surface any city where the user's hit rate is poor (see `taste-profile.md` `## Problematic cities` if populated)

### 4. No Obvious Picks
Assume the user knows the global boutique scene. Recommendations must match that level — not chain hotels, not from Google's first page.

### 5. Vibe References for Comparison
Vibe references come from the user's `taste-profile.md` TOP-3, Strong, and Aspirational sections. See `references/format-guide.md` `## Calibration Anchors` for how the three anchor tiers map to specific hotels and how they're used in Vibe lines and rating gates.
</essential_principles>

<data_layout>
## Data layout

User-specific data (taste profile, booking history, city caches, feedback, trips) lives in `${CLAUDE_SKILL_DIR}/data/`. It may be a link to a folder kept elsewhere (`install.sh --data-dir`).

**Start every Glob or Grep on user data at `{skill}/data/` or deeper.** A search started at the skill folder does not follow a linked data folder and comes back empty without an error. Reading a named file works either way. The `feedback/` and `trips/` folders are created by the workflows the first time they write there.

Files inside `data/`:

| File | Purpose |
|---|---|
| `taste-profile.md` | Full taste profile (anchors, formula, anti-patterns, pet, home city) |
| `booking-history.md` | Booking history with ratings (Peak/End/Disconfirm/Return H3-blocks) |
| `cities/{city-slug}.md` | Per-city continuation cache (Recommended / Mentioned / Excluded / Rounds) |
| `cities/README.md` | City-slug rule and canonical cache section order (seeded by `install.sh`) |
| `feedback/feedback_{city-slug}_hotels.md` | Per-city `## Blacklist` and `## Positive reference` tables. Written by `workflows/rate-stay.md` Phase 2 (Steps 2.5–2.6); read by `workflows/find-hotel.md` (required reading + Step 2d). Uses the compact feedback-file slug defined in rate-stay Step 2.5 |
| `trips/{city-slug}-{YYYY-MM}/` | Per-trip folder: `hotels-shortlist.md` (file mode, `references/format-guide.md`) and `booking-details.md` + `booking-confirmation.{ext}` (rate-stay Phase 1) |
</data_layout>

<intake>
Determine mode from $ARGUMENTS:

**If arguments contain city + budget/occasion** -> go to workflow find-hotel
**If arguments contain "rate" / "review" / "stayed"** -> workflow rate-stay
**If arguments contain "learn" / "analyze" / "patterns"** -> workflow learn
**If arguments are empty or unclear** -> ask:

What are we doing?
1. Find a hotel (city + budget/occasion)
2. Record a stay review
3. Analyze my hotel preferences
4. Something else
</intake>

<routing>
| Response / Keywords | Workflow |
|---|---|
| 1, city name, "find", "where to stay", "hotel", "accommodation" | `workflows/find-hotel.md` |
| 2, "booked / reserved" **+ confirmation artifact** (PDF path, email text, screenshot) and no "rating" language | `workflows/rate-stay.md` → Phase 1 (booking confirmation) |
| 2, "rate / review / stayed / {N}/10 / liked / didn't work" | `workflows/rate-stay.md` → Phase 2 (post-stay review) |
| 2, "booked" without an artifact **and** no rating language | Ask once: "Is this about a booking or about a completed stay?" then route |
| 3, "learn / analyze / patterns / what do I like / update profile" | `workflows/learn.md` |
| 4, other | Clarify, then select workflow |

**After reading the workflow — follow it exactly.** For rate-stay, disambiguate Phase 1 vs Phase 2 via its `<phase_detection>` block before doing any work.
</routing>

<round_detection>
## Round Detection

On every find-hotel invocation, BEFORE loading booking-history, check whether `${CLAUDE_SKILL_DIR}/data/cities/{city-slug}.md` exists.

**If yes — load it.** Parse these sections:
- `## Searched` — prior search history (date + query + outcome)
- `## Recommended` — currently active picks
- `## Mentioned section (researched, not selected)` — candidates surfaced but not picked; re-evaluate against current criteria before re-researching
- `## Excluded (with reason)` — definitive exclusions (do NOT re-recommend)
- `## Round N — {outcome}` — archived rounds
- `## Criteria changes` — what shifted between rounds

Pass exclusion list + criteria changes + Mentioned candidates into the find-hotel flow as constraints.

**If no — cold start.** The cache file is created lazily after recommendations are delivered.

**After delivering recommendations:** write Searched / Recommended / Excluded / Mentioned. Every researched-but-NOT-selected candidate goes into `## Mentioned section (researched, not selected)` with a one-line context (why not picked). Every rejection goes into `## Excluded (with reason)` with a causal reason (use the user's or companion's words verbatim, preserve original language).

**Multi-round:** when a new round begins, archive the prior round under `## Round N — {outcome}` and log shifts under `## Criteria changes` as `R{N}→R{N+1}: {what changed and why}`.

Use exactly the term **"Mentioned section"** throughout — never "Mentioned cache". See `data/cities/README.md` (created by `install.sh`) for the slug rule and worked example.
</round_detection>

<no_fabrication>
## No Fabrication

Never invent hotel specifics. Forbidden without a source:
- Amenities, spa details, room count, restaurant on-site, pool, gym
- Renovation year ("renovated 2024"), opening year, ownership history ("still owned by the X family")
- Owner identity, designer/architect attribution, chef name

Every load-bearing factual claim about a hotel must trace to **one A-tier source** OR **two independent B-tier sources** (per the existing `reliability_tiers` model in `references/search-sources.md`).

Enforcement order when a load-bearing claim cannot be sourced:
1. FIRST: expand search to additional sources (direct hotel site, recent press, additional Reddit subs, owner/architect interviews).
2. IF expansion still cannot source the claim: mark with ❓ in output and flag specifically what needs verification.
3. NEVER silently demote a fact to a guess or drop a candidate without recording the reason.

Do NOT silently demote, do NOT paraphrase into vagueness, do NOT drop the claim while keeping its implication.

If asked to recommend without sufficient sourcing → say "not enough verified info" and ask what the user needs to make the decision, rather than fabricating.
</no_fabrication>

<output_language>
## Output Language

Response language matches the user's last message.

Structural anchors stay English regardless of body language: all bolded section headings (e.g., "Overview", "Why you", "Vibe", "Rooms", "Sources", "Hidden Gem", "What's special", "Peak/End/Disconfirm/Return") and explicit format-template labels. Only narrative body text translates.

Latin anchors are intentional — they preserve grep-ability across cache files and recommendations corpus, including in user-facing files.

Internal artifacts (`cities/{city-slug}.md`, `taste-profile.md`, `booking-history.md`, this SKILL.md) stay in English. User-facing recommendation files in `recommendations/` follow the request-language rule.
</output_language>

<reference_index>
## Reference Materials

All in `references/`. Each workflow's `<required_reading>` block (or the named step) says when to read them:

**Search:** `references/search-sources.md` — query patterns per source, search strategy, A/B/C reliability tiers. Read by find-hotel (required reading).
**Format:** `references/format-guide.md` — response format, vibe comparisons, calibration anchors, file-mode rule, `{city-slug}-{YYYY-MM}` convention. Read by find-hotel and rate-stay (required reading).
**Feedback:** `references/feedback-format.md` — stay review format, rating scale. Read by rate-stay (required reading).
**Occasion:** `references/occasion-taxonomy.md` — six occasions, ranking modifiers, anchors. Read at find-hotel Step 1a.
**Pet:** `references/pet-search.md` — pet-friendly protocol, room-type trap, cross-reference rules, pet-paradox detection, call scripts. Read by find-hotel (required reading; applied when a pet is set) and for rate-stay Phase 1 pet flags.
</reference_index>

<workflows_index>
## Workflows

| Workflow | Purpose |
|---|---|
| `workflows/find-hotel.md` | Find a hotel: city + budget -> search -> filter -> 5+2 options |
| `workflows/rate-stay.md` | Phase 1: record a booking confirmation (safety checklist). Phase 2: record a post-stay review -> update booking-history |
| `workflows/learn.md` | Analyze bookings -> detect patterns -> update profile |
</workflows_index>
