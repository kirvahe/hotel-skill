# Smoke-Test Eval Prompts

Five manual smoke-test prompts to run in chat after a refactor. Type each prompt into a fresh `/hotel` chat and check outputs against the verification points. Together they cover every workflow: find-hotel (cold start and continuation), rate-stay (Phase 1 and Phase 2), and learn.

All hotels, people, addresses and confirmation numbers below are fictional. Dates are in October 2027; once that has passed, move every date forward by whole years and update the weekdays.

## Setup — synthetic data only

Evals 3–5 write to `booking-history.md`, `feedback/` and `trips/`. **Never run them against your own data.** Back up `~/.claude/skills/hotel/data/`, run the evals on a fresh install (`./install.sh` seeds the templates), then restore your backup.

**Fixture A — `data/taste-profile.md`** (edit the seeded template; leave every other section as is):

- `## Who`: Home city: Lyon. Pet by default: yes (miniature poodle, 4 kg). Budget per night: EUR 180–320. Loyalty programs: Booking.com Genius Level 2.
- Add a `## Pet` section with one line: `Miniature poodle, 4 kg — travels on most trips.` (The workflows read the pet from `## Pet`.)
- `## TOP-3 reference hotels`:

| Hotel | City | Rating | Why it anchors |
|---|---|---|---|
| Palazzo Esempio | Bologna | 9.6 | 18th-century palazzo, 26 rooms, owner-run |
| Hotel Beispielhaus | Vienna | 8.0 | design inside a historic shell, 38 rooms |
| Casa Ejemplo | Valencia | 7.0 | affordable cool, 21 rooms, great neighborhood |

**Fixture B — `data/cities/porto.md`** (for Eval 2):

```markdown
# Porto

Updated: 2027-03-02

## Searched
2027-03-02 R1: Porto city-break, EUR 250 → trips/porto-2027-04/hotels-shortlist.md

## Recommended
| Name | Type | Area | Rating | Notes |
|---|---|---|---|---|
| Hotel Exemplo Ribeira | boutique | Ribeira | — | R1 pick |
| Casa Teste Bonfim | design | Bonfim | — | R1 pick |

## Mentioned section (researched, not selected)
| Name | Type | Source/Context | Date |
|---|---|---|---|
| Quinta Amostra Foz | heritage | R1 research — far from the centre | 2027-03-02 |

## Excluded (with reason)
- Hotel Fictício Aliados — "lobby like an airport lounge" (companion)
```

**Fixture C — `data/feedback/feedback_porto_hotels.md`** (for Evals 2 and 4):

```markdown
---
city: Porto
slug: porto
---

# Porto — Hotel Feedback

## Blacklist

| Hotel | Reason | Source |
|---|---|---|
| Hotel Fictício Aliados | "lobby like an airport lounge" | user feedback, 2027-03 |

## Positive reference

| Hotel | Reason | Source |
|---|---|---|
```

## Eval 1 — Cold Start + Festivo + Inferred State

**Prompt:**
```
/hotel Seville 10–13 Oct 2027, up to EUR 300/night
```

**Verifications:**
1. No `cities/seville.md` exists → cold start, no "Continuation detected" line
2. One declarative echo line, no question: `Proceeding as city-break trip with pet=true. Correct me before Step 4 if wrong.`
3. Festivo warning for Día de la Hispanidad (12 Oct) appears before any hotel card
4. Top-3 finalists carry an operational-verification flag (✓ / ⚠ / ❌); the summary table has a `Status` column
5. File mode: the full list (5 main + 2 premium) is saved to `~/.claude/skills/hotel/data/trips/seville-2027-10/hotels-shortlist.md`; the terminal shows only the top-3 plus the file pointer
6. Every hotel has room count, collection flag, Booking.com + Google Maps links, a "Why you" line, a "Vibe:" line naming one of the Fixture A anchors, and pet notation (✅ / ⚠️ / ❓ / ❌); the Overview line starts with "City-break pick in Seville"
7. `cities/seville.md` is created with Searched / Recommended / Mentioned section / Excluded; the response ends with a clickable absolute-path link to the saved file

If the pet-paradox warning fires (<20% pet-friendly after 5 candidates), the skill stops and asks. That is correct behavior: answer "(c) fewer options" and keep scoring.

