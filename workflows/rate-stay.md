# Workflow: Record a Stay — Phase 1 (confirmation) or Phase 2 (review)

## Contents
- Required reading (load before recording)
- Phase detection (pick one phase before doing anything else)
- Phase 1 — Booking confirmation: 1.1 read the artifact, 1.2 provisional booking-history entry, 1.3 safety checklist (mandatory), 1.4 write the artifact file, 1.5 action plan output
- Phase 2 — Post-stay review: 2.1 four-question batch, 2.1.5 Disconfirm probe, 2.2 determine rating, 2.3 learning signals, 2.4 write to booking-history, 2.5 blacklist auto-append, 2.6 positive-reference auto-append, 2.7 signals for profile update
- Anti-patterns
- Success criteria (per phase)

<required_reading>
**Read BEFORE recording:**
1. `references/feedback-format.md` — recording format and rating scale
2. `references/format-guide.md` — file-mode rule and `{city-slug}-{YYYY-MM}` folder convention
3. `{skill}/data/booking-history.md` — existing log
4. `{skill}/data/taste-profile.md` — for rating context
</required_reading>

<phase_detection>
## Phase detection — pick one before doing anything else

This workflow has two phases that share the same trigger keywords but do different work. Disambiguate by **artifact presence** and **tense**:

| Signal | Phase |
|---|---|
| User says "booked / reserved" **and** provides a confirmation artifact (PDF path, email text, screenshot path) **and** no "rating" or "stayed" language | **Phase 1: booking confirmation** |
| User says "stayed / rating / liked / didn't work / {N}/10" **or** talks in past tense about the actual stay | **Phase 2: post-stay review** |
| Ambiguous (e.g., "booked, liked it") — ask once: "Is this about a booking (just made) or about a stay (already happened)?" | ask and route |

Never run both phases in one turn. If the user later comes back with a review for a hotel that has a Phase 1 entry, Phase 2 **updates that entry in place** rather than creating a new one.
</phase_detection>

<phase_1_process>
## Phase 1 — Booking Confirmation

Triggered when the user just booked a hotel and hands you a confirmation artifact. Goal: extract everything useful, write a provisional booking-history entry, and **surface risks the user needs to act on before any cancellation deadline passes**.

### Step 1.1: Read the artifact

Use `Read` on the provided path (PDF, email text, screenshot). Extract:

- **Hotel name** (full, including collection suffix like "Autograph Collection")
- **Address** + phone + GPS if present
- **Confirmation number** and PIN (treat as sensitive — keep in the file, do not echo full PIN in chat)
- **Check-in / check-out** dates with times
- **Room type** — verbatim string from the confirmation
- **Guest count + names** — note if the pet is listed or not
- **Total price** breakdown (base + tax + fees)
- **Prepayment** requirement (none / partial / full)
- **Cancellation terms** — exact deadline (date + time + timezone) and fee after that
- **Date-change policy** — possible / not possible
- **Parking** cost and reservation requirement
- **Pet markers** — look for 🚷 or 🐕 icons next to the room type (Booking.com room-level pet signals); only relevant if a pet is set in `taste-profile.md`
- **Special requests** logged in the confirmation

### Step 1.2: Append to booking-history.md (provisional entry)

Append a provisional H3-block at the end of the `## Stays` section in `{skill}/data/booking-history.md`.

Use the H3-block template from `references/feedback-format.md`, but mark it provisional:

```markdown
### {Hotel Name} — {City}, {YYYY-MM-DD} — Upcoming

- **Peak:** — (will fill after stay)
- **End:** —
- **Disconfirm:** —
- **Return:** —

Room: {verbatim room type}
Price: EUR {total} ({breakdown})
Occasion: {city-break | anniversary | ski | …}
Pet: {true | false}
Notes: **Upcoming.** Conf# {number}. Cancel-free until {weekday, D Mon YYYY, HH:MM local}. {Other flags}
```

No rating in the header line — `Upcoming` instead. Phase 2 will replace the placeholder fields with real Peak/End/Disconfirm/Return and add the rating to the header.

### Step 1.3: Safety checklist (mandatory — run every time)

Work through every item. Do not skip. Print the result as a checklist in the response.

- [ ] **Pet in guest count?** If the user travels with a pet (per the `## Pet` section in `taste-profile.md`) and the confirmation says "2 adults" with no pet listed → **FLAG**. Action: user must call hotel to add pet to reservation.
- [ ] **Room-type pet marker?** If the confirmation shows 🚷 or "Pets not allowed" next to the booked room type even when the hotel is pet-friendly overall → **FLAG**. Use call script from `references/pet-search.md`.
- [ ] **Free cancellation deadline?** Calculate exact local date + time. State it explicitly: "Free cancel until {weekday}, {D Mon YYYY}, {HH:MM} local. After that: {fee} EUR penalty." Pin it as a deadline-bound TODO.
- [ ] **Date-change restriction?** If confirmation says "changing dates not possible" → **FLAG**. The only lever if plans shift is cancel + rebook.
- [ ] **Special requests confirmed or not?** A logged request is not the same as a confirmed one. If confirmation wording is "we will try" → flag as unconfirmed.
- [ ] **Prepayment status?** Full / partial / none. If partial or full → flag the amount already charged.
- [ ] **Parking reservation?** If the user drives and parking requires reservation → flag as TODO.

