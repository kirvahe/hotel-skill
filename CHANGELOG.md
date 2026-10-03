# Changelog

## [v1.2] — 2026-10-03

Structural alignment with Anthropic's "Skill authoring best practices" guide. Triggers, rules, step order, output format, `install.sh` and `scripts/` are unchanged. User data is not migrated or modified.

### Added

- `evals/evals.md` — five manual smoke-test scenarios (find-hotel cold start, find-hotel multi-round continuation, rate-stay Phase 1, rate-stay Phase 2, learn) with synthetic fixtures. Not installed by `install.sh`.
- Table of contents at the top of `workflows/find-hotel.md`, `workflows/rate-stay.md`, `workflows/learn.md` and all five files in `references/`.

### Changed

- `SKILL.md` frontmatter `version` set to `1.2`.
- `SKILL.md` data layout now lists `cities/README.md`, `feedback/feedback_{city-slug}_hotels.md` and `trips/{city-slug}-{YYYY-MM}/`, which the workflows already read and write.
- `SKILL.md` reference index uses full `references/…` paths and states which workflow step reads each file. The workflow index uses full `workflows/…` paths and describes both rate-stay phases.
- `workflows/rate-stay.md` Step 2.4: "new-stays section" renamed to the `## Stays` section, matching the rest of the step.
- `ROADMAP.md`: planned features move from v1.2 to v1.3. `README.md`: roadmap reference and data-folder tree updated to match.

## [v1.1.1] — 2026-05-11

Adds automatic updates via a SessionStart hook. After running `./install.sh` once with this version, future releases install themselves silently every 24 hours — no terminal commands required. Skill content is identical to v1.1.

### Added

- `scripts/sync-hotel-skill.sh` — async sync script with 24h throttle. Maintains a persistent clone at `~/.claude/skills/hotel/.source/`, fast-forward merges from upstream, re-runs `./install.sh --non-interactive` when new commits arrive. Emits a one-line notification in Claude Code chat when an update is applied.
- `install.sh` `--non-interactive` flag — used by the sync script to install without prompts.
- `install.sh` `--uninstall-hook` flag — removes the SessionStart hook and the sync script, leaves skill files untouched.
- `install.sh` interactive prompt at end of install: `Enable auto-updates via SessionStart hook? [Y/n]` (default Yes). On Yes, the hook is added to `~/.claude/settings.json` via `jq` with a timestamped backup. On No, the JSON snippet is printed for manual addition.

### Migration (from v1.1)

- **Recommended**: re-run `./install.sh` and accept the auto-update prompt. From that point on, future versions install themselves on the next Claude Code session that's >24h since the last sync.
- **Opt out later**: run `./install.sh --uninstall-hook` (removes hook + sync script, leaves skill files intact).

## [v1.1] — 2026-05-11

First public release. Built on the internal v1.0 baseline; applied a 3-tier CE-upgrade transferring mature mechanisms from the `/restaurant` skill (search, persistence, visit protocol) and adding hotel-specific surfaces (occasion taxonomy, operational verification, festivo calendar, pet protocol as first-class parameter).

### Added

- **Multi-round persistence** — city cache (`data/cities/{city}.md`) preserves Searched / Recommended / Mentioned section / Excluded across sessions. Subsequent `/hotel` runs for the same city build on prior research instead of starting cold. Round-N archives and a `Criteria changes` log capture what shifted between rounds.
- **Occasion taxonomy** — six occasions (city-break / ski / beach / anniversary / concert / new-country-exploration) with per-occasion ranking modifiers and anti-patterns. Occasion is inferred from the request in Step 1 and composed into the candidate score.
- **Calibration anchors** — three-tier reference (your TOP-3 from `taste-profile.md`) acts as a rating-drift guard. Before a 9+ assignment the skill must answer "strictly better than the tier-8 anchor?".
- **Visit protocol** — `/hotel rate-stay` Phase 2 now captures Peak / End / Disconfirm / Return (replacing Pros / Cons). Decimal granularity required on 9.0+; the 8.6–8.9 band is invalid by design to force commitment into the top tier.
- **Operational verification** — Booking.com availability check + 6-month press scan run for top-3 finalists before output. Flags render as `✓` / `⚠` / `❌` in the summary table.
- **Multi-language Reddit** — regional sub queries (Euskara, Catalan, Italian, Turkish, Portuguese, Greek, Japanese) run alongside English to surface local-only gems.
- **Owner/architect interviews as A-tier source** — query templates for Monocle, Apartamento, Wallpaper*, Cereal, Openhouse in `references/search-sources.md`.
- **Booking-rating bias adjustment** — tourist-zone suppression, hidden-gem surfacing, family-business signal heuristics applied to aggregate Booking scores.
- **Pet-as-parameter** — pet-friendly is a boolean filter, not an occasion. Default `pet=true`; explicit "couple-only" or "trip without the pet" signals flip to `pet=false`.
- **Spain festivo + puente-risk check** — trips intersecting (±2 days) a maintained festivo table trigger a price-premium + cancellation-window warning before recommendation cards appear.
- **Two-phase rate-stay** — Phase 1 (booking confirmation) extracts confirmation artifact, runs a mandatory safety checklist (pet in guest count, room-type pet marker, free-cancel deadline, date-change restriction, prepayment, parking), and surfaces deadline-pinned TODOs. Phase 2 (post-stay review) replaces the Phase 1 placeholder block in place.

### Changed

- `references/format-guide.md` Overview line now requires occasion-tag + anchor reference.
- `workflows/rate-stay.md` Phase 2: a 4-question batch (Peak / End / Disconfirm / Return) replaces freeform Pros/Cons. Disconfirm has a must-fill enforcement with one asymmetric probe before accepting `—`.
- `workflows/learn.md`: H3-block reader for Peak/End/Disconfirm/Return entries. Stale Phase-1 `Upcoming` blocks (>14 days past check-out, never reviewed) are flagged at the top of the report and excluded from aggregation.
- `references/feedback-format.md`: H3-block template with Peak / End / Disconfirm / Return, decimal granularity rules, and the legacy-table transition note.
- `SKILL.md` routing table: explicit Phase 1 vs Phase 2 disambiguation via artifact-presence and tense.
- `references/search-sources.md`: A/B/C reliability tiers, multi-language Reddit block, owner-interview query templates.

### Internal CE-upgrade summary (for readers comparing to /restaurant)

- Three review checkpoints caught 21 issues before they multiplied (initial: 7, mid: 10, final: 4).
- All changes are additive — no breaking changes to v1.0 user data. Old 50+ entries are not migrated.
- Five compound learnings captured for reuse on the next recommendation skill: recommendation-skill maturity ladder, transfer mechanism vs. transfer rule, calibration anchor pattern, persistence layer as compound/one-off divider, output-language matching at skill-level vs. global.
