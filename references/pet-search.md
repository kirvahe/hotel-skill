<overview>
Pet-friendly hotel protocol. If a pet is set in the user's `taste-profile.md` `## Pet` section, pet-friendly is a baseline filter on every trip by default — not a mode. This file is the lookup reference for the four traps that repeatedly cost tokens and user trust: room-type-level pet blocks, welcome-vs-tolerate confusion, single-source false positives, and pet-paradox cities.
</overview>

<room_type_trap>
## The room-type trap

Booking.com shows pet icons on **individual room types**, not just on hotels overall. A hotel can be pet-friendly at the property level while specific room types carry a 🚷 "Pets not allowed on this room type" marker. Example failure mode: an Autograph Collection property where the hotel-level page confirmed pet-friendly (brand policy), but the booked "Guest Room with Double Bed" carried the no-pets icon, and the pet was missing from the reservation's guest count on the confirmation PDF. Both issues would have been invisible if only the hotel overview page had been checked.

**Rule:** Before recommending or confirming a room, verify pet policy **on the specific room-type page**, not just on the hotel overview page. If in doubt → flag it and route to the phone call script below.

**At confirmation time** (Phase 1 of rate-stay.md): if the confirmation PDF or email shows 🚷 next to the booked room type → surface as a red flag even when the hotel is listed as pet-friendly. The user needs to call the hotel before the free-cancel deadline.
</room_type_trap>

<welcome_vs_tolerate>
## Welcome vs tolerate — learn the markers

Hotels that **welcome** pets invest in the experience. Hotels that **tolerate** pets charge a fee and restrict you. Both are technically "pet-friendly" but only the first is a match for the user's profile.

**Welcome markers:**
- Pet bed / bowl / treats provided in-room on arrival
- In-room grooming kit or dedicated pet toiletries
- Walking service or pet-sitter available
- Restaurant allows pets in the dining room (not just terrace)
- Website has a dedicated "Traveling with pets" page, not a buried FAQ line
- Staff training mentioned (e.g., "our concierge can recommend pet-friendly walks")

**Tolerate markers:**
- Flat pet fee without specifying what you get
- "Pets allowed in specific rooms only"
- Breed / weight restrictions — check against your pet's weight in `taste-profile.md`; common cutoffs are 10 kg and 15 kg
- Pets not allowed in common areas
- "Please notify us in advance" wording without confirmation workflow

**Rule:** When scoring candidates, bias toward welcome markers over tolerate markers. A 7-rated hotel with real pet welcome beats a 9-rated hotel with grudging tolerance.
</welcome_vs_tolerate>

<cross_reference_rule>
## Cross-reference rule — never trust a single source for "pet-friendly"

A "pet-friendly" claim must be confirmed by:

- **One A-tier source**, or
- **Two B-tier sources** (independent, not mirrors of each other)

**A-tier (trustable alone):**
- Direct hotel website — dedicated pets page or explicit line in room policy
- SLH / LHW / Design Hotels / Leading Hotels of the World — official collection pet listing
- Mr & Mrs Smith — pet filter on the booking page
- Marriott / Hyatt / IHG corporate pet policy page if the hotel is part of a brand whose policy is binding at property level (Autograph = usually yes, check)

**B-tier (need two):**
- Reddit thread with a specific trip report (not generic "is X pet-friendly?")
- Pipper on Tour listing
- i-escape pet tag
- TripAdvisor pet-specific review (only if quoted in full — do not trust aggregated labels)

**C-tier (known false positives — never use alone):**
- **BringFido** — observed to label tolerate-with-high-fee boutique hotels as "pet-friendly" without distinguishing welcome vs tolerate. Always cross-reference against A or B before trusting the label.
- Generic pet travel blogs without trip reports
- "Top 10 pet-friendly hotels in X" aggregator lists

**Rule:** If only C-tier sources support the pet-friendly claim → mark it as ❓ in the output, not ✅. Route to phone call before booking.
</cross_reference_rule>

<pet_paradox_detection>
## Pet-paradox city detection