### Step 1.4: Write the artifact file

Save a human-readable summary to:

`{skill}/data/trips/{city-slug}-{YYYY-MM}/booking-details.md`

Where `{city-slug}` follows the convention from `references/format-guide.md` (lowercase, ASCII, hyphenated). Create the folder if it does not exist. Copy the original PDF / screenshot next to it as `booking-confirmation.{ext}`.

The booking-details.md file contains: the extraction table, the safety checklist output (with flags visible), the action plan, and any call scripts needed.

### Step 1.5: Action plan output

Respond in the terminal with:

1. Short confirmation that booking-history and booking-details were updated (file paths)
2. **Red flags** from the safety checklist, each with a deadline and the exact action
3. **Action plan** as dated TODO list ending with the free-cancel deadline — user can paste into a calendar or reminder
4. Any call script from `references/pet-search.md` if pet flag is unresolved (ES + EN templates with placeholders pre-filled)

Do **not** rate the stay. Do **not** add to taste-profile. Phase 1 is risk-surfacing, not retrospective.
</phase_1_process>

<phase_2_process>
## Phase 2 — Post-Stay Review

Triggered when the user has stayed at the hotel and is reporting how it went. Goal: capture the rating, extract learning signals, update feedback files, and suggest profile updates.

### Step 2.1: Gather information — 4-question batch (one block, not one by one)

Ask all four in a single batched message. Use the user's request language; English default below, mirror to the user's language when they write in something else.

```
Recording the stay. 4 questions in one block so the data becomes useful for future recommendations:

1. Peak moment: what was the best moment of the stay? (morning view from the room,
   breakfast, the bathroom, a specific service detail — what stayed in memory)

2. End: how did checkout feel? (last impression — reception at checkout,
   last-day breakfast, how you left)

3. Disconfirm: what did NOT work or what negatively surprised you?
   (must-fill — if it feels like "nothing", name the smallest friction)

4. Return: would you return? under what conditions? one line
   (yes mandatory / yes situational + context / maybe / no)
```

**Also gather, if not volunteered (don't re-ask if user already wrote it):** hotel name, city, rating (1–10), room type, price/night, occasion, pet yes/no, collection membership (SLH / Design Hotels / LHW / Autograph / independent), number of rooms.

If the user gives a detailed review — don't re-ask, extract Peak/End/Disconfirm/Return from their text.

### Step 2.1.5: Disconfirm probe (must-fill enforcement)

If the user's Disconfirm response is empty, "—", "nothing", "all perfect", or similarly elliptical: probe **once** with an asymmetric prompt (in the user's language; English default below):

> Smallest friction — elevator, WiFi, breakfast queue, anything? Name one detail.

Only write `Disconfirm: —` if the user **explicitly insists** after the probe. In that case, mark it as deliberate acknowledgment rather than lazy capture:

```
Disconfirm: — (user insists nothing failed after probe)
```

This distinguishes "asked twice, genuinely nothing" from "user shrugged on first ask and I let it go".

### Step 2.2: Determine rating

Scale (aligned with Booking.com 1–10):

- **9–10** — "Legend" — would return, recommend to friends, reference hotel
- **7–8** — Strong — great stay, will consider again
- **5–6** — Average — functional, no memorable experience
- **3–4** — Disappointing — expected more, wouldn't return
- **1–2** — Fail — would actively warn others

**Decimal granularity** (per `references/feedback-format.md`):
- 9.0+ → one decimal required (9.0, 9.1, …, 9.7, 9.9, 10.0) — top-tier discrimination matters
- 6.0–8.5 → integers OR .5 increments only (6.0, 6.5, 7.0, 7.5, 8.0, 8.5)
- ≤5.9 → integers only

**Note: 8.6–8.9 is invalid by design** — rounds up to 9.0 if the stay genuinely warrants .X granularity, down to 8.5 if not. This forces the rater to commit: was this strong enough to enter the top tier?

If user doesn't give a numeric rating — infer from context and **confirm explicitly**:
"Sounds like a 7.5 — strong stay but not legend-level. Correct?"

Anchor the rating against the user's calibration anchors in `taste-profile.md` — before assigning 9+, the question "strictly better than {your-anchor-8}?" must be explicit (see `references/format-guide.md` `## Calibration Anchors`).

### Step 2.3: Extract learning signals

From the 4-question batch, determine:
- **Peak signal** (positive): which dimension drove the high moment? architecture? room? bathroom? service? location? lobby? rooftop? view?
- **End signal**: was the closing experience positive (peak-end harmony) or negative (drag on memory)?
- **Disconfirm signal** (negative): noisy? outdated? impersonal? bad neighborhood? overpriced? reception attitude?
- **Return intent**: yes/maybe/no — a strong "no" + low rating = blacklist candidate
- **Pattern match:** which taste-profile criteria does this confirm or challenge?
- **Hotel type:** boutique / design / palace / resort / city
- **Size:** number of rooms
- **Collection:** LHW / SLH / Design Hotels / Autograph / independent
- **Booking source:** Booking.com / direct / other