**Failure modes to catch:**
- Skill asks "do you need pet-friendly?" or "what's the occasion?" → pet baseline / occasion inference not applied
- No festivo warning → Step 2e skipped
- A 6+ row table printed inline in the terminal → file-mode rule ignored
- No `Status` column or verification footnote → Step 5 skipped
- Chain hotel, apartment or B&B in the list → Step 4 filters not applied
- Room count, renovation year or owner name with no source and no ❓ → `<no_fabrication>` broken

## Eval 2 — Multi-Round Continuation + Blacklist

**Prompt (requires Fixtures B and C):**
```
/hotel Porto again for 15–18 Oct 2027, EUR 250 — last round felt too touristy, want somewhere more residential
```

**Verifications:**
1. Continuation echo with exact counts: `Continuation detected for Porto: 2 recommended before, 1 mentioned candidates to re-evaluate, 1 excluded.`
2. Hotel Exemplo Ribeira, Casa Teste Bonfim (prior Recommended) and Hotel Fictício Aliados (Excluded + blacklisted) do not appear in the new shortlist
3. Quinta Amostra Foz (Mentioned; fictional, so no sources exist) is re-evaluated explicitly: it stays in Mentioned with a note or moves to Excluded with a reason. It is never promoted with invented specifics
4. `cities/porto.md` is updated: the prior `## Recommended` is archived under `## Round 1 — {outcome}` with an `Occasion: …, Pet: …` line, `## Criteria changes` gains `R1→R2: occasion city-break→city-break, pet true→true, …`, and a fresh `## Recommended` table is written
5. No Spain festivo warning (Portugal is out of scope)
6. Output contract holds as in Eval 1 (links, room counts, `Status` column, file link last)

**Failure modes to catch:**
- Prior picks reappear → Step 0 hard-exclude broken
- Quinta Amostra Foz promoted with a room count or amenities → fabrication
- A Mentioned candidate disappears from the cache with no reason → "never silently re-drop" broken
- No Round 1 archive or no Criteria changes line → continuation-aware write skipped
- Festivo warning for a Portugal trip → Step 2e scope ignored

## Eval 3 — Booking Confirmation (rate-stay Phase 1)

**Prompt:**
```
booked this, confirmation email below

Casa Teste Bonfim, Rua Exemplo 123, 4000-000 Porto, Portugal
Booked by: Alex Example
Confirmation number: 0000000000 · PIN: 0000
Check-in: Friday 15 October 2027 (from 15:00)
Check-out: Monday 18 October 2027 (until 12:00)
Room: Classic Double Room 🚷 Pets not allowed
Guests: 2 adults
Price: EUR 630 (3 nights) + EUR 18 city tax = EUR 648
Prepayment: none — you pay at the property
Free cancellation until Tuesday 12 October 2027, 23:59 (Lisbon time). After that: EUR 210.
Changing the dates of your stay is not possible.
Special request: quiet room on a high floor — the property will try to accommodate.
Parking: on-site, EUR 20 per day, reservation needed.
```

**Verifications:**
1. Routed to Phase 1 without asking (booked + artifact, no rating language); no rating requested, `taste-profile.md` untouched
2. Provisional block `### Casa Teste Bonfim — Porto, 2027-10-15 — Upcoming` appended under `## Stays` with placeholder Peak / End / Disconfirm / Return and `Notes: **Upcoming.** Conf# …`
3. Safety checklist printed with all 7 items answered; flags raised for: pet missing from guest count, 🚷 on the booked room type, date change not possible, special request unconfirmed ("will try"); parking reservation appears as a TODO (conditional on driving is fine — the profile does not say)
4. Free-cancel deadline stated explicitly (Tuesday, 12 Oct 2027, 23:59 Lisbon time) with the EUR 210 fee; the dated action plan ends with it
5. English call script (Portugal is "everywhere else") with placeholders pre-filled (confirmation number, check-in date, Alex Example, room type, miniature poodle, 4 kg, deadline); the full PIN is not echoed in chat
6. `booking-details.md` saved under `~/.claude/skills/hotel/data/trips/porto-2027-10/`; the response gives both file paths

**Failure modes to catch:**
- Skill asks "booking or stay?" → routing ignored the artifact signal
- Skill asks for a rating or Peak/End → Phase 1 and Phase 2 mixed
- Any checklist item missing → mandatory checklist skipped
- "will try" treated as a confirmed request
- Spanish script used for Portugal, or placeholders left unfilled

## Eval 4 — Post-Stay Review (rate-stay Phase 2)

