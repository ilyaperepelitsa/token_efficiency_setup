# Repository maintenance

Keep this toolkit language-neutral, client-aware and free of personal or project
data. Use synthetic fixtures only. Do not copy runtime transcripts, reports,
account configuration, credentials or machine-specific paths into this repository.

Preserve native client permissions, routing, model selection and project gates.
Hooks are optional, advisory and main-session-only; never block tools or wake idle
sessions. Keep collection deterministic and reports capped. Distinguish local
transcript data from CodeBurn output and quota estimates from recorded tokens.

Before publishing, run `python3 -m unittest discover -s tests -v` and
`python3 scripts/check_public_content.py`; inspect the exact staged diff. These
checks complement human privacy review; they cannot prove absence of every secret.

Reusable user instructions live in `examples/AGENTS.snippet.md`, not this file.
