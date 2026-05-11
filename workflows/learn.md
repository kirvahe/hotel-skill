# Workflow: Analyze Preferences and Update Profile

<required_reading>
**Read BEFORE analysis:**
1. `~/.claude/skills/hotel/data/booking-history.md` — all bookings
2. `~/.claude/skills/hotel/data/taste-profile.md` — current profile
</required_reading>

<process>
## Step 1: Load All Data

Read:
- Booking history (all H3-block entries)
- Taste profile (current state)

### Pre-flight: stale-Upcoming scan

Before reading entries, scan the `## Stays` section for any H3-block whose rating slot reads `Upcoming` and whose check-out date is **>14 days in the past**. Emit a separate warning list at the top of the report:

```
⚠️ Stale Phase 1 entries (>14 days past check-out, never reviewed):
- {Hotel} — {City}, checked out {YYYY-MM-DD}
- ...
Suggest running /hotel rate-stay on each before this analysis pass.
```

These are Phase 1 confirmations that never received Phase 2 review. They are excluded from aggregation in Step 1 below.

### Entry reader

For each H3-block stay in booking-history.md:

- **Skip H3-block entries where the rating slot reads `Upcoming`** — these are provisional Phase 1 entries that never got Phase 2 review. Log a one-line note: `"Skipped N orphan Upcoming entries; consider /hotel rate-stay for these."`
- **Positive signals** from the `Peak` field — this is the single specific moment that defined the stay; weight higher than generic pros lists.
- **Negative signals** from `End` (if negative — read the wording, not just keywords) and from `Disconfirm`.
- **Return** field → repeat-intent signal: `yes mandatory` = strongest positive; `no` + low rating = blacklist candidate.
- **Occasion** field → per-occasion analysis (ski / beach / city-break / anniversary / concert / new-country-exploration hit rates).
- **Pet** field → pet-impact analysis (does pet-true correlate with lower ratings? which hotels handled pets well?).
- Rating is in the header line: `### {Name} — {City}, {YYYY-MM-DD} — {N.M}/10`. Use the actual decimal value, no rounding.

When a hotel appears more than once (e.g., a re-stay), treat them as separate data points.

Calculate basic statistics:
- Total stays
- Average rating (use actual decimal values, not rounded)
- Rating distribution (1-10)
- Distribution by city
- Distribution by type (boutique / design / palace / resort)
- Distribution by collection (SLH, Design Hotels, LHW, independent)
- Distribution by price range
- Per-occasion hit rate
- Pet-true vs pet-false rating delta

## Step 2: Identify High-Rating Patterns (8-10)

Analyze entries rated 8-10:

**What's common:**
- Hotel type (boutique? design? palace?)
- Size (how many rooms?)
- Collection membership
- Architecture / design (which words repeat in "Peak" fields?)
- Location / neighborhood
- Price range
- Occasion (do special occasions correlate with higher ratings?)
- End-moment quality (does positive end correlate with 8+?)
- Return-intent distribution among 8+ stays

**Success formula:**
"Hotels rated 8+ most often share: {pattern1} + {pattern2} + {pattern3}"

## Step 3: Identify Low-Rating Patterns (1-5)

Analyze entries rated 1-5:

**What's common:**
- Which words repeat in "Disconfirm" fields?
- Is there a hotel type that consistently fails?
- Cities where it fails more often?
- Price ranges that disappoint?
- Are negative End moments clustered in low-rating stays?
- "Return: no" + low rating = blacklist confirmation

**Failure formula:**
"Hotels rated 1-5 most often share: {anti-pattern1} + {anti-pattern2}"

**City analysis:**
- Which cities have consistently high/low hit rates?
- Update problematic cities list

## Step 4: Compare with Current Profile

Check if taste-profile matches reality:

| Profile claim | Supported by data? | Evidence |
|---|---|---|
| "Compact (up to 60 rooms)" | ? | Avg rooms for 8+ vs 1-5 |
| "Architecture is key" | ? | Architecture mentioned in 8+ vs 1-5 |
| "Collections = quality signal" | ? | Collection hotels avg rating |
| "{City} is problematic" | ? | {City} ratings distribution |
| ... | ... | ... |

Find discrepancies:
- What's in profile but data doesn't confirm?
- What data shows but profile doesn't reflect?

## Step 5: Propose Profile Updates

Formulate specific proposals:

```
## Proposed Changes to taste-profile

### Confirmed (strengthen)
- {What data confirms — can be made more specific}

### New Insights (add)
- {What data shows but profile doesn't have}

### Questionable (discuss)
- {What's in profile but data doesn't confirm}

### Update TOP/Strong
- Promote: {hotels deserving higher tier}
- Demote: {if any reference got a low re-rating}

### Update Anti-patterns
- Add: {new anti-patterns from data}

### City Hit Rates
- {City X}: Y% hit rate (8+/10)
- {City Y}: Z% hit rate
```

**Show to user and wait for confirmation before any changes.**

## Step 6: Apply Approved Changes

After confirmation:
1. Update taste-profile.md (Edit tool)
2. Add update date
3. If new TOP/Strong hotels added — update relevant sections
4. If anti-patterns updated — update relevant sections

## Step 7: Report

Show summary:
- Analyzed: N stays
- Average rating: X.X
- Best city: {city} (avg Y.Y)
- Worst city: {city} (avg Z.Z)
- Best type: {type} (avg Y.Y)
- Collection hit rate: {collection} = X%
- Profile changes: {list}
</process>

<anti_patterns>
Avoid:
- Changing profile without user confirmation
- Drawing conclusions from < 5 entries (too little data)
- Ignoring context (a low rating in a problematic city might be "problematic city", not "bad type")
- Removing from profile what user explicitly added (their preferences > statistics)
- Mixing Booking.com 1-10 scale with restaurant 1-5 scale
</anti_patterns>

<success_criteria>
Analysis complete when:
- [ ] All data loaded and tallied
- [ ] High and low rating patterns identified
- [ ] Comparison with current profile done
- [ ] City hit rates calculated
- [ ] Proposals shown to user
- [ ] Approved changes applied
- [ ] Report shown
</success_criteria>
