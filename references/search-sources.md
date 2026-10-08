## Contents
- Search languages
- Trusted sources (when / why / query patterns): curated lists and collections; Michelin Guide and Michelin Keys; Condé Nast Traveller; local press and local guides; owner / architect / designer interviews (A-tier); Reddit; multi-language Reddit subs; Booking (search results only)
- Link only: Google Maps
- Banned sources (NEVER use)
- Reliability tiers A/B/C (single taxonomy) and known C-tier failure cases
- Booking-rating bias adjustment
- Search strategy — source order, validation, cities with quirks

<overview>
Where find-hotel looks for candidates, and how much each source can carry. Goal: maximum recommendation accuracy for boutique/design hotels. The research agents' briefs in `references/briefs/` apply these tiers; `research-contract.md` there holds the tool route and caps.
</overview>

<search_languages>
## Search languages

Every query follows the search-language rule in `workflows/find-hotel.md` Step 3: **A** the country's language (plus the regional language where one exists) first, then **B** English, then **C** the language of the subject's origin or community, if any; never the request language on its own. The patterns below are English templates: rewrite them for A and C the way a native speaker would type them, and keep operators (`site:`, `OR`, `NOT`) and brand/collection names unchanged. `{year}` is the current year.
</search_languages>

<sources>

<source name="Curated lists and collections">
**When:** Always
**Why:** Each list or collection has a curation standard; membership is an A-tier signal
**Lists:** Small Luxury Hotels (SLH), Design Hotels, Leading Hotels of the World (LHW), Mr & Mrs Smith, World's 50 Best Hotels, and similar curated lists

**Patterns:**
- `site:slh.com {city}`
- `site:designhotels.com {city}`
- `{city} leading hotels of the world`
- `site:mrandmrssmith.com {city}`
- `"World's 50 Best Hotels" {city}`

**Collection guide:**
- **LHW** — grand classic, 5-star level
- **SLH** — boutique luxury, personal service
- **Design Hotels** — design-forward, creative, often < 50 rooms
- **Autograph Collection** — independent character hotels within the Marriott umbrella
</source>

