# Roadmap — /hotel skill

## v1.1 (current — first public release)

Shipped as a CE-upgrade from the internal v1.0 baseline. Mature mechanisms from the sibling `/restaurant` skill (multi-round persistence, source tier model, visit protocol) ported to the hotel domain, with hotel-specific additions (occasion taxonomy, operational verification, Spain festivo calendar, pet protocol as first-class parameter).

- Multi-round city cache (Searched / Recommended / Mentioned / Excluded + Round-N archive + Criteria changes)
- Six-occasion taxonomy with per-occasion ranking modifiers
- Calibration anchors (3-tier reference from taste-profile)
- Visit protocol (Peak / End / Disconfirm / Return) with decimal granularity on 9.0+
- Operational verification (Booking availability + press scan) for top-3 finalists
- Multi-language Reddit search across 7+ regional subs
- Owner/architect interviews as A-tier source
- Booking-rating bias adjustment heuristics
- Pet as boolean parameter, not occasion

## v1.2 (planned)

Quality and onboarding improvements before considering distribution work.

- **Guided onboarding** — replace manual taste-profile fill with a conversational flow (batched question blocks, ~15 min). Mirror the `/restaurant` onboarding pattern.
- **Direct hotel-site availability check** — augment Booking.com availability with a direct check against the hotel's own reservation engine (when feasible without headless browser). Catches Booking-only delistings that the press scan misses.
- **Genius Level integration** — track per-hotel Genius discount and free-upgrade eligibility, surface in the summary table. Important for anniversary occasions where upgrade probability matters.
- **Per-occasion learn aggregation** — `/hotel learn` reports hit rate per occasion ("ski stays average 8.6, beach stays 7.2") so the profile reflects where the user's taste is reliably calibrated vs. drifting.
- **Festivo calendar auto-refresh** — Spain festivo table currently hand-maintained. Add an annual auto-verify against BOE.es. Extend to Italian (Ferragosto) and French (Toussaint, 15 Aug, 1 May, Pentecôte) puente windows once a real trip surfaces the need.
- **City-quirks auto-generation** — after 3+ stays in a city, generate neighborhood map and operational quirks (parking habits, transfer norms, front-desk language) from booking-history into the city cache.

## v2.0 (vision)

Larger structural moves, all gated on real evidence of need from v1.x use.

- **Multi-traveler profiles** — per-traveler taste overlay (e.g., father-in-law profile, couple-vs-solo profile). One install, named profiles in `config.yml`, switch with `--profile`.
- **Real-time price tracking** — watch shortlisted hotels for price drops between recommendation time and cancellation deadline. Alert when a tracked hotel crosses a user-set threshold.
- **Hotel API integration** — if Booking.com partner program access becomes feasible, replace search-and-link with direct availability and rate-plan reads. Same for SLH / LHW / Design Hotels APIs where they exist.
- **Multi-property trips** — chain of hotels in a route (e.g., 3-stop Tuscany trip). Joint optimization for travel time between properties, not per-hotel optimization.
- **Calendar sync** — read upcoming travel from Google Calendar / iCal, pre-warm city caches, surface festivo intersections proactively before the user even searches.
- **Booking debrief loop** — 2 weeks after a recommendation, ask "did you book? did you stay?" to close the recommendation→outcome loop and feed pattern analysis automatically.

## Out of scope (won't build)

- Crowd-rating aggregation (TripAdvisor, Yelp) — explicitly excluded by the source model
- Mass-market discovery (chain finders, all-inclusive marketplaces) — the skill is opinionated against these by design
- Multi-domain merge with `/restaurant` into a unified "city" skill — premature abstraction; revisit only if a third recommendation skill emerges
