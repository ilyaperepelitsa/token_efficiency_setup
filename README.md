# Token efficiency setup

A language-neutral setup for using **Serena** to navigate source and **CodeBurn**
to inspect coding-agent usage, with compact 15-minute reviews for active tasks.
Works with Claude Code and Codex; Cursor gets the shared skill and instructions.

This repository provides setup recipes, a portable review skill and an optional
advisory reminder. It does not choose models, change permissions, create agent
teams or relax project acceptance checks. Savings are workload-dependent; measure
accepted work as well as usage before claiming an improvement.

## Start here

1. Follow [Serena and CodeBurn installation](docs/setup.md).
2. Install the local review skill (Python 3.10+, macOS/Linux):

   ```sh
   python3 scripts/install.py --clients claude codex cursor --dry-run
   python3 scripts/install.py --clients claude codex cursor
   ```

3. Merge the short [AGENTS.md snippet](examples/AGENTS.snippet.md) into your own
   instructions. Keep one canonical copy and import/reference it from other clients.
4. Optionally install Claude's passive reminder:

   ```sh
   python3 scripts/install.py --clients claude --claude-hook
   ```

   It checks a small state file after tools complete. Every 15 minutes while the
   main session works, it supplies a compact comparison. No timer daemon, model
   calls, worker reviews or idle wakeups. A long tool call defers delivery until
   completion. See [client integration and removal](docs/clients.md).
5. [Verify actual tool use](docs/verification.md). A running server is not proof
   that an agent or its workers can access or use it.

The installer copies only this repository's skill, creates a launcher and client
skill links, and optionally merges one Claude hook. It does not install external
packages or rewrite AGENTS.md/MCP configuration. Existing unrelated settings are
preserved; conflicting skill paths cause a refusal. Preview changes with `--dry-run`.

## The review

```sh
~/.local/bin/codeburn-review report --provider claude --session SESSION_UUID
~/.local/bin/codeburn-review report --provider codex --transcript /path/to/rollout.jsonl
```

Example with **synthetic numbers**:

```text
metric | prev | now | delta
new    | 100k | 80k | -20%
write  | 200k | 180k | -10%
cached | 8M   | 6M  | -25%
output | 20k  | 21k | +5%
calls  | 40   | 36  | -10%
ctx worker-a:110k worker-b:95k
complete=1 accepted=? cpu=?; scope=main+workers
```

The hook's entire injected text is capped at **1,000 characters**. Default CLI
output is capped at 840. Exact JSON stays local; `--json` opts into full output.
Routine written reviews are at most three short lines: result, action, evidence.
Investigate further only for a concrete anomaly or a failed prior adjustment.

**Data source:** CodeBurn 0.9.28 CLI supports date ranges, not arbitrary minute
windows. This repository's local transcript adapter supplies adjacent 15-minute
windows; it does not call itself a CodeBurn API. CodeBurn remains useful for broader
project/model analysis. Avoid running both scans for the same small checkpoint.

Claude reports include that session's workers. Codex reports cover the specified
rollout only. Counts are recorded usage, **not subscription allowance or a bill**.
See [accounting and limitations](docs/accounting.md).

## Evidence, including the limits

In an uncontrolled sample across two real sessions, equal 15-minute windows showed:

| Metric | Before → after | Change |
| --- | ---: | ---: |
| New input + cache writes | 4.43M → 4.21M | −4.9% |
| Cached input | 73.25M → 47.17M | −35.6% |
| Output | 223.59k → 303.46k | **+35.7%** |
| Model responses | 243 → 267 | **+9.9%** |

**Smaller contexts were observed; better overall efficiency was not established.**
Workloads were not matched and accepted-work comparison was unavailable. Multiple
changes happened together, so these figures do not isolate Serena, CodeBurn or the
review skill, and do not measure subscription savings.

See [the full observation and limitations](docs/observations.md) and
[exact anonymized aggregates](data/anonymized-observations.json). Names, languages,
models, identifiers, paths and calendar timestamps have been removed. Raw session
records remain private, which limits independent verification of this sample.

## Privacy and validation

The tools read local usage metadata and do not upload it or make model/network
calls. The coding client still sends its normal context to its provider; a compact
hook report becomes part of that context. Reports include shortened agent labels,
usage counts and a local output path. See [privacy boundaries](docs/privacy.md).

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_public_content.py
python3 scripts/check_evidence.py
```

Tests use synthetic fixtures. The only real-session evidence is the explicitly
allowlisted anonymized aggregate above. No raw runtime reports, personal
configuration, session exports, histories or project-specific instructions belong here.

Upstream: [Serena](https://github.com/oraios/serena),
[Serena client setup](https://oraios.github.io/serena/02-usage/030_clients.html),
[CodeBurn](https://github.com/getagentseal/codeburn),
[Claude hooks](https://code.claude.com/docs/en/hooks),
[Codex MCP](https://developers.openai.com/codex/mcp).

MIT licensed. Third-party tools retain their own licenses and privacy policies.
