# Verify the workflow

Do these checks in a small disposable project before relying on a setup for long
tasks. Use synthetic transcripts for report tests. Never upload a private session
export as a diagnostic fixture.

## Serena

1. Confirm the client lists the MCP server and exposes the symbol tools.
2. Activate the actual worktree, or check the project bound by startup detection.
3. Run a symbol overview or definition lookup against a small known source file.
   Confirm that the returned symbol and location match the current source.
4. If delegation is used, have one existing relevant worker verify its own tool
   access. Parent MCP access does not imply worker access; restricted agent types
   may omit MCP tools. Report the limitation once and use scoped native reads.
5. Check actual usage later. A successful installation or one rehearsal does not
   prove that future workers are using the tool. Do not restart a working agent
   solely for MCP access or block all work behind an unavailable tool.

## CodeBurn

Confirm `codeburn doctor --provider claude --json` (or `--provider codex`) detects
the intended local source. Use one scoped `models --period today --provider ...
--project ... --format json` report. Treat missing history as missing data.
Keep the output private; it can include project names and filesystem paths.

## Review adapter

Run `python3 -m unittest discover -s tests -v`. Tests use only synthetic data.
For a real local session, compare the compact and exact output over the same fixed
end time. `--until` accepts an ISO timestamp with a timezone; do not use an example
date to claim current usage. Check scope, data completeness and the five buckets.

## Passive reminder

1. Install the optional Claude hook, then confirm it appears in the client's loaded
   hooks/settings. Reload or normally resume if the client requires it.
2. During an existing active task, confirm the first main-session tool event creates
   a state file under `~/.cache/codeburn-review/`.
3. After 15 minutes, the next completed main tool should create/update a local
   `.latest.json` report and supply a short context reminder. Check both the state
   and actual client delivery; do not infer delivery from configuration alone.
4. Confirm workers do not create their own reviews, and repeated tool completions
   before the next interval do not produce another report. Check the skill is used
   to make a short decision, not to launch another analysis team.

No claim of savings is established by these checks. Measure comparable accepted
work, usage, turnaround and useful resource occupancy before and after a change.
Preserve project correctness and qualification requirements throughout.
