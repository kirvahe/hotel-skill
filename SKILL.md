---
name: hotel
description: Find hotels matching taste profile. This skill should be used when the user asks for hotel recommendations, wants to rate a hotel stay, or asks to analyze hotel preferences. Triggers on hotel search, "where to stay", accommodation, city names with hotel context.
argument-hint: [city budget/occasion]
version: "1.2"
hooks:
  PreToolUse:
    - matcher: "^(Bash|WebFetch|mcp__(plugin_(.*_)?)?(playwright|claude-in-chrome|computer-use|cmux-cua|Claude_Browser|remote-devices|firecrawl|fetch|exa|claude_ai_Exa)(__.*)?|mcp__.*[Gg][Mm][Aa][Ii][Ll].*)$"
      hooks:
        - type: command
          command: '[ -f "__HOTEL_SKILL_DIR__/bin/guard_hook.py" ] || exit 0; exec python3 "__HOTEL_SKILL_DIR__/bin/guard_hook.py"  # hotel-skill-guard'
          timeout: 10
---

## Before anything else

`{skill}` in every workflow and reference file means this skill's folder: `${CLAUDE_SKILL_DIR}`. User data lives in `{skill}/data/`; scripts live in `{skill}/bin/`.

Run `python3 ${CLAUDE_SKILL_DIR}/bin/preflight.py` first. If it prints `"status": "stop"`, show the user its `message` and stop. Otherwise continue.

## Find a hotel: resume rule

A find-hotel run keeps its state on disk, in a run folder (`RUN`). Before starting one, and whenever the conversation lost track of a run (after a compaction, in a new session), run:

```bash
python3 ${CLAUDE_SKILL_DIR}/bin/orchestrate.py resume --data ${CLAUDE_SKILL_DIR}/data --city "{city}"
```

- It lists an open run for this trip: continue it. Read `workflows/find-hotel.md`, then the `stage_file` it names, and do that stage on its `run_dir`. `waiting_for` lists agents that were still running.
- It lists an open run for the same city with other dates: ask the user whether to continue it or start a new run.
- It lists none: start at stage 1.
- `stale` lists runs whose check-in date has passed: tell the user and close each one with `python3 ${CLAUDE_SKILL_DIR}/bin/orchestrate.py close {run_dir} --reason "dates passed"`. A run that is not closed counts as open, and an open run blocks every Gmail tool that changes mail.

## Find a hotel: stages

Read `workflows/find-hotel.md` (shared run rules) once per session, then one stage file at a time. Each stage ends by naming the next.

| Stage | File | What happens |
|---|---|---|
| 1 intake | `workflows/find-hotel/1-intake.md` | One question: budget per night, the dog, missing dates (R1); the run starts |
| 2 context | `workflows/find-hotel/2-context.md` | Blacklists, past stays, city cache, profile rules; Gmail bookings when available |
| 3 research | `workflows/find-hotel/3-research.md` | Three research agents in parallel: curated lists and press, Reddit, Booking search results |
| 4 filter | `workflows/find-hotel/4-filter.md` | Merge and the profile's hard rules |
| 5 availability | `workflows/find-hotel/5-availability.md` | Resolver agents (official site, closures, judgment calls), then each hotel's own booking engine |
| 6 shortlist | `workflows/find-hotel/6-shortlist.md` | The user strikes out entries or changes dates, budget or the dog answer |
| 7 final | `workflows/find-hotel/7-final.md` | Final-check agents: price, rate and cancellation on the hotel's own site |
| 8 answer | `workflows/find-hotel/8-answer.md` | The answer, its output check and the city cache |

<essential_principles>
## How This Skill Works

### 1. Taste Profile Is the Foundation
Every run reads `${CLAUDE_SKILL_DIR}/data/taste-profile.md`:
- **TOP-3, Strong, Aspirational tier:** the user's reference hotels; they anchor the rating scale and the vibe lines (`references/format-guide.md`, Calibration Anchors)
- **Hotel philosophy and anti-patterns:** what the research agents look for and what the filter removes
- **Hard filters:** the Booking score floor, the "do not recommend" list, limited-choice cities
- **Base:** the home city; a trip from the home city never gets a hotel in it
- **Pet:** the dog's size and weight. Each trip asks whether the dog travels (stage 1); when it does, pet policy is a filter and `references/pet-search.md` applies
- **Budget:** no default; stage 1 asks for it

### 2. Sources — Strict Rules
**Trusted:** Booking (search results only), Condé Nast Traveller, the Michelin Guide including Michelin Keys, Reddit (threads read in full), local press and local guides, Small Luxury Hotels, Design Hotels, Leading Hotels of the World, Mr & Mrs Smith, World's 50 Best Hotels and similar curated lists, the hotel's own website.
**Links only:** Google Maps (never a source of candidates, scores or reviews), Booking (dated links), Airbnb (dated search links for special formats).
**Never:** TripAdvisor, Yelp, Instagram, blogs, mass tourist guides and listicles. Details and tiers: `references/search-sources.md`.

### 3. Booking History Drives Accuracy
A hotel the user stayed in before stays in play and carries its past rating and note. Problematic cities in `taste-profile.md` `## Problematic cities` call for deeper research.

### 4. No Obvious Picks
Assume the user knows the global boutique scene. Chains pass only with a character of their own; the profile's named "do not recommend" chains never pass.

### 5. Never Automate Booking or Airbnb
No tool opens a Booking or Airbnb page, logged in or not, and nothing is booked or paid. Prices and availability come from the hotel's own booking engine, read by `bin/engine_reader.py` in a browser with no visible window.
</essential_principles>

<data_layout>
## Data layout

User-specific data lives in `${CLAUDE_SKILL_DIR}/data/`. It may be a link to a folder kept elsewhere (`install.sh --data-dir`).

