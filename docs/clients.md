# Client integration and removal

## Shared instructions

Merge [AGENTS.snippet.md](../examples/AGENTS.snippet.md) into your canonical global
instructions. Do not replace existing AGENTS.md or CLAUDE.md. Codex commonly reads
`~/.codex/AGENTS.md`; Claude can import that one file from `~/.claude/CLAUDE.md`:

```text
@~/.codex/AGENTS.md
```

Confirm imports against your installed client. Cursor requires its supported rules
or an explicit session-start import; installation of a skill alone does not load
AGENTS.md. This installer does not add a Cursor instruction hook or claim that a
specific Cursor release reads another client's global instruction file.

## Skill installation

`scripts/install.py` links a shared installed copy into selected client roots:

| Client | Skill root |
| --- | --- |
| Claude | `~/.claude/skills/` |
| Codex | `~/.agents/skills/` |
| Cursor | `~/.cursor/skills/` |

Some Codex versions also discover `~/.codex/skills/`; avoid duplicate installations
of the same skill. Use the real client skill list to verify discovery. Python and
POSIX filesystem support are required; Windows/WSL behavior is not validated here.

The launcher is installed at `~/.local/bin/codeburn-review`. Put that directory on
PATH or invoke it by absolute path. External MCP tools are configured separately.

## Claude's optional reminder

```sh
python3 scripts/install.py --clients claude --claude-hook
```

This adds one **PostToolUse** command to user settings. It preserves other keys
and backs up the JSON file before changing it. Re-running is idempotent. The hook
returns only `additionalContext`; it never returns a permission or Stop decision.
It skips workers using their agent metadata and starts its first 15-minute clock
on a main-session tool event. Long calls defer the reminder until completion.

The report is a local summary, not a scheduler that guarantees the model's behavior.
The main agent still has to apply the skill and verify the chosen correction. A
running process, installed file or forwarded instruction is not proof of use.

Disable reminders without changing other hooks:

```sh
mkdir -p ~/.config/codeburn-review
touch ~/.config/codeburn-review/disabled
```

Remove the marker to enable them again. No background service needs stopping.

## Codex and Cursor reminders

The report CLI and skill work independently of hooks. Codex hook support varies
by version and host. On versions supporting command PostToolUse hooks with the
Claude-compatible input/output envelope, the following is an **optional template**:

```toml
[[hooks.PostToolUse]]
matcher = ".*"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 /absolute/path/to/installed/skills/codeburn-review/scripts/review.py hook --provider codex"
timeout = 15
```

Inspect your installed schema before adding it. The adapter needs the actual
`transcript_path` to the native rollout; a missing path yields a bounded diagnostic
instead of inventing a total. Verify an actual delivery after normal reload/resume.
The installer does not alter Codex hooks. No Cursor reminder is supplied; its hooks
use a different protocol. Use the skill at native checkpoints in unsupported hosts.

## Remove installed pieces

```sh
python3 scripts/install.py --clients claude codex cursor --remove
```

This removes only links and the launcher that target this installation, and this
installation's optional Claude hook. It leaves the shared payload, cached reports
and backups for inspection. Delete those explicitly after reviewing them if desired.
Remove only this toolkit's instruction/MCP entries manually; preserve other config.
