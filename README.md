# /hotel — Claude Code Skill

A personalized hotel recommendation engine that lives inside Claude Code. Learns your taste, finds character-driven hotels, and never recommends another soulless chain.

For people who travel deliberately and are tired of Booking.com's first page.

## Why this exists

Generic hotel search optimizes for the average traveler. The average traveler wants predictable rooms, a familiar logo, and a high aggregate score. You don't. You want architecture, compactness, a neighborhood with a story, fresh renovation, personal service — the things that turn a stay into a memory rather than a transaction.

This skill solves that by maintaining a persistent taste profile — your reference hotels, your aspirational tier, your anti-patterns, the collections you trust (LHW, SLH, Design Hotels, Autograph), and the operational details that matter (Genius Level, pet travelling with you (configurable in taste-profile.md), festivo calendars). It searches Reddit in up to three languages, cross-references owner and architect interviews from editorial outlets (Monocle, Apartamento, Wallpaper*, Cereal, Openhouse), and verifies each top finalist is actually open on your dates before showing it to you.

## What it does

- **Find** — searches A-tier editorial sources, Reddit in multiple languages, and member-collection directories; filters every result through your profile
- **Rate** — captures stays in two phases (booking confirmation with safety checklist, then post-stay review with Peak/End/Disconfirm/Return)
- **Learn** — analyses booking history to find what actually drives your 9+ ratings and proposes profile updates
- **Persist** — every city you search builds a local cache (Searched / Recommended / Mentioned / Excluded) so the second trip is never a cold start
- **Verify** — top-3 finalists pass an operational check (Booking.com availability + 6-month press scan) before reaching you
- **Calibrate** — six-occasion taxonomy (city-break / ski / beach / anniversary / concert / new-country-exploration) composes occasion-specific ranking modifiers into the candidate score

## Who is this for

Anyone who uses Claude Code and cares where they sleep. The skill is city-agnostic and works best if you:

- Book boutique, design, or independent hotels rather than chains
- Have opinions about architecture, neighborhood, room count, and service style
- Travel often enough that a learning system pays off
- Are willing to spend ~15 minutes filling a taste profile before first use

## Quick Start

### 1. Install

```bash
git clone https://github.com/kirvahe/hotel-skill.git && cd hotel-skill && ./install.sh
```

Or manually:

```bash
mkdir -p ~/.claude/skills/hotel/{workflows,references}
cp SKILL.md ~/.claude/skills/hotel/SKILL.md
cp workflows/*.md ~/.claude/skills/hotel/workflows/
cp references/*.md ~/.claude/skills/hotel/references/
```

### 2. Auto-updates (optional, recommended)

During install, you'll be asked: **`Enable auto-updates via SessionStart hook? [Y/n]`**.

If you say **Yes**, the installer adds a small SessionStart hook to `~/.claude/settings.json` that:

