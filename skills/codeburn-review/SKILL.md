---
name: codeburn-review
description: Review recent token usage every 15 minutes during active work, compare structured windows, verify earlier efficiency changes and apply a bounded correction. Main session only; no idle monitoring or worker reviews.
---

# CodeBurn review

Use in the main session every 15 minutes while a task is active. This is a short
checkpoint in the existing work, never a separate research task or agent team.
The global reminder is advisory: it supplies a report after tool completion when
due, without spawning models, blocking tools or waking an idle session. After a
long tool call, the reminder arrives at the next tool completion. No busy polling.

## Structured comparison

If a reminder already supplies a table, use it; do not run another scan.
Otherwise:

```sh
codeburn-review report --provider claude --session CURRENT_SESSION_UUID
codeburn-review report --provider codex --transcript /absolute/current/rollout.jsonl
```

The script compares adjacent, non-overlapping 15-minute windows. It separates new
input, cache writes, cache reads and output; lists the three largest active
contexts; and labels missing data. It reads local token metadata, makes no model
or network calls and emits no prompts/source/audio. Claude includes that session's
workers. Codex covers the named rollout only; do not present it as fleet-wide.

Automatic injection is capped at **1,000 characters including instructions**.
The default CLI prints the same dense table: previous/current/delta for all five
metrics, three largest contexts, scope and missing-data flags. Counts use three
significant digits; exact JSON stays at the linked local path (`--json` prints it).
Never open the full JSON routinely. The regular review is at most three short
lines in the existing checkpoint: result, action/no change, evidence/constraint.
Do not narrate the review or send a separate user-facing update without an
actionable finding. Expand only to investigate a specific anomaly or failed fix.

**Source boundary:** CodeBurn's CLI filters by date, not minute. This local
transcript adapter supplies the precise recent windows. Use CodeBurn's structured
`models --format json` or MCP usage/savings for a relevant broader milestone,
scoped to the same project/provider; don't scan all history every 15 minutes.
Do not call adapter data a CodeBurn API response. Do not run both unnecessarily.

## Decide and act

1. Verify the previous adjustment's actual adoption using current evidence:
   context sizes after handoff, a real Serena call, reduced redundant reads/turns,
   or useful CPU occupancy. A forwarded instruction is not proof of adoption.
2. Join the token windows to comparable accepted work and resource observations
   from existing receipts. `accepted_batches` and `cpu_utilization` are null until
   you supply evidence. No acceptance data means efficiency remains unmeasured;
   lower activity alone is not improvement. Cached input has different weight
   from writes/output; don't equate raw total tokens with quota or money.
3. If evidence warrants it, apply at most one or two concrete corrections within
   existing authority: narrow discovery, avoid repeated unchanged output, use
   verified symbol tools, chain deterministic steps or hand off a finished batch
   from an oversized context. Follow through at a safe boundary and verify it.
   If already efficient, record no change and continue the task.
4. Put one brief delta in the EXISTING checkpoint: compared interval, accepted
   work/resource evidence, adjustment, observed result or constraint/owner/next
   action. Revisit this result at the next review. Keep raw logs/evidence on disk;
   do not create another acceptance ledger or a global usage diary.

The review itself does not authorize model changes, new teams, stopping jobs,
permission changes, commits/pushes or weakened gates. Preserve original receipts,
all qualification, source ownership and useful admitted CPU parallelism. Workers
send efficiency findings with normal results; they do not run this review.

Promote a verified cross-project lesson into the canonical shared AGENTS.md
after recording evidence and limits in project memory; merge it with the existing
rule instead of duplicating it. Provisional/project-specific findings stay local.

## Installation and runtime

Install this skill using the repository's `scripts/install.py` and optionally
its Claude PostToolUse reminder. Client-specific paths and hook compatibility are
in `docs/clients.md` in the source repository. The installed
payload is self-contained for report execution; it does not contain client config.
Codex needs the native rollout path and host support for the hook envelope; Cursor
uses the skill manually at native checkpoints. Do not claim installation proves
live delivery. Silence reminders with `~/.config/codeburn-review/disabled`.

The CLI has no third-party dependencies (Python 3.10+, macOS/Linux). No server,
model call or background service is needed for collection. Read
[accounting limits](references/limits.md) when diagnosing counters or hook behavior.
