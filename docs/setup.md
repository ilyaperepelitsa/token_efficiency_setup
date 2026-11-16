# Serena and CodeBurn

Use Node.js 22.15+ for CodeBurn 0.9.28. Use Python 3.10+ for this repository's
standard-library-only scripts. Serena manages its own Python requirements through
`uv`; language-server prerequisites depend on your language and are deliberately
outside this language-neutral guide.

## Install the upstream tools

```sh
npm install -g codeburn@0.9.28
uv tool install serena-agent
codeburn --version
serena start-mcp-server --help
```

Check [Serena's installation documentation](https://oraios.github.io/serena/02-usage/010_installation.html)
for the current supported distribution and Python version. Upstream tools change;
record your installed versions and review updates before applying them. Avoid
automatically downloading a different tool version on every client launch.

## Add MCP servers

MCP **stdio servers start automatically as child processes of the coding client**.
They do not require a Docker container, boot service, or separately running web
dashboard. If you instead choose HTTP transport, starting and securing that server
becomes a separate responsibility. This setup uses stdio.

Claude Code user scope:

```sh
claude mcp add --scope user codeburn -- codeburn mcp
claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd
```

Codex user scope:

```sh
codex mcp add codeburn -- codeburn mcp
codex mcp add serena -- serena start-mcp-server --context codex --project-from-cwd
```

The client's executable search path must include these tools. Use absolute paths
from `command -v` in MCP config if a GUI client does not inherit your shell PATH.
Don't register the same server twice at conflicting global/project scopes.

Cursor user MCP configuration can use this shape (merge entries into your existing
`~/.cursor/mcp.json`; do not replace the file):

```json
{
  "mcpServers": {
    "codeburn": {"command": "codeburn", "args": ["mcp"]},
    "serena": {
      "command": "serena",
      "args": ["start-mcp-server", "--context", "ide", "--project-from-cwd"]
    }
  }
}
```

Activate the actual worktree if startup detection picks the wrong directory. A
project-scoped server can instead use `--project /path/to/worktree` explicitly.
Choose per-project binding when multiple independent worktrees must stay isolated.

## Reduce overhead without changing native routing

- Start with upstream client-specific Serena contexts. The optional
  [navigation context](../examples/serena/navigation.yml) removes duplicate generic
  file/shell tools. Pass its absolute path as `--context` if you want that policy;
  verify the resulting tools before relying on it.
- Use symbol overviews and definitions before requesting bodies. Fetch references
  only when needed; use native text search for non-symbol data.
- If indexing is limited for resource reasons, missing references are incomplete
  evidence. Don't globally disable indexing or prescribe language-server settings
  for every language just to save tokens.
- Install the [shared review skill](../README.md) and merge the instruction snippet.
  Do not force model roles or edit built-in agents just to make tools appear.

## CodeBurn beyond the small review

```sh
codeburn doctor --provider claude --json
codeburn models --period today --provider claude --project PROJECT --format json
codeburn models --period today --provider codex --project PROJECT --format json
codeburn web
```

Check `codeburn doctor --help` if your version uses different output flags.
The dashboard is optional; the MCP and CLI do not depend on it. Large histories
can make dashboard queries expensive. Prefer scoped CLI reads rather than loading
all history or blindly increasing Node's heap. No upstream package patches are
distributed here. Keep any dashboard bound to loopback unless explicitly secured.

Sources: [CodeBurn](https://github.com/getagentseal/codeburn),
[Serena clients](https://oraios.github.io/serena/02-usage/030_clients.html),
[Codex MCP](https://developers.openai.com/codex/mcp),
[Claude MCP](https://code.claude.com/docs/en/mcp).
