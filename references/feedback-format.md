## Contents
- File location
- Stay entry format — H3-block template, Disconfirm must-fill, rating decimals
- Rating scale (1–10, aligned with Booking.com)
- Learning signals
- booking-history.md structure

<overview>
Format for recording hotel stay reviews. Booking-history is the key file for system learning.
</overview>

<file_location>
`{skill}/data/booking-history.md`
</file_location>

<entry_format>
## Stay entry format

New stays use a Peak/End/Disconfirm/Return H3-block, appended to the `## Stays` section of booking-history.md. Field LABELS stay in English (structural anchors); example content is shown in the user's request language.

```markdown
### {Hotel Name} — {City}, {YYYY-MM-DD} — {Rating}/10

- **Peak:** {best moment of the stay, concretely — ideally with a specific detail}
- **End:** {how it felt at checkout, last impression}
- **Disconfirm:** {what did NOT work / what surprised negatively — must-fill, never empty}
- **Return:** {would you return? under what conditions? one line}

Room: {type, view, floor}
Price: {EUR/night, total}
Occasion: {city-break | ski | beach | anniversary | concert | new-country-exploration}
Pet: {true | false}
Notes: {1-2 lines of context — weather, who was there, special events}
```

**Disconfirm is must-fill.** Empty Disconfirm = lazy capture. If truly nothing failed, write the smallest friction observed (e.g., "slow elevator", "WiFi password didn't work on first try"). The asymmetric question surfaces signal the brain otherwise suppresses; collapsing it to "—" defeats the protocol.

**Probe-once enforcement:** if the user gives an elliptical answer ("nothing", "all perfect", "—"), `workflows/rate-stay.md` Step 2.1.5 mandates a single asymmetric probe. Only write `Disconfirm: — (user insists nothing failed after probe)` if the user explicitly insists after the probe — never on a first-pass shrug.

### Rating decimals

| Range | Format |
|---|---|
| 9.0+ | one decimal required (9.0, 9.1, …, 9.7, 9.9, 10.0) — top-tier discrimination matters |
| 6.0–8.5 | integers OR .5 increments only (6.0, 6.5, 7.0, 7.5, 8.0, 8.5) |
| ≤5.9 | integers only |

**Note: 8.6–8.9 is invalid by design** — rounds up to 9.0 if the stay genuinely warrants .X granularity, down to 8.5 if not. This forces the rater to commit: was this strong enough to enter the top tier?
</entry_format>

<rating_scale>
## Rating Scale (1-10, aligned with Booking.com)

| Rating | Meaning | Action |
|---|---|---|
| **9-10** | Legend — reference hotel, would bring friends, return | Add to taste-profile TOP or Strong |
| **7-8** | Strong — great stay, will consider again | Note patterns |
| **5-6** | Average — functional, nothing memorable | Neutral |
| **3-4** | Disappointing — expected more | Record reason, avoid pattern |
| **1-2** | Fail — would actively warn others | Add to anti-patterns |
</rating_scale>

<signals>
## Learning Signals

When recording each review, extract:

### Positive signals (from 8-10):
- Which words: "beautiful building", "renovation", "compact", "personal", "design"
- Architecture: historic? modern? renovated?
- Size: how many rooms? Under 60?
- Collection: which one?
- Location: neighborhood character
- Special: bathroom? lobby? rooftop? pool?

### Negative signals (from 1-4):
- Which words: "impersonal", "chain-feel", "outdated", "noisy", "overpriced"
- Size: too large? Too many rooms?
- What specifically failed: room? service? location? design?
- Pattern: does this match known anti-patterns?

### Meta-signals:
- Collection vs rating: SLH avg X/10, Design Hotels avg Y/10
- City vs rating: which city has better hit rate?
- Price vs rating: does spending more correlate with satisfaction?
- Room count vs rating: does compact really correlate with higher ratings?
</signals>

<file_structure>
## booking-history.md Structure

```markdown
# Booking History

*Last analysis: YYYY-MM-DD (N entries)*

---

## Stays

### {Hotel Name} — {City}, {YYYY-MM-DD} — {Rating}/10
- **Peak:** ...
- **End:** ...
- **Disconfirm:** ...
- **Return:** ...

Room: ...
Price: ...
Occasion: ...
Pet: ...
Notes: ...

### {Hotel Name} — {City}, {YYYY-MM-DD} — {Rating}/10
...

---

## Statistics (updated on /hotel learn)

- Total stays: N
- Average rating: X.X
- Best city: {city} (avg Y.Y)
- Best collection: {collection} (avg Z.Z)
```
</file_structure>