### Step 2.4: Write to booking-history

Write a new H3-block at the end of the `## Stays` section in booking-history.md. Use the H3-block template from `references/feedback-format.md`.

If this hotel has a Phase 1 "Upcoming" H3-block → **update that block in place**: replace the placeholder Peak/End/Disconfirm/Return values with the real ones, swap "Upcoming" in the header for the rating, and trim the "Upcoming." prefix from Notes. Do not create a duplicate block.

**Matching key:** match by `Hotel name + check-in date (YYYY-MM-DD from header line)`. If the same hotel was stayed twice with different check-in dates, each gets a separate H3-block — never collapse two stays into one.

Otherwise, append a fresh H3-block at the end of the `## Stays` section.

### Step 2.5: Blacklist auto-append

If any of these fire, append the hotel to the city-specific feedback file:

- Rating ≤ 4
- Negative keywords (English defaults; the user's localized negatives can be added to `taste-profile.md` `## Negative keywords`): "soulless", "generic", "chain feel", "didn't work", "disappointing"
- User explicitly asks to "never recommend this again"

**Target file:** `{skill}/data/feedback/feedback_{city-slug}_hotels.md`. Create the `feedback/` directory if it does not exist.

Where `{city-slug}` here uses the **feedback-file convention**, which is *compact* and differs from the trip-folder convention in `format-guide.md`:

- Trip folder (`data/trips/{city-slug}-{YYYY-MM}/`) → full hyphenated slug: `Málaga` → `malaga`, `Nîmes` → `nimes`
- Feedback file (`feedback_{city-slug}_hotels.md`) → compact abbreviation: multi-word cities get a short tag (e.g. two-letter initials for two-word names), single-word cities keep their full lowercase name

The compact form exists because feedback files are flat and greppable — shorter names reduce noise. Single-word cities keep their full name; multi-word cities get an abbreviation **chosen on first creation and locked in** (check existing files in the feedback directory before inventing a new one).

**If the file does not exist:** create it with this minimal frontmatter:

```markdown
---
city: {City name}
slug: {slug used in filename}
---

# {City} — Hotel Feedback

## Blacklist

| Hotel | Reason | Source |
|---|---|---|

## Positive reference

| Hotel | Reason | Source |
|---|---|---|
```

Then append the row.

**If the file exists:** append the row to the existing Blacklist table.

**Row format:**
```
| {Hotel full name} | {one-line reason from user text, keep original language for flavor} | user feedback, {YYYY-MM} |
```

Never invent a reason — paraphrase the user's actual words. If the user gave no reason and the rating is ≤4, ask before appending: "What's the main reason for the low rating? This will go into the {city} blacklist for future searches."

### Step 2.6: Positive-reference auto-append

If rating is 8+ and the hotel carries genuine character markers (independent / SLH / LHW / Design Hotels / Autograph / historic-building conversion), append to the **Positive reference** table in the same `feedback_{city-slug}_hotels.md` file. Same row format, same create-or-append logic.

### Step 2.7: Signals for profile update

If **5+ new Phase-2 entries** since last analysis — suggest:
"You have 5+ new reviews. Run `/hotel learn` to update your profile?"

If rating is 9–10 — suggest:
"This is a 9–10 — add to TOP or Strong in taste-profile?"

If rating is 1–4 — note the anti-pattern:
"This confirms the pattern: {anti-pattern}. Should I update anti-patterns in taste-profile?"
</phase_2_process>

<anti_patterns>
Avoid:
- Running both phases in one turn (always disambiguate first via `<phase_detection>`)
- Asking questions one by one (gather everything in 1 message)
- Re-asking what the user already told you
- Recording a rating without confirming it with the user
- Using the restaurant 1–5 scale (hotels use 1–10 to match Booking.com)
- Silently dropping red flags from the Phase 1 safety checklist — always surface them
- Inventing a blacklist reason — always paraphrase the user's own words
- Treating "will try" special requests as confirmed
</anti_patterns>

<success_criteria>
## Phase 1 success
- [ ] Artifact read and all fields extracted
- [ ] booking-history.md updated with provisional "Upcoming" entry
- [ ] Safety checklist run, every item answered (not skipped)
- [ ] Red flags surfaced with deadline-pinned TODOs
- [ ] booking-details.md + artifact copy saved under `{skill}/data/trips/{city-slug}-{YYYY-MM}/`
- [ ] Cancellation deadline stated explicitly in local date + time + timezone
- [ ] Action plan delivered in terminal response

## Phase 2 success
- [ ] Rating confirmed by user (1–10 scale)
- [ ] Entry added to booking-history.md (or in-place update of Phase 1 row)
- [ ] Learning signals extracted
- [ ] Blacklist auto-append fired on rating ≤4 OR negative keywords
- [ ] Positive-reference auto-append fired on rating ≥8 with character markers
- [ ] /hotel learn suggested if 5+ new entries
- [ ] Profile update suggested if 9–10 or 1–4 rating
</success_criteria>
