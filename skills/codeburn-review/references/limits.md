# Adapter limits

The report uses native local transcripts because the supported CodeBurn CLI has
date-only filters. It is not an account ledger and makes no quota/cost conversion.
Claude includes the named session and its workers; Codex includes one rollout only.
Codex legacy fallback is labelled and less reliable across forks/counter resets.
Incomplete records mark the report incomplete. Output already includes reasoning.

Hook data is capped at 1,000 characters including instructions; CLI output at 840.
The default is a dense rounded table; exact counters and names stay in local JSON.
Do not read exact JSON routinely. Written reviews are limited to three short lines,
with expansion only for a concrete anomaly. The cap does not constrain a model's
internal reasoning or guarantee that the model follows the guidance.

Reminders skip worker metadata, use a nonblocking lock and claim each 900-second
interval before scanning. A failure becomes one bounded advisory per interval,
never a permission decision, Stop continuation or retry loop. Idle clients receive
no reminders; a long-running tool defers delivery to completion. Registration is
not evidence of actual delivery: inspect the local state/report and client output.

Run the repository tests, including duplicate records, synthetic notices, adjacent
windows, main-only throttling, metadata rows and output-size regressions. Fixtures
are synthetic. No production session logs or measurements are distributed.
