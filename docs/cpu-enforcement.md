# Optional CPU enforcement

**Resource admission is enforced; improved throughput is not established.**
This is separate from the advisory usage-review skill. It is for Linux hosts with
a working systemd user manager, cgroup v2, `busctl`, `flock` and Python 3.10+.
Installing Codex's configuration requires Python 3.11+ for TOML validation.
It is not a macOS/Windows CPU scheduler or a general agent coordinator.

## Install explicitly

1. Make a private copy of [CPU.md](../examples/CPU.md) and
   [the configuration example](../examples/cpu-config.json). Every value is
   synthetic: replace the total, system reserve, budget, exact CPU IDs, worktree
   paths and unique service prefixes for your machine. Do not commit the private
   configuration. Register every table project; do not use broad system prefixes.
2. Preview, then apply:

   ```sh
   python3 scripts/install_cpu.py --config /path/to/private-config.json --clients claude codex
   python3 scripts/install_cpu.py --config /path/to/private-config.json --clients claude codex --apply
   ```

   Preview writes nothing. Apply copies the generic Python payload, installs a
   bounded guardian user service and service-prefix drop-ins, starts the guardian,
   then adds shell/review hooks. It backs up changed files, preserves unrelated
   settings and never rewrites CPU.md or global instructions. Existing Bash input
   hooks, unmanaged installations, overlapping prefixes and mixed Codex hook
   formats cause a refusal; integrate those explicitly instead of replacing them.
3. Review/trust the exact handlers using Codex's native `/hooks` UI. No trust or
   sandbox bypass is supplied. Reload/resume clients as needed and verify a real
   guarded command; installed files and an active daemon are insufficient evidence.
   Claude and Codex hooks were exercised on a local deployment; every supported
   version/host combination has not been tested. Cursor's shell path is not covered.
4. Merge the separate [CPU instruction snippet](../examples/CPU-AGENTS.snippet.md)
   into your canonical shared instructions. It is not activated by installing the
   Serena/CodeBurn review skill.

The guardian is enabled on `default.target`: it starts with the user systemd manager.
For service availability before login, inspect `loginctl show-user "$USER" -p Linger`.
If needed, an operator can explicitly enable lingering with `loginctl enable-linger`.
The installer does not silently change login policy or host-wide system services.

## What is mechanical

- A project shell wrapper waits before executing code. The guardian matches its
  actual PID/start identity and current reservation, then places that same process
  in a kernel CPU scope. Its native filesystem/network/seccomp sandbox stays in
  force; the guardian never executes submitted source or shell code.
- Service-prefix ExecCondition gates revalidate every start/restart and apply
  AllowedCPUs. Inactive owners, stale requests and undrained conflicting holders
  block new work. Existing healthy project jobs are not restarted or repinned.
- Flag/loan changes use a file lock. Inactive, release and borrowing an inactive
  pool check actual services, waiting processes, queued starts and populated scopes.
  A dead wrapper alone is not proof that its descendants drained. After recall,
  borrowers cannot launch successors on that loan and owners wait for safe release.
- Fixed CPU bookkeeping operations are validated by the trusted hook outside a
  restricted shell and returned as inert output. This grants no general filesystem
  writes, project-code execution, unit-stop permissions or model/routing overrides.
- The guardian takes deterministic minute samples without model calls. Main agents
  get a compact reminder every 15 active minutes at tool/Stop boundaries and must
  acknowledge a current lane constraint/action with nonempty fresh evidence:

  ```text
  cpu-enforce review --project NAME --constraint CODE --next ACTION --evidence /path/to/current-lane-brief
  ```

Workers do not run separate reviews. Idle sessions are not woken. Long tool calls
defer model feedback. `cpu-enforce audit` is compact; `audit --json` exposes exact
owned-service/scope accounting. Short/exited jobs can be missing; CPU time is not
accepted work, and allocated CPUs are not the same as measured busy CPUs.

Use the installed `cpu-reservations.py` with `--file /path/to/CPU.md status`, or
`--project NAME active|inactive|borrow|release`. Loans need `--cpus N,M` and releases
need `--drained`, which is verified rather than blindly trusted. Keep work/resource
details in existing lane briefs. CPU.md grows only for actual current project rows.

## Verification and honest evidence

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_cpu_native.py         # preview only
python3 scripts/check_cpu_native.py --run   # explicit isolated, tiny Linux probes
```

The native check starts/removes only its own UUID-named guardian and uses a separate
temporary CPU table. It checks exact CPU boundaries, denied affinity expansion,
reservation changes, inactive admission and shell/exit semantics, without model
calls or editing real project/client state. CI runs synthetic policy/installer
tests; it does not claim that hosted runners have a working systemd user manager.

A local deployment additionally passed eleven real service/loan scenarios and
nine native sandbox scenarios, plus an actual Codex shell dispatch. These local
checks included recall, stale inactive flags, waiting jobs and preserved filesystem
restrictions. Raw host configuration, private integration logs and session records
are not published; the public native check covers a smaller reproducible subset.

**Negative operational evidence:** idle reserved capacity persisted. Missing
completion notifications delayed worker handoffs, and a serial candidate build
left downstream lanes waiting. Reviews recorded these constraints and next actions;
that does not prove they were resolved or that accepted throughput improved.
There is no matched before/after accepted-work or token-savings result for this
component. Native client completion delivery and dependency planning remain real
limits. More polling or an artificial CPU load would not establish progress.

This is a guard for registered cooperating clients, not a security boundary against
the same Unix user deliberately disabling it. Unregistered execution paths are not
automatically covered. It cannot force useful work, parallelize a true dependency,
prove scientific acceptance or promise that every instruction will always be obeyed.

## Removal and recovery

Drain owned work and inspect requests first. Remove all installed CPU clients
together so one client is not left pointing to a stopped guardian:

```sh
python3 scripts/install_cpu.py --config /path/to/private-config.json --clients claude codex --remove
python3 scripts/install_cpu.py --config /path/to/private-config.json --clients claude codex --remove --apply
```

Removal affects only this installation's controller, hooks, launcher and marked
drop-ins. Payload/configuration/backups remain for inspection; project jobs and
their original resource properties are retained. Existing foreign installations
are not migrated or overwritten automatically. For failures, inspect the exact
guard diagnostic and `journalctl --user -u cpu-reservation-guardian.service` before
retrying; do not duplicate a live workload or weaken its native permissions.

Native mechanism references: [systemd resource controls](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html),
[systemd execution conditions](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html),
[Claude hook protocol](https://code.claude.com/docs/en/hooks),
[Codex hook protocol and trust](https://learn.chatgpt.com/docs/hooks).