- Runs at most once every 24 hours, async (doesn't slow Claude Code startup)
- Maintains a hidden clone at `~/.claude/skills/hotel/.source/`
- Fast-forward merges new commits from this repo
- Re-runs `install.sh --non-interactive` when updates are available
- Prints a one-line notification in chat: `✓ /hotel updated to vX.Y.Z — <release URL>`
- Preserves your `taste-profile.md`, `booking-history.md`, and `cities/` data

After enabling, you never need to think about updates again.

**To disable later**: run `./install.sh --uninstall-hook` (removes the hook + sync script, leaves skill files intact).

### 3. Fill the taste profile

The profile is the calibration source. Edit `taste-profile.md` and fill in at minimum:

- **TOP-3 reference hotels** — your three calibration anchors (one ~9.5+, one ~8, one ~7)
- **Core formula** — what consistently produces a high rating for you
- **Anti-patterns** — what kills a hotel
- **Home city** — used to avoid recommending hotels in your own city
- **Genius Level** (Booking.com) — used in anniversary upgrade probability
- **Pet baseline** — pet-friendly is a boolean filter, not an occasion

Onboarding is currently manual via the template; a guided flow is on the v1.3 roadmap.

## Requirements

- **Claude Code** with skill support
- **Web search MCP** (Exa, Firecrawl, or equivalent) — strongly recommended. The skill auto-detects available search tools. Without web search, it falls back to your booking history and saved profile only.

## Usage

**Find a hotel:**

```
/hotel Lisbon
/hotel Andermatt ski
/hotel Tuscany anniversary
/hotel Lisbon concert
/hotel Vietnam new country
/hotel                      # Claude asks what you need
```

**Record a booking or rate a stay:**

```
booked Hotel X in Y, here is the confirmation PDF
stayed at Hotel X, 9.2/10
```

**Analyze patterns:**

```
analyze my hotel preferences
```

## Architecture

```
~/.claude/skills/hotel/
  SKILL.md                          # Skill entry — routing, principles, no-fabrication rule
  workflows/
    find-hotel.md                   # Search flow with multi-round persistence
    rate-stay.md                    # Phase 1 booking confirmation + Phase 2 post-stay review
    learn.md                        # Pattern analysis on H3-block stay entries (Peak / End / Disconfirm / Return aggregation)
  references/
    search-sources.md               # A/B/C reliability tiers, query templates, multi-language Reddit
    format-guide.md                 # Output format, anchor tiers, file-mode rule
    feedback-format.md              # H3-block template, decimal rating granularity
    pet-search.md                   # Pet protocol — room-type trap, call scripts, pet-paradox detection
    occasion-taxonomy.md            # Six-occasion ranking modifiers and anti-patterns

~/.claude/skills/hotel/data/        # Your data — path configured in the profile
  taste-profile.md                  # TOP-3, anchors, anti-patterns, references
  booking-history.md                # Peak / End / Disconfirm / Return blocks per stay
  cities/{slug}.md                  # City caches — Searched / Recommended / Mentioned / Excluded
  feedback/                         # Per-city blacklist + positive-reference files (written by rate-stay)
  trips/{slug}-{YYYY-MM}/           # Per-trip shortlist and booking-confirmation artifacts
  recommendations/                  # Saved recommendation outputs
```

## The six occasions

The same traveller has radically different hotel needs depending on the occasion. Occasion is a first-class input to ranking — composed into the candidate score, not applied as a downstream filter.

- **city-break** — short urban trip; up-weight walkability, neighborhood character, food-scene proximity
- **ski** — winter trip where the mountain is the point; up-weight ski-in/out, boot room, early breakfast, après venue
- **beach** — water is the point; up-weight direct sea access (distance in minutes), pool quality, A/C, true sea-view rooms
- **anniversary** — couple-only milestone; up-weight upgrade potential, romantic touches, secluded-vs-central balance
- **concert** — venue is the gravity well; up-weight venue walking distance, late check-out, late-night bar
- **new-country-exploration** — first or near-first visit; up-weight central orientation, English-speaking front-of-house, strong breakfast, real concierge

Default: city-break. Pet presence is a separate boolean filter applied across all occasions.

## Key mechanisms

**Multi-round persistence.** Every city search creates or extends `cities/{slug}.md` with four canonical sections (Searched / Recommended / Mentioned / Excluded) plus archived Round-N blocks and a Criteria-changes log. A second `/hotel Lisbon` query never starts cold — it builds on the prior round, re-evaluates mentioned candidates against the new criteria, and never re-recommends an excluded one.

**Reliability tiers A/B/C.** Sources are explicitly tiered. Every load-bearing claim about a hotel (renovation year, room count, owner identity, on-site spa) must trace to one A-tier source or two independent B-tier sources. Unsourced claims are marked with `❓` or trigger expanded search — never silently demoted.

**Calibration anchors.** Three reference hotels from your taste profile (high / mid / low tier) act as rating-drift guards. Before assigning a 9+, the skill checks: strictly better than your tier-8 anchor? If not, the rating caps at 8.

**Visit protocol.** Post-stay reviews capture Peak (the single moment that defined the stay) / End (the closing impression) / Disconfirm (must-fill, asymmetric probe if elliptical) / Return (yes / yes-situational / maybe / no). This replaces the older Pros/Cons format. Decimal granularity is required on 9.0+ — the 8.6–8.9 band is invalid by design to force commitment into the top tier.

**Multi-language Reddit.** Local-only gems surface in local-language threads. The skill queries r/Euskadi in Euskara, r/catalunya in Catalan, r/italy in Italian, r/turkey in Turkish, and city-equivalents in Portuguese, Greek, and Japanese alongside English.

**Operational verification.** Top-3 finalists pass two checks before output: a Booking.com availability call on the user's dates (no rooms across the calendar window = strong signal of renovation closure) and a 6-month press scan (`"{hotel}" renovation OR closed OR reopening`). Results render as `✓ verified open` / `⚠ availability check failed` / `⚠ press mentions renovation` / `❌ listing not found` in the summary table.

**Pet-friendly first-class.** The pet (small breed by default; configurable in taste-profile.md `## Pet config`) is a baseline parameter, not an occasion. Pet protocol handles the room-type trap (hotel pet-friendly but the booked room isn't), welcome-vs-tolerate distinction, pet-paradox detection (city has <20% pet-friendly hit rate), and ES + EN call scripts for confirmation. Explicit "couple-only" or "trip without the pet" signals flip `pet=false`.

**Spain festivo calendar.** Trips into Spain cross-check dates against a maintained festivo + puente table. Intersections trigger a warning about price premium, non-refundable promo rates, and tightened cancellation windows before the recommendation cards appear.

## Configuration

The taste profile is the single calibration source. Fill it before first use. The skill is designed to fail gracefully on missing sections (it asks instead of fabricating), but the more it knows, the sharper the first round.

- TOP-3 reference hotels are required — they are the rating-drift guards
- Anti-patterns are highly recommended — they front-load filtering before search
- Aspirational references (hotels you want to reach but haven't) are useful for "vibe" comparisons in output cards
- Booking history is optional at start; it accumulates through use and powers `/hotel learn`

## Contributing

Issues and PRs welcome at https://github.com/kirvahe/hotel-skill. The skill is opinionated — fixes and bug reports are highest-leverage; feature requests are weighed against the taste model.

## License

MIT