**Start every Glob or Grep on user data at `{skill}/data/` or deeper.** A search started at the skill folder does not follow a linked data folder and comes back empty without an error. Reading a named file works either way. The `feedback/` and `trips/` folders are created the first time something is written there.

| File | Purpose |
|---|---|
| `taste-profile.md` | Full taste profile (anchors, formula, anti-patterns, pet, home city, hard filters) |
| `booking-history.md` | Booking history with ratings (legacy tables and Peak/End/Disconfirm/Return blocks) |
| `cities/{city-slug}.md` | City cache: Searched, Sources, Recommended, Struck out, Excluded (with reason). Written by `bin/orchestrate.py`; format in `bin/citycache.py` |
| `feedback/feedback_{city-slug}_hotels.md` | Per-city `## Blacklist` and `## Positive reference` tables. Written by `workflows/rate-stay.md` Phase 2 (Steps 2.5–2.6); read at find-hotel stage 2 |
| `trips/{city-slug}-{YYYY-MM}/` | Per-trip folder: `run/` (the find-hotel run folder), `hotels-shortlist.md` (the answer), `booking-details.md` + `booking-confirmation.{ext}` (rate-stay Phase 1) |
| `engines.json` | Optional: booking engines on a hotel's own subdomain, added to `bin/engines.json` by the reader |
</data_layout>

<intake>
Determine mode from $ARGUMENTS:

**If arguments name a city or ask where to stay** -> find a hotel (resume rule, then the stages above)
**If arguments contain "rate" / "review" / "stayed"** -> workflow rate-stay
**If arguments contain "learn" / "analyze" / "patterns"** -> workflow learn
**If arguments are empty or unclear** -> ask:

What are we doing?
1. Find a hotel (city + dates)
2. Record a stay review
3. Analyze my hotel preferences
4. Something else
</intake>

<routing>
| Response / Keywords | Workflow |
|---|---|
| 1, city name, "find", "where to stay", "hotel", "accommodation" | Resume rule, then `workflows/find-hotel.md` and the stage files |
| 2, "booked / reserved" **+ confirmation artifact** (PDF path, email text, screenshot) and no "rating" language | `workflows/rate-stay.md` → Phase 1 (booking confirmation) |
| 2, "rate / review / stayed / {N}/10 / liked / didn't work" | `workflows/rate-stay.md` → Phase 2 (post-stay review) |
| 2, "booked" without an artifact **and** no rating language | Ask once: "Is this about a booking or about a completed stay?" then route |
| 3, "learn / analyze / patterns / what do I like / update profile" | `workflows/learn.md` |
| 4, other | Clarify, then select workflow |

**After reading the workflow — follow it exactly.** For rate-stay, disambiguate Phase 1 vs Phase 2 via its `<phase_detection>` block before doing any work.
</routing>

<no_fabrication>
## No Fabrication

Never invent hotel specifics. Forbidden without a source:
- Amenities, spa details, room count, restaurant on-site, pool, gym
- Renovation year ("renovated 2024"), opening year, ownership history ("still owned by the X family")
- Owner identity, designer/architect attribution, chef name

Every load-bearing factual claim about a hotel must trace to **one A-tier source** OR **two independent B-tier sources** (per the `reliability_tiers` model in `references/search-sources.md`). In a find-hotel run the sources are the run folder's records: the candidates' mentions, the evidence and the agents' quotes.

Enforcement order when a load-bearing claim cannot be sourced:
1. FIRST: look in the run's records (mentions, evidence, district notes).
2. IF they cannot source the claim: mark it with ❓ and say what needs verification.
3. NEVER silently demote a fact to a guess or drop a candidate without recording the reason.

If asked to recommend without sufficient sourcing → say "not enough verified info" and ask what the user needs to make the decision, rather than fabricating.
</no_fabrication>

<output_language>
## Output Language

Answers, shortlists, questions and the text the model writes into run files (`advice.json`, verdict reasons, module reasons) follow the language of the user's request. `bin/render.py` holds the labels for each language (R20).

Internal files (`cities/{city-slug}.md`, `taste-profile.md`, `booking-history.md`, the run folder's JSON keys, this SKILL.md) stay in English.
</output_language>

<reference_index>
## Reference Materials

All in `references/`:

**Search:** `references/search-sources.md` — trusted, link-only and banned sources, A/B/C reliability tiers. The research briefs in `references/briefs/` apply it.
**Briefs:** `references/briefs/research-contract.md` and one brief per agent (curated-press, reddit, booking-search, resolver, final-check). The agents read them; the orchestrator builds their prompts.
**Format:** `references/format-guide.md` — the answer's fixed layout, what the model writes into it, vibe comparisons, calibration anchors, the `{city-slug}-{YYYY-MM}` folder convention. Read at find-hotel stage 8 and by rate-stay.
**Feedback:** `references/feedback-format.md` — stay review format, rating scale. Read by rate-stay (required reading).
**Occasion:** `references/occasion-taxonomy.md` — six occasions and their ranking modifiers. Read at find-hotel stage 1.
**Pet:** `references/pet-search.md` — room-type trap, welcome vs tolerate, pet-paradox detection, call scripts. Read when the dog travels and for rate-stay Phase 1 pet flags.
</reference_index>

<workflows_index>
## Workflows

| Workflow | Purpose |
|---|---|
| `workflows/find-hotel.md` + `workflows/find-hotel/` | Find a hotel: eight stages over a run folder, one checkpoint, as many options as the city deserves |
| `workflows/rate-stay.md` | Phase 1: record a booking confirmation (safety checklist). Phase 2: record a post-stay review -> update booking-history |
| `workflows/learn.md` | Analyze bookings -> detect patterns -> update profile |
</workflows_index>
