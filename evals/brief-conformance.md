# Research brief conformance — protocol

This protocol checks that each brief in `references/briefs/`, run by a fresh agent, produces what the pipeline needs. It holds only the method. The fixture city, run folders, transcripts and results live in the user's private data folder, never in this repository.

## Contents
- When and who
- Fixture city and setup
- Runs
- Reading tool logs
- Checks
- Records and pass rule

## When and who

- Run after `bin/engine_reader.py` and `bin/reddit_fetch.py` pass their own tests, and before the user approves the caps: the counts recorded here go with the cap proposal.
- The runner is a fresh agent that did not write the briefs. It spawns one agent per brief, on Opus, and reviews what they did. It does not do the research itself.

## Fixture city and setup

1. **City.** A real city in a country whose language is not English, so the A-before-B order can be checked. It must not appear in the user's data folder (no city cache, trip, stay or feedback file for it). Record the choice in the private folder.
2. **Trip.** Future dates, two guests, a mid-range budget. The family runs use `--dog no`; the final-check run uses a separate run folder with `--dog yes`.
3. **Run folders.** One temporary data folder per run (two runs in the same city and month would share a run folder):
   ```bash
   python3 bin/ledger.py init --data {tmp_data_R1} --city "{fixture city}" --check-in {date} --check-out {date} --guests 2 --budget-max {eur} --dog no
   ```
   The command prints the run folder (`{run_dir}`).
4. **Prompt values.** Every placeholder in the contract's Inputs table, with `{skill}` = this repository's root and `{languages}` named explicitly. `{taste_summary}` is synthetic, for example "small hotels with character in historic buildings, lively neighbourhoods, personal service; no large chains". The caps, the Firecrawl credit floor and the reader's page timeout and give-up values are the provisional values under test; record them.
5. **Agent prompt.** The prompt values, then: "Read `{skill}/references/briefs/research-contract.md` and `{skill}/references/briefs/{brief}.md` in full, then do the task." Nothing else: no hints about the checks.
6. **Before spawning.** Record the Firecrawl balance with `mcp__firecrawl__firecrawl_credit_usage`, and `touch` a marker file in the scratchpad for the transcript lookup.

## Runs

| Run | Agents | Inputs |
|---|---|---|
| R1 cold | curated-press, reddit, booking-search, spawned in one message | `{source_map_slice}` = `none` |
| R2 warm | the same three, new run folder | each family's slice = the `source_map` from its R1 envelope file |
| R3 resolver | resolver, batch 1 | three R1 candidates, one of them a Booking-only find; `{dog}` = `true` with a synthetic `{dog_note}` |
| R4 final check | final-check, batch 1 | the R3 candidates with their official URLs; `{dog}` = `true` |

## Reading tool logs

Claude Code saves each subagent's transcript as `~/.claude/projects/{project}/{session}/subagents/agent-{id}.jsonl`. Find the new ones with `find ~/.claude/projects -path '*subagents*' -name 'agent-*.jsonl' -newer {marker}`, and match each to its agent by the first prompt line. List its tool calls in order:

```bash
python3 -I - "$TRANSCRIPT" <<'EOF'
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    content = (json.loads(line).get("message") or {}).get("content")
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            print(block["name"], json.dumps(block.get("input"), ensure_ascii=False)[:300])
EOF
```

A check that needs the tool log is "not verified" when no transcript is found, never "pass".

## Checks

| ID | Runs | Check | Pass when |
|---|---|---|---|
| C1 | all | Final message | It is only the envelope the contract defines: no candidate data |
| C2 | R1, R2 | Candidate file | `python3 bin/ledger.py validate {run_dir}/candidates-{family}.jsonl --kind candidate` prints `OK`, and the file has records unless the status is `failed` with a reason the transcript bears out |
| C3 | R1, R2 | Envelope file | `validate … --kind envelope` prints `OK`; its status matches the final message |
| C4 | R1, R2 | Language order | In the envelope file's `queries`, inside each block, every set-A query comes before the first set-B query and every B before the first C; the transcript's search calls show the same order |
| C5 | R1, R2 booking-search | Search calls only | The transcript has no `mcp__firecrawl__firecrawl_scrape`, `mcp__firecrawl__firecrawl_crawl`, `mcp__firecrawl__firecrawl_map`, `mcp__exa__web_fetch_exa` or `WebFetch` call, and no `scrapeOptions` in any `mcp__firecrawl__firecrawl_search` call |
| C6 | all | No Booking or Airbnb page, no browser | No page-read call or Bash command targets a booking.com or Airbnb host; no browser, screen-control or mail tool is called |
| C7 | R1, R2 reddit | Reddit read in full | Every Reddit mention URL is a permalink whose post ID was passed to `reddit_fetch.py tree` in the transcript |
| C8 | R1, R2 | Booking score from results | Every `booking_score` has `query` and `quote`; for three of them, the quoted text appears in that query's search result in the transcript |
| C9 | R1 | Cold-city source map | Each family's envelope file lists the outlets, subs or Booking queries it used in `source_map` |
| C10 | R2 | Warm-city slice | The cached outlets, subs or Booking queries are searched first; no query aims to find an outlet the slice lists; no `source_map` entry repeats a cached outlet, and each new one has `"new": true` |
| C11 | R1, R2 | Kind tags | Spot-check five records: a source describing an apartment, a villa or a whole house is not tagged `hotel` |
| C12 | R3 | Resolver output | Both validation commands in `resolver.md` print `OK`; every `closure` record quotes a page that states the closure; no booking engine is opened by any tool |
| C13 | R4 | Engines only through the reader | Every booking-engine read is a Bash call to `bin/engine_reader.py`; no page-read call targets an engine URL the reader reported; both validation commands in `final-check.md` print `OK` |

## Records and pass rule

Record in the private folder, per agent: status, records written, search calls, page reads, threads read, reader runs, wall time, the Firecrawl credits used (balance before and after), the transcript path, and each check as pass, fail or not verified with a one-line note.

The protocol passes when every check passes for every run. A "not verified" fails the protocol run: re-run with the transcript found. When a check fails, fix the brief, re-run only the affected agent, and record both runs.
