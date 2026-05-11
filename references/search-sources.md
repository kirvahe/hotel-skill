<overview>
Search query patterns for each approved source. Goal: maximum recommendation accuracy for boutique/design hotels.
</overview>

<sources>

<source name="Reddit">
**When:** Always (first source)
**Why:** Real travelers, detailed reviews, no ads

**Query patterns:**
- `site:reddit.com r/travel {city} boutique hotel hidden gem`
- `site:reddit.com {city} best hotel NOT chain small rooms`
- `site:reddit.com {city} design hotel recommendation locals`
- `site:reddit.com {city} romantic hotel couples boutique`
- `site:reddit.com {city} hotel architectural beautiful building`

**City subreddits:**
- Madrid: r/Madrid, r/SpainTravel
- Rome: r/rome, r/ItalyTravel
- Paris: r/paris, r/ParisTravelGuide
- Lisbon: r/Lisboa, r/portugal
- Vienna: r/wien, r/Vienna
- Barcelona: r/Barcelona
- Budapest: r/budapest
- Istanbul: r/istanbul
- General: r/travel, r/solotravel, r/TravelHacks

**Red flags:** post < 3 upvotes, author promoting their own property
</source>

<source name="Multi-language Reddit subs">
**When:** For any city in a country with strong regional language identity (Spain regions, Italy, Turkey, Portugal, Greece, Japan, etc.)
**Why:** Diaspora and locals surface character signals that tourist-language results miss

## Multi-language Reddit subs (run alongside English)

For countries with strong regional language identity, search regional-language Reddit subs in addition to English (r/travel, r/europe). Diaspora and locals surface character signals tourist-language results miss.

**Per-country sub list:**

- **Basque Country (Bilbao, San Sebastián, Donosti):** r/Euskadi — queries in Euskara when possible, also Spanish queries work
- **Catalunya (Barcelona, Girona, Sitges):** r/catalunya — Catalan queries; do not auto-translate place names (preserve "Eixample" not "Eixample area")
- **Italy (all cities):** r/italy + r/AskItalia + city-specific r/roma, r/milano, r/firenze — Italian queries
- **Turkey (Istanbul, İzmir, Bodrum):** r/turkey + r/istanbul + r/Turkey — Turkish queries (Türkçe), include district-level (Galata, Karaköy, Beyoğlu)
- **Portugal (Lisbon, Porto):** r/portugal + r/lisbon — Portuguese queries
- **Greece (Athens, islands):** r/greece + r/athens — English mostly works, but Greek queries surface local-only listings
- **Japan (any city):** r/japan + city-specific r/tokyo, r/kyoto, r/osaka — English queries surface tourist-tier; Japanese queries via subs like r/Japanese surface ryokan / local-only

**How to apply:**
- Run regional-language queries IN PARALLEL with English queries (via parallel subagent calls in find-hotel.md Step 3)
- Do not REPLACE English queries — local-language adds; English is still good for tourist-friendly hotels
- Translate user's original keywords to the regional language where natural (e.g., "neighborhood" → "barrio" in Spanish, "quartiere" in Italian, "mahalle" in Turkish)
</source>

<source name="Owner / architect / designer interviews">
**When:** When a hotel has a named owner, in-house architect, or designer who has been profiled in editorial press
**Why:** Insider perspective on philosophy, recent renovations, ongoing curation — A-tier signal

## Owner / architect / designer interviews (A-tier)

When a hotel's owner, in-house architect, or designer is profiled in a quality editorial venue, those interviews carry A-tier weight — equivalent to direct hotel site or SLH/LHW/Design/Autograph official listing.

**Why:** insider perspective on philosophy, recent renovations, ongoing curation, and the "why" behind design choices. Much higher signal than generic tourist press coverage.

**Venues that count as editorial-quality:**
- Monocle (especially Monocle on Design, Monocle 24)
- Apartamento
- Wallpaper*
- Cereal Magazine
- Openhouse Magazine
- The Gentlewoman / Fantastic Man (occasional hotel features)
- Kinfolk (travel-adjacent features only)
- The New York Times T Magazine (travel features)