**Prompt (after Eval 3):**
```
stayed at Casa Teste Bonfim in Porto, 4/10. Peak: the tiled staircase in the morning light. End: checkout took 25 minutes, nobody said goodbye. Disconfirm: nothing really. Return: no.
```

When the skill probes Disconfirm, reply: `the lobby felt soulless, like a chain`

**Verifications:**
1. Routed to Phase 2; Peak, End and Return are not re-asked
2. Exactly one asymmetric Disconfirm probe ("Smallest friction — …"); "nothing really" is not written as `—`
3. Rating kept as the integer 4 (≤5.9 → integers only)
4. The Eval 3 `Upcoming` block is updated in place: the header ends `— 4/10`, the "Upcoming." prefix is gone from Notes, and there is no duplicate block
5. A Blacklist row is appended to the existing `feedback/feedback_porto_hotels.md` (Hotel Fictício Aliados row kept): the reason paraphrases the user's words, source `user feedback, {YYYY-MM}`
6. No Positive-reference row; the 1–4 anti-pattern prompt appears ("This confirms the pattern: … Should I update anti-patterns in taste-profile?")

**Failure modes to catch:**
- A new H3 block next to the Upcoming one → in-place update broken
- `Disconfirm: —` written without a probe → must-fill enforcement broken
- Blacklist reason invented, or the feedback file recreated and the existing row lost
- `taste-profile.md` edited without asking

## Eval 5 — Pattern Analysis (learn)

**Fixture D — append to `## Stays` in `data/booking-history.md`:**

```markdown
### Palazzo Esempio — Bologna, 2025-05-02 — 9.6/10
- **Peak:** breakfast under the frescoed ceiling
- **End:** the owner walked us to the taxi
- **Disconfirm:** weak shower pressure on day two
- **Return:** yes mandatory

Room: Junior suite, courtyard view
Price: EUR 340/night
Occasion: anniversary
Pet: true
Notes: synthetic fixture

### Hotel Beispielhaus — Vienna, 2025-11-14 — 8.0/10
- **Peak:** concrete-and-oak lobby bar at night
- **End:** smooth, luggage held until evening
- **Disconfirm:** street noise with the window open
- **Return:** yes situational — winter city-break

Room: Studio, courtyard
Price: EUR 260/night
Occasion: city-break
Pet: true
Notes: synthetic fixture

### Casa Ejemplo — Valencia, 2026-03-20 — 7.0/10
- **Peak:** rooftop at sunset
- **End:** checkout fine, nothing memorable
- **Disconfirm:** tiny bathroom
- **Return:** maybe

Room: Double, street view
Price: EUR 150/night
Occasion: city-break
Pet: false
Notes: synthetic fixture

### Hotel Probe Lago — Como, 2026-08-14 — Upcoming
- **Peak:** — (will fill after stay)
- **End:** —
- **Disconfirm:** —
- **Return:** —

Room: Lake View Double
Price: EUR 900 (3 nights)
Occasion: city-break
Pet: true
Notes: **Upcoming.** Conf# 0000000001. Check-out 2026-08-17. Cancel-free until Tue, 11 Aug 2026, 23:59 local.
```

**Prompt:**
```
/hotel learn
```

**Verifications:**
1. A stale Phase 1 warning at the top lists Hotel Probe Lago — Como, checked out 2026-08-17, and suggests `/hotel rate-stay`
2. The Upcoming entry is excluded from all statistics; averages use actual decimals (7.15 with the Eval 4 stay included, 8.2 without it)
3. With fewer than 5 reviewed stays the report flags the sample as too small and keeps conclusions tentative
4. Proposals follow the "Proposed Changes to taste-profile" structure; the skill waits for confirmation and edits nothing before you answer
5. Final report lists stays analyzed, average rating, best and worst city

**Failure modes to catch:**
- Upcoming entry counted in averages → entry reader skip broken
- `taste-profile.md` edited before confirmation → Step 5 gate broken
- A confident "success formula" from 3–4 stays → small-sample guard ignored

## How to run

For each eval:

1. Open a fresh chat window (clean context). Evals 3 → 4 → 5 build on each other's files, not on chat history
2. Type the prompt
3. Read output once, scoring the verifications
4. Note any failure mode triggered
5. If 2+ failures across the five evals, the change introduced a regression — investigate

These cover the main code paths: cold-start search, multi-round continuation, booking confirmation, post-stay review, and pattern analysis. Smoke test, not proof of correctness — add new evals only when a specific bug needs a regression check.
