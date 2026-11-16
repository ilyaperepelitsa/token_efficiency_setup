# Measured observations

**Context size decreased. Overall efficiency improvement is not established.**

These are anonymized observations from two real, concurrent coding sessions on
one machine. They are an uncontrolled before/after sample, not a benchmark or a
claim that this toolkit saves a fixed percentage of tokens or subscription usage.

## Usage across both sessions

Two equal **15-minute windows** were compared, one before and one after execution
changes. The windows were separated by an intervention period; they were not
adjacent. Main agents and their workers are included. Streaming duplicates were
deduplicated and synthetic quota notices excluded from model response counts.

| Recorded metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| New input + cache writes | 4.43M | 4.21M | −4.9% |
| Cached input | 73.25M | 47.17M | −35.6% |
| Output | 223.59k | 303.46k | **+35.7%** |
| Model responses | 243 | 267 | **+9.9%** |

The cached-input reduction was real in these records. Output and response count
increased. Different token categories have different prices and quota treatment;
these numbers do **not** establish a 35.6% reduction in cost or allowance use.

The workloads were not matched, accepted-work comparison was unavailable, and
worker transitions were still in progress. It is possible that the later window
contained more useful work, more overhead, or both. This sample cannot distinguish
those explanations and cannot attribute the change to one tool.

## Lead context snapshots

The latest full input sizes recorded in those same windows were:

| Anonymous session | Before | After | Change |
| --- | ---: | ---: | ---: |
| A | 200,016 | 120,766 | −39.6% |
| B | 265,029 | 113,382 | −57.2% |

These are input-token snapshots for the main agents, **not fleet totals** and not
the size of the generated compaction summary. Older workers still held much larger
contexts. Reducing a lead's context alone did not remove that worker overhead.

## What changed, and what remains unproved

Observed changes included earlier native compaction, shorter continuation briefs,
some fresh worker contexts, smaller inline command output, and more explicit
source-navigation guidance. Several changes happened together, so this is not a
controlled test of any single mechanism.

| Mechanism | Evidence available | Limit |
| --- | --- | --- |
| Context compaction and handoffs | Smaller main input snapshots above | No isolated effect or accepted-work improvement proved |
| Serena adoption | Real symbol calls were observed after explicit guidance | Installation initially did not produce consistent use; token savings not isolated |
| Periodic review reminder | Actual delivery observed in both active main sessions | Delivery does not guarantee the agent makes or verifies a useful correction |
| Compact report | Real default output measured at 500 characters; size-cap tests pass | Bounds reminder text, not internal model reasoning or total review cost |
| Review adapter accounting | A real window matched an independent local reader's five usage buckets | Matching readers do not prove complete provider/account history |

The rollout was imperfect: existing large worker contexts persisted, broad reads
continued, and usage reviews sometimes recorded a plan without verifying adoption.
Those failures motivated explicit tool-access checks, safe handoff follow-through,
and small periodic comparisons. The existence of those rules is not evidence that
all agents now follow them or that future work is cheaper.

## Provenance and anonymization

The [exact aggregate data](../data/anonymized-observations.json) contains only
numeric totals, anonymous labels and measurement-limit flags. A strict allowlist
validator checks its schema. Project names, programming languages, model names,
task details, calendar timestamps, machine paths, session identifiers, worker
names and source text are intentionally absent. The numeric totals were retained;
they were not replaced by synthetic success claims.

Raw transcripts and the private source-to-label mapping are **not published**.
The full local history was not re-audited for publication. This means an outsider
can reproduce the arithmetic and test the adapter, but cannot independently verify
these raw-session observations from this repository alone. The automated tests
continue to use synthetic fixtures, not private session fragments.

For a stronger evaluation, measure comparable accepted batches, completion time,
resource occupancy and regressions across repeated, matched runs. Report negative
results and differences in model/settings/workload before claiming causal savings.
