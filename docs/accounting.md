# Accounting and measurement limits

Each comparison uses adjacent, half-open windows: `[now-30m, now-15m)` and
`[now-15m, now)`. It is session-scoped, not an account ledger. Local history may
omit deleted, remote, background or interrupted usage.

| Field | Meaning |
| --- | --- |
| new | Input excluding cache reads and separately reported writes |
| write | Input written to the prompt cache |
| cached | Input read from the prompt cache |
| output | Recorded output, already including reasoning where the provider includes it |
| calls | Unique recorded model responses; not tool calls |
| ctx | Most recent input size for an active context; three largest shown |
| complete | Whether this read found incomplete/missing/oversized usage records |
| accepted / cpu | Unknown until joined with existing independent project evidence |

Counts are rounded to three significant digits in the table. `--json` returns
exact values and scope details. A `?` delta means there is no nonzero baseline;
it is not zero change. Short worker labels include a stable hash when truncated.

Claude: repeated streaming fragments are merged by message ID and the largest
counter is retained. Synthetic notices are not model responses. The named main
transcript and its `subagents/` transcripts are included. Timestamp-preserving
copied history is outside the window or deduplicated within the scanned files.

Codex: `input_tokens` includes cached input, so cached input is subtracted before
reporting new input. Response IDs deduplicate `token_usage_record` and its
`token_count` mirrors. Legacy token_count-only fallback is explicitly labelled;
forks, counter resets, schema transitions and missing records can make it less
reliable. Child rollouts are not aggregated. Request a specific rollout explicitly.

The reader limits individual lines to 1 MiB and marks oversized/unreadable records
as incomplete. It retains token metadata for the selected interval, not message
content. Hook errors yield one small advisory diagnostic per interval; they never
block tools or enter a retry loop.

## Evaluate work, not just activity

Match projects and time intervals. A drop in tokens because workers were idle is
not an efficiency win. Compare useful accepted batches, time to acceptance,
resource occupancy and regressions. Avoid comparing unrelated batch sizes.

Cached reads, writes and output have different rates; apply the current model's
pricing only when calculating a labelled API-equivalent estimate. Subscription
limits are not reliably inferred from raw tokens or those estimated dollars.

The 1,000-character injection cap bounds reminder text, not the model's internal
reasoning. Keep routine review output to three lines and avoid another scan when
the hook already supplied the report. Expand only for an actionable anomaly.