**Query templates (run alongside Reddit / CNT / Tablet queries):**
- `"{hotel name}" interview owner OR architect OR designer`
- `"{hotel name}" Monocle OR Apartamento OR Wallpaper OR Cereal OR Openhouse`
- `"{hotel name}" -tripadvisor -booking ("designed by" OR "owned by")` (negative filters drop tourist sites)

**Anti-pattern:** generic press releases ("Hotel announces new partnership"), influencer interviews, sponsored content. These are NOT A-tier — at best B-tier, often C.
</source>

<source name="Conde Nast Traveller">
**When:** For design-forward, architecturally interesting hotels
**Why:** Curated lists emphasizing design and atmosphere

**Patterns:**
- `{city} best boutique hotel conde nast traveller 2025 2026`
- `{city} best new hotel conde nast traveller`
- `site:cntraveller.com {city} hotel`
- `{city} hotel design architecture conde nast`
</source>

<source name="Collections & Curators">
**When:** For quality signal — collection membership = vetted
**Why:** LHW, SLH, Design Hotels, Autograph — each has a curation standard

**Patterns:**
- `{city} leading hotels of the world`
- `{city} small luxury hotels slh`
- `{city} design hotels member`
- `{city} autograph collection marriott boutique`
- `site:designhotels.com {city}`
- `site:slh.com {city}`

**Collection guide:**
- **LHW** — grand classic, 5-star level
- **SLH** — boutique luxury, personal service
- **Design Hotels** — design-forward, creative, often < 50 rooms
- **Autograph Collection** — independent character hotels within Marriott umbrella
</source>

<source name="Mr & Mrs Smith / Tablet Hotels">
**When:** For curated boutique picks
**Why:** Hand-picked, reviewer-tested boutique hotels

**Patterns:**
- `{city} mr mrs smith hotel`
- `{city} tablet hotels boutique`
- `site:mrandmrssmith.com {city}`
- `site:tablethotels.com {city}`
</source>

<source name="Google Maps">
**When:** For verifying reviews, location, and photos
**Why:** Real reviews, exact address, neighborhood context

**Usage:**
- Check rating (< 4.0 = red flag)
- Read 2-3 recent reviews
- Check photos (real interior vs stock)
- Verify neighborhood (walkability, safety, vibe)
- Link is MANDATORY in every recommendation
</source>

<source name="Booking.com">
**When:** For pricing, availability, and loyalty-program perks
**Why:** Canonical pricing source; surface Genius / loyalty-tier discounts if the user has a tier set in `taste-profile.md`

**Usage:**
- Check price range
- Check room types and sizes
- Check Genius / loyalty discount availability
- Link is MANDATORY in every recommendation
- Note if hotel offers "Genius discount" or "free upgrade" perks
</source>

</sources>

<banned_sources>
## NEVER Use

| Source | Why |
|---|---|
| TripAdvisor | Mass market, tourist traps in top positions |
| Yelp | Same problem |
| Instagram | Not used for hotel research |
| Mass tourist guides | "Top 10 hotels in Rome" = garbage |
| AI-generated listicles | Rewrite TripAdvisor |
| Expedia / Hotels.com | No curation, price-driven |
</banned_sources>

<reliability_tiers>
## Reliability tiers — single taxonomy

Every claim about a hotel (character, pet policy, collection membership, renovation year) must be backed by sources at the right tier. This taxonomy is shared across the skill: `pet-search.md` applies it to pet-friendly claims, `find-hotel.md` applies it to character and fit claims.

