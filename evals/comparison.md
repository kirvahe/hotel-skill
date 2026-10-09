# With-skill vs without-skill comparison — protocol

This protocol decides whether `/hotel` beats Claude without the skill on the same request. It holds only the method. The chosen cities, their fixed answers, every output and the verdict live in the user's private data folder, never in this repository.

## Contents
- Arms
- Cities and fixed answers
- Running each arm
- Normalization and blinding
- Metrics
- Records

## Arms

- **Without the skill:** Claude in the user's normal environment (memory and rules loaded), told not to use `/hotel`. The baseline is captured before the find-hotel rewrite.
- **With the skill:** the rebuilt `/hotel`, after the rewrite, in the same environment.

## Cities and fixed answers

Three cities, each chosen for one property:

| Slot | Property |
|---|---|
| City A | The user already has rated stays there |
| City B | A trip with the dog |
| City C | Few known sources (no international lists, little Reddit) |

Each city has fixed answers to the skill's opening question: dates, budget per night, and whether the dog travels. Both arms receive the same answers. The values are recorded in the private data folder before any run.

## Running each arm

- The request text is the same for both arms and states the city, dates, budget and dog answer, so no clarifying question is needed.
- When the skill asks its opening question, an operator agent answers with the fixed answers.
- At the shortlist checkpoint the operator agent keeps every shortlisted hotel. The user never sees a shortlist or a candidate before judging.
- Wall-clock time per run is recorded for the separate "clearly faster than the old skill" criterion. It is not a judging metric.

## Normalization and blinding

- A fresh agent that saw neither run rewrites both final answers into one neutral layout: hotel name, area, price, links, a short reason. It removes skill-specific markers (flags, section names, labels) that would reveal the arm.
- Each city's pair is labelled A and B at random. The mapping is sealed in the private folder until the user has judged all three cities.

## Metrics

Fixed before the rewrite, in this order of importance:

1. **Preference:** for each city, the user picks A, B or "tie": the answer they would book from.
2. **Strike count:** in each answer, the number of options the user marks as not fitting.
3. **Unbookable count:** a separate fresh agent checks, after both runs, how many options in each answer cannot actually be booked on the dates (booked out or closed), using the hotels' own websites.

The skill wins when the user prefers it in the majority of cities. Metrics 2 and 3 explain the verdict and are reported next to it.

## Records

Private folder per comparison: request texts, fixed answers, both raw outputs, both normalized outputs, the sealed mapping, the user's verdicts, the strike and unbookable counts, and run times.