<source name="Michelin Guide and Michelin Keys">
**When:** Always
**Why:** Inspector-selected hotels; a Michelin Key is the hotel equivalent of a star. Tablet Hotels is part of this selection
**Patterns:**
- `site:guide.michelin.com {city} hotel`
- `{city} Michelin Key hotel` (use Michelin's own name in language A, e.g. Spanish "Llave MICHELIN")
</source>

<source name="Conde Nast Traveller">
**When:** For design-forward, architecturally interesting hotels
**Why:** Curated lists and full reviews emphasizing design and atmosphere
**Patterns:**
- `{city} best boutique hotel conde nast traveller {year}`
- `{city} best new hotel conde nast traveller`
- `site:cntraveller.com {city} hotel`
</source>

<source name="Local press and local guides">
**When:** Always, in language A first
**Why:** Local editors cover small and new hotels that international lists miss, and report closures, reopenings and renovations
**What counts:** the city's and region's newspapers (travel, lifestyle and city sections), city magazines, national editions of travel magazines, local guides with an editorial team. A personal blog is not a local guide.
**Patterns (rewrite natively in language A):**
- `where to stay in {city} charming hotels`
- `new hotel {city} historic building restored`
- `{city} hotel opening {year}`
The outlets found for a city are saved in its city cache and reused on later trips.
</source>

<source name="Owner / architect / designer interviews">
**When:** When a hotel has a named owner, in-house architect, or designer who has been profiled in editorial press
**Why:** Insider perspective on philosophy, recent renovations, ongoing curation — A-tier signal

## Owner / architect / designer interviews (A-tier)

When a hotel's owner, in-house architect, or designer is profiled in a quality editorial venue, those interviews carry A-tier weight — equivalent to direct hotel site or SLH/LHW/Design/Autograph official listing.

**Venues that count as editorial-quality:**
- Monocle (especially Monocle on Design, Monocle 24)
- Apartamento
- Wallpaper*
- Cereal Magazine
- Openhouse Magazine
- The Gentlewoman / Fantastic Man (occasional hotel features)
- Kinfolk (travel-adjacent features only)
- The New York Times T Magazine (travel features)

**Query templates:**
- `"{hotel name}" interview owner OR architect OR designer`
- `"{hotel name}" Monocle OR Apartamento OR Wallpaper OR Cereal OR Openhouse`
- `"{hotel name}" -tripadvisor -booking ("designed by" OR "owned by")` (negative filters drop tourist sites)

**Anti-pattern:** generic press releases ("Hotel announces new partnership"), influencer interviews, sponsored content. These are NOT A-tier — at best B-tier, often C.
</source>

<source name="Reddit">
**When:** Always
**Why:** Real travelers, detailed reviews, no ads
**How:** the Reddit brief (`references/briefs/reddit.md`). Threads are found with `mcp__firecrawl__firecrawl_search` (`site:reddit.com`) and subreddit scans, and read in full through `bin/reddit_fetch.py`. Exa and WebSearch return no Reddit threads. Search snippets are not Reddit data: a mention counts only with the permalink of the thread or comment that was read.

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
**When:** Always — every city, every country (search languages A/B/C, see `workflows/find-hotel.md` Step 3)
**Why:** Diaspora and locals surface character signals that tourist-language results miss

## Multi-language Reddit subs (run alongside English)

Always search the country-language subs (language A) — plus regional-language subs where they exist — in addition to English (B: r/travel, r/europe), and communities in the language of the subject's origin (C) when there is one — never the request language on its own. Diaspora and locals surface character signals tourist-language results miss. The list below is not exhaustive: for a country not listed, find its national and city subs (e.g. Spain: r/es, r/askspain, r/{city}).

**Per-country sub list:**

- **Basque Country (Bilbao, San Sebastián, Donosti):** r/Euskadi — queries in Euskara when possible, also Spanish queries work
- **Catalunya (Barcelona, Girona, Sitges):** r/catalunya — Catalan queries; do not auto-translate place names (preserve "Eixample" not "Eixample area")
- **Italy (all cities):** r/italy + r/AskItalia + city-specific r/roma, r/milano, r/firenze — Italian queries
- **Turkey (Istanbul, İzmir, Bodrum):** r/turkey + r/istanbul + r/Turkey — Turkish queries (Türkçe), include district-level (Galata, Karaköy, Beyoğlu)
- **Portugal (Lisbon, Porto):** r/portugal + r/lisbon — Portuguese queries
- **Greece (Athens, islands):** r/greece + r/athens — English mostly works, but Greek queries surface local-only listings
- **Japan (any city):** r/japan + city-specific r/tokyo, r/kyoto, r/osaka — English queries surface tourist-tier; Japanese queries via subs like r/Japanese surface ryokan / local-only

**How to apply:**
- Run regional-language queries IN PARALLEL with English queries (via parallel subagent calls in find-hotel.md Step 3), but list the A-language block first
- Do not REPLACE English queries — local-language adds; English is still good for tourist-friendly hotels
- Translate user's original keywords to the regional language where natural (e.g., "neighborhood" → "barrio" in Spanish, "quartiere" in Italian, "mahalle" in Turkish)
</source>

<source name="Booking.com (search results only)">
**When:** Always, through search results
**Why:** Guest scores and review counts at scale; small, well-rated listings that press and Reddit miss
**How:** the Booking-search brief (`references/briefs/booking-search.md`). `site:booking.com` searches only: the score and review count come from the search result's text, quoted. No agent opens a Booking page, logged in or not.

**Patterns:**
- `site:booking.com {city} boutique hotel old town`
- `site:booking.com "{hotel name}" {city}` (score lookup)

**Rules:**
- A candidate known only from Booking results stays in play with the "Booking only, unconfirmed" flag. A bare Booking listing does not confirm a hotel.
- Two different scores for one hotel, or none found: "score unverified ❓"; the user checks it through the dated Booking link.
- Prices and availability come from the hotel's own booking engine, never from Booking. The user sees the Genius price through the dated Booking link in the answer.
</source>

</sources>

<link_only>
## Link only: Google Maps

Google Maps is not a source: no candidates, ratings, reviews or photos are taken from it. Every hotel in the answer carries a Google Maps link, built by the link script from name, street and city.
</link_only>

<banned_sources>
## NEVER Use

| Source | Why |
|---|---|
| Instagram | Not used for hotel research |
| Blogs | Single-author, influencer and affiliate "best hotels" sites, Medium and Substack posts: no editorial check |
| TripAdvisor | Mass market, tourist traps in top positions |
| Yelp | Same problem |
| Mass tourist guides | "Top 10 hotels in Rome" = garbage |
| AI-generated listicles | Rewrite TripAdvisor |
| Expedia / Hotels.com | No curation, price-driven |
| Airbnb pages | Never opened; Airbnb appears only as a dated search link for special formats found through trusted sources |
</banned_sources>

<reliability_tiers>
## Reliability tiers — single taxonomy

Every claim about a hotel (character, pet policy, collection membership, renovation year) must be backed by sources at the right tier. This taxonomy is shared across the skill: `pet-search.md` applies it to pet-friendly claims, `find-hotel.md` applies it to character and fit claims.

| Tier | Trust level | Sources | Rule |
|---|---|---|---|
| **A** | Trustable alone | Direct hotel website (dedicated page, not buried FAQ); SLH / LHW / Design Hotels / Mr & Mrs Smith official listings; Michelin Guide hotel page (Michelin Key or selection); World's 50 Best Hotels entry; Autograph/Marriott corporate policy page **for the specific property**; Condé Nast Traveller full review (not list roundup); local press article about this hotel; owner / architect / designer interview in an editorial venue | 1 source is enough to make the claim |
| **B** | Need two independent | Reddit thread with a specific trip report (not "is X good?"), read in full; curated list roundup entry; local guide entry; i-escape tag | Need 2 B-tier sources, and they must be independent (not mirrors of each other) |
| **C** | Never trust alone | **BringFido** (observed to list tolerate-with-high-fee boutique hotels as "pet-friendly" without distinguishing welcome vs tolerate) | Can be a lead, never a source. Must be cross-referenced against A or B before the claim lands in output |

A Booking score from search results is evidence for the score only, never for character or pet claims.

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

### Source order
Research runs as three parallel families, each with its own brief in `references/briefs/`, its per-agent query and page-read caps, and its tool route:
1. Curated lists, collections and local press (`curated-press.md`)
2. Reddit (`reddit.md`)
3. Booking listings in search results (`booking-search.md`)

Hotel websites are read after the fit filter, for closures, pet policy and availability (`resolver.md`, `final-check.md`). Google Maps is only a link.

### Validation:
A hotel is a reliable recommendation if its load-bearing claims pass the `<reliability_tiers>` rule above:
- **1 A-tier source** (direct site, collection listing, Michelin Guide page, CNT full review, local press article, Mr & Mrs Smith), **or**
- **2 independent B-tier sources** (Reddit trip report + curated roundup, two Reddit threads from different travelers, etc.)

Collection membership (SLH, Design Hotels, LHW, Autograph) and a Michelin Key are themselves A-tier signals. A candidate found only in Booking results stays with the "Booking only, unconfirmed" flag; a C-tier-only claim never ships without its ❓.

### Cities with quirks:
City-specific patterns (problematic cities, home-city knowledge, etc.) are tracked in `{skill}/data/taste-profile.md` `## Problematic cities` and `## Base` sections. The skill consumes those automatically — do not hardcode city rules here.

General heuristics that apply everywhere:
- Avoid the most touristed central strip (Rambla / Plaza Mayor / Centro Storico equivalents) unless the user explicitly wants it
- Prefer adjacent neighborhoods with character (e.g., Trastevere over Centro Storico, Born over Rambla)
- In the user's home city, focus on NEW openings or overlooked gems — the user likely knows the established scene
</search_strategy>