Some cities have a structural mismatch: many boutique hotels, but few that allow dogs at the character-first tier the user wants. The first identified case surfaced in a small boutique-heavy coastal city in northern Spain: ~15 candidates evaluated, 0 pet-friendly matches at the taste-profile level after two search rounds.

**Detection rule:** After the first 5 candidate hotels are evaluated, if the pet-friendly hit rate is **below 20%** (0 or 1 hits out of 5), stop and **tell the user explicitly**:

> "City {X} is thin for pet + boutique + character. Hit rate after 5 candidates: {N}/5. Options: (a) expand to {adjacent city}, (b) loosen the character bar (not recommended), (c) fewer options in the shortlist, each hand-verified. Which do you prefer?"

Do **not** quietly keep searching until you find 5. Do **not** lower the bar to pad the list. Bar-lowering picks that "technically allow pets" but miss character or charge grudging fees get rejected — better to shrink the shortlist than dilute it.

**Known pet-paradox cities:** start empty — add entries here as cases surface. Typical qualifying pattern: boutique-heavy coastal or old-town cities where pet-friendly × genuine-character overlap is <20% across 5 candidates. Record findings in the local per-city feedback files, not this reference.
</pet_paradox_detection>

<call_scripts>
## Call scripts — copy, fill placeholders, call

Use these when (a) pet policy is unclear, (b) room-type trap is suspected, (c) pet is not in the reservation guest count, or (d) only C-tier sources support the pet claim.

### Spanish (Spain, LatAm)

> Hola, tengo una reserva con el número **{CONF_NUMBER}** para el **{CHECK_IN_DATE}**, a nombre de **{GUEST_NAME}**. Viajamos con un **{BREED}** de **{WEIGHT} kg**. Tengo dos preguntas:
>
> 1. ¿Está permitido el perro en mi tipo de habitación, **{ROOM_TYPE}**? Vi un icono en la confirmación que me hizo dudar.
> 2. ¿Podrían añadir al perro al recuento de huéspedes de la reserva y enviarme un correo confirmando la política de mascotas para mi habitación específica?
>
> Quiero estar seguro antes de la fecha límite de cancelación gratuita, que es **{CANCEL_DEADLINE}**. Muchas gracias.

### English (everywhere else)

> Hello, I have a reservation with confirmation number **{CONF_NUMBER}** for **{CHECK_IN_DATE}** under the name **{GUEST_NAME}**. We travel with a **{BREED}** weighing **{WEIGHT} kg**. Two questions:
>
> 1. Are pets allowed in my specific room type, **{ROOM_TYPE}**? I saw an icon on the confirmation that made me unsure.
> 2. Could you add the pet to the guest count on the reservation and send me a short email confirming the pet policy for my specific room?
>
> I'd like to sort this out before the free-cancellation deadline, which is **{CANCEL_DEADLINE}**. Thank you.

### Placeholders to fill before calling

- `{CONF_NUMBER}` — confirmation number from booking-details.md
- `{CHECK_IN_DATE}` — DD Month YYYY
- `{GUEST_NAME}` — full name on the reservation
- `{BREED}` — pet breed from `taste-profile.md` `## Pet` (e.g., "small terrier", "miniature poodle")
- `{WEIGHT}` — pet weight in kg from `taste-profile.md` `## Pet`
- `{ROOM_TYPE}` — verbatim room type string from the confirmation
- `{CANCEL_DEADLINE}` — exact date + time + timezone ("29 April 2026, 23:59 CEST")

**After the call:** ask the hotel to email written confirmation. Save the email next to `booking-details.md` as `pet-confirmation-{YYYY-MM-DD}.eml` or `.pdf`. Do not rely on verbal assurance.
</call_scripts>

<anti_patterns>
Avoid:
- Trusting BringFido as a single source for pet-friendly
- Skipping room-type verification when the hotel overview says "pets allowed"
- Continuing to pad a shortlist after the pet-paradox threshold fires
- Recommending a hotel where only C-tier sources support the pet claim without a ❓ flag
- Assuming Marriott / Hyatt brand pet policy applies at Autograph-collection properties without checking the specific property
- Missing the pet from the confirmation guest count in Phase 1 of rate-stay.md
</anti_patterns>
