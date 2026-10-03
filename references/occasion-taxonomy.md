---
name: occasion-taxonomy
description: Six-occasion taxonomy for hotel search. Occasion is a first-class input that changes ranking modifiers; inferred in Step 1 of find-hotel.md. Pet presence is a separate boolean filter applied across all occasions.
---

# Occasion Taxonomy — Hotels

## Contents
- The six occasions — city-break, ski, beach, anniversary, concert, new-country-exploration (definition, ranking modifiers, anti-patterns, anchor)
- Pet parameter
- Inference defaults
- Multi-occasion contexts

The same person has radically different hotel needs depending on the occasion. A "ski trip in Andermatt" and a "concert weekend in Lisbon" cannot share the same ranking function, even for the same traveler. This taxonomy makes occasion a first-class input to ranking — composed into the candidate score, not applied as a downstream filter.

Occasion is inferred in **Step 1 of `workflows/find-hotel.md`**, propagates through `continuation_state`, and is surfaced in the **Overview line** per `references/format-guide.md`.

## The Six Occasions

### city-break

Definition: short urban trip, ~2–4 nights, primary value is the city itself (food, walking, neighborhood texture).

Ranking modifiers:
- Up-weight walkability score (10-min walk to ≥3 anchor restaurants / cafés / sights)
- Up-weight neighborhood character (Trastevere / Eixample / Pera / Alfama-style — a place with a story, not a postcode)
- Up-weight food-scene proximity — restaurants the user would actually pick walking out the door
- Up-weight transit access (one metro / tram stop within 5 min)

Anti-patterns:
- Business-district isolation (CBD glass towers, conference-hotel rows)
- Suburban "scenic location" requiring car or 30-min transit to anything

Anchor: see your `taste-profile.md` `## Occasion anchors` for the city-break reference (typically a 7-tier hotel that punches above its category through neighborhood and personality).

### ski

Definition: winter trip where the mountain is the point. Snow, lifts, après.

Ranking modifiers:
- Up-weight ski-in / ski-out access (or ≤5-min walk to the closest gondola)
- Up-weight boot room with heated boot dryers
- Up-weight early-breakfast service (≥7:00, ideally 6:30) for first-lift mornings
- Up-weight après-ski venue access — bar / lounge / fireplace in-hotel, or known venue within walking distance
- Up-weight warming infrastructure (fireplace, sauna, indoor pool)

Anti-patterns:
- Long transfer to lifts (>15-min shuttle = disqualifying for serious skiers)
- No warm-up areas (no lobby fire, no spa) — turns the hotel into a glorified motel

Anchor: see your `taste-profile.md` `## Occasion anchors` for the ski reference (typically a compact chalet-boutique, ski-in/ski-out).

### beach

Definition: trip where the water is the point. Sea, pool, slow days.

Ranking modifiers:
- Direct beach access (note distance in minutes — "30 sec to sand" vs. "8-min walk")
- Pool quality (size, position, sun exposure, lounger density)
- Climate-controlled room (real A/C, not a noisy split unit)
- Sea-view room availability — confirm room type with view, not just hotel-on-coast

Anti-patterns:
- City-beach with crowds, kiosks, and parade traffic (Barceloneta-style)
- "Near the coast" but no waterfront connection — a 15-min uphill walk kills the format

Anchor: see your `taste-profile.md` `## Occasion anchors` for the beach reference (aspirational coastal property).

### anniversary

Definition: trip for a couple-only milestone — anniversary, birthday, special occasion. Memorability required.

Ranking modifiers:
- Room upgrade potential — Booking Genius / loyalty-tier status helps; flag hotels known to upgrade on occasion-marked stays
- Romantic touches — welcome amenity (flowers, prosecco, hand-written note) on arrival, ideally as standard
- Secluded vs. central balance — central enough to walk to dinner, secluded enough that the hotel feels like an event
- In-room dining quality (when breakfast-in-bed or late-night dining matters)

Anti-patterns:
- Family-with-kids energy — pool full of children, lobby chaos
- Sterile chain feel — the occasion needs character, not a points stay

Anchor: see your `taste-profile.md` `## Occasion anchors` for the anniversary reference. The operational bar: a hotel that notices the milestone and acts on it (e.g., upgrades the room).

### concert

Definition: trip built around a specific live event. The venue is the gravity well.

Ranking modifiers:
- Venue proximity — walking distance (≤15 min) or one short transit hop
- Late check-out — post-concert sleep recovery (12:00 minimum, ideally 14:00)
- Bar / lounge open late — a place to wind down without leaving the hotel after midnight
- Secure storage — relevant if the user is carrying an instrument, merchandise, or expensive gear

Anti-patterns:
- 30+ min from venue — defeats the point; the post-show transit drag kills the trip
- Early-only restaurants and 10:00 check-out — the hotel works against the schedule

Anchor: see your `taste-profile.md` `## Occasion anchors`. If empty, calibrate against your city-break anchor for the urban-fit piece, plus venue-walk distance as the differentiator.

### new-country-exploration

Definition: first or near-first visit to a country. The traveler is orienting.

Ranking modifiers:
- Central location for first-time orientation — old town, main spine, or the canonical "where to be" district
- English-speaking front-of-house — low friction in an unfamiliar territory, especially for currency / SIM / transit questions on Day 1
- Strong breakfast — the introduction to local cuisine when the user hasn't yet found their restaurants
- Concierge with real local knowledge — neighborhood walks, transit, where-to-eat advice that beats Google Maps top-rated

Anti-patterns:
- Business-district hotels with no neighborhood story — the country becomes invisible
- Brand-uniform experience — a chain in Tokyo feels like the same chain in Dallas, defeating the point

Anchor: see your `taste-profile.md` `## Occasion anchors` for the new-country-exploration reference (typically a heritage conversion in a central old-town district).

## Pet parameter

If a pet is set in the user's `taste-profile.md` `## Pet` section, it's a **baseline boolean filter**, not an occasion. Most trips include the pet by default but **not all** — couple-only travel happens (anniversaries, concerts in cities where the pet stays home, hard-to-reach destinations).

When `pet=true` in the Step 1 parse, apply pet-friendly rules from `references/pet-search.md` across whichever occasion was inferred — pet-friendly filter, pet-paradox warning at <20% hit rate, ✅/⚠️/❓/❌ notation in the response. When `pet=false`, no pet-search overhead — the occasion's modifiers run alone.

Both states are valid for any occasion. The Step 1 echo line surfaces both — `Proceeding as {occasion} trip with pet={true|false}. Correct me before Step 4 if wrong.` (declarative, non-blocking) — so the user can interject if either inference is wrong.

If no pet is set in `taste-profile.md`, the pet line is omitted from the echo and pet filters never run.

## Inference defaults

| Signal in query | Inferred occasion |
|---|---|
| "concert in X", "[band] in X", "show", "festival" | concert |
| "ski in X", "skiing", "Andermatt / Courchevel / Verbier" | ski |
| "beach", "coast", "sea", named beach destination (Sardinia, Mallorca, Algarve) | beach |
| "anniversary", "birthday", "celebrate", "special occasion" | anniversary |
| "first time in [country]", "never been to", "new country" | new-country-exploration |
| Generic "where to stay in X" with no other signal | city-break |

Travel queries default to **city-break** unless an explicit signal pushes elsewhere.

## Multi-occasion contexts

Some queries blend occasions ("anniversary trip to a new country" = anniversary + new-country-exploration). Apply both modifier sets. Up-weights stack; anti-patterns take the most restrictive. Surface both in the Overview line.