| Tier | Trust level | Sources | Rule |
|---|---|---|---|
| **A** | Trustable alone | Direct hotel website (dedicated page, not buried FAQ); SLH / LHW / Design Hotels / Mr & Mrs Smith official listings; Autograph/Marriott corporate policy page **for the specific property**; Condé Nast Traveller full review (not list roundup) | 1 source is enough to make the claim |
| **B** | Need two independent | Reddit thread with specific trip report (not "is X good?"); Tablet Hotels curated pick; Google Maps reviews (recent, detailed, not aggregated rating alone); i-escape tag; Pipper on Tour pet listing | Need 2 B-tier sources, and they must be independent (not mirrors of each other) |
| **C** | Never trust alone | **BringFido** (observed to list tolerate-with-high-fee boutique hotels as "pet-friendly" without distinguishing welcome vs tolerate); "Top 10 hotels in {city}" aggregator listicles; generic travel blogs without trip reports; AI-generated content farms | Can be a lead, never a source. Must be cross-referenced against A or B before the claim lands in output |

**How to use:**
- When writing a recommendation, every load-bearing claim (character, pet, collection, recent renovation) must trace to at least one A-tier or two B-tier sources
- If only C-tier sources support a claim → mark it `❓` in the output and flag for verification (phone call for pet, direct-site check for renovation)
- Never silently promote a C-tier source to B just because nothing else turned up — expand the search instead

**Known C-tier failure cases:**
- **BringFido false-positive pattern:** has labeled tolerate-with-high-fee boutique hotels as "pet-friendly". Direct-site verification routinely reveals a per-night fee plus restricted rooms with no welcome treatment. Rule: never trust BringFido alone — always cross-reference with A-tier or 2×B-tier sources before the claim lands in output.

## Booking-rating bias adjustment

Booking.com aggregate ratings are not raw signal. Apply context-aware reweighting before relying on them:

- **Tourist-zone bias (subtract ~1 point):** Hotel in heavy-tourist district (Plaza Mayor, Champs-Élysées, Trastevere, Ramblas) with Booking 9.0+ is closer to "actually 8.0" — high-volume guests inflate scores via low-friction stays without judging character.
- **Hidden-gem suppression (add ~1):** SLH/Design/Autograph independent with Booking 7.5 in a small market — single-A-source confidence outweighs the suppressed aggregate. Worth investigation, often actually 8.5+.
- **Family-business signal (add ~0.5):** Booking 8.0–8.5 with consistent "owner himself helped us" / "felt like home" in reviews — operational character undervalued by review optimizers.

These are heuristics, not formulas. State the adjustment explicitly in the recommendation card: "Booking 9.2 (Plaza Mayor — adjust to ~8.0 for tourist bias)."
</reliability_tiers>

<search_strategy>
## Search Strategy

### Minimum queries: 6
### Recommended: 8-10

### Priority order:
1. Reddit (always first)
2. Collections (Design Hotels, SLH, LHW)
3. Conde Nast / Mr & Mrs Smith / Tablet
4. Fresh articles 2024-2026 (new openings)
5. Google Maps (verification)
6. Booking.com (pricing)

### Validation:
A hotel is a reliable recommendation if its load-bearing claims pass the `<reliability_tiers>` rule above:
- **1 A-tier source** (direct site, collection listing, CNT full review, Mr & Mrs Smith), **or**
- **2 independent B-tier sources** (Reddit trip report + Tablet pick, two Reddit threads from different travelers, etc.)

Collection membership (SLH, Design Hotels, LHW, Autograph) is itself an A-tier signal. A C-tier-only hotel never ships in the shortlist — either upgrade the sourcing or drop it.

### Cities with quirks:
City-specific patterns (problematic cities, home-city knowledge, etc.) are tracked in `~/.claude/skills/hotel/data/taste-profile.md` `## Problematic cities` and `## Home city` sections. The skill consumes those automatically — do not hardcode city rules here.

General heuristics that apply everywhere:
- Avoid the most touristed central strip (Rambla / Plaza Mayor / Centro Storico equivalents) unless the user explicitly wants it
- Prefer adjacent neighborhoods with character (e.g., Trastevere over Centro Storico, Born over Rambla)
- In the user's home city, focus on NEW openings or overlooked gems — the user likely knows the established scene
</search_strategy>
