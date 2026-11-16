# Privacy boundaries

This repository contains generic instructions, code, synthetic tests and one
explicitly reviewed anonymized aggregate. Its allowed numeric fields and anonymous
labels are checked separately; it contains no raw session records. Do not publish
raw local reports, transcripts, screenshots, session identifiers,
agent briefs, personal filesystem layouts, account configuration or credentials.
The release check flags common private paths, secret patterns and runtime file
types, but cannot prove the absence of every form of sensitive content.

The local adapter reads transcript files to find usage counters and message IDs.
It parses transient message records but does not emit prompt/source bodies or
make network/model calls. Its compact output can include worker labels, token
counts and a local report path. Exact JSON, reminder state and locks live under
`~/.cache/codeburn-review/`. They are not written into this repository.

Runtime reports and state files are created with user-only permissions. The
installer writes executable paths for your own machine into your local client
settings. Those generated files are private configuration, not distributable
examples. Backups may contain pre-existing sensitive settings; keep them local.

**Local does not mean never sent anywhere:** a reminder becomes coding-agent
context, so its metadata is sent to that agent's provider in the normal request.
Serena's returned source snippets also become agent context. Review project data
policies before using these tools on restricted code. No new external service or
telemetry endpoint is added by this toolkit.

CodeBurn and Serena are separate upstream tools with their own behavior. Installing
them, enabling sharing/telemetry, exposing dashboards or choosing HTTP transports
requires independent review. This setup uses client-owned stdio servers and does
not enable CodeBurn remote sharing or publish dashboards.

Before publishing changes:

```sh
python3 scripts/check_public_content.py
git diff --cached --stat
git diff --cached
```

Use an explicit staging list. Never stage runtime directories or copy a whole user
configuration tree as an example. Inspect filenames as well as file contents.
