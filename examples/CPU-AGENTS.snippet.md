## CPU reservations and useful execution — only after installing CPU enforcement

- Lead with project work and results. Run ordinary shell commands and let the
  hook add the admission wrapper. Mention resource details when they explain
  a refusal, actionable idle capacity or a due review.
- CPU.md is current state: global logical-CPU total, system reserve and project
  maximum; each project's exact count/list, active flag and current loans. No
  overlap, over-budget reservations, history, transactions or status diary. No
  fixed line/project-count limit. Project instructions link the shared authority.
- Verify a real guarded call in every new setup/context. Use registered worktrees
  and the declared service prefix. Do not escape the guard via alternate tools,
  unregistered services, containers or schedulers. Native routing, permissions,
  acceptance, memory caps, locks and timing restrictions remain binding.
- Read current usable CPUs and effective affinity before launch/after allocation
  changes. Pass exact admitted CPUs and fit thread/process counts to that set and
  the job's memory profile. Many workers pinned to one CPU are not parallel use.
- Leads update only their own flags/loans through the installed reservation helper.
  Keep active through handoffs. Inactive/release requires verified drained jobs,
  sleeping waiters and queued launches. A quiet sample or idle conversation is not
  a release. Borrow only atomically claimed inactive pools, never system CPUs.
  Resumed owners wait for borrowers to drain without successors and release safely.
- Judge accepted progress and useful owned CPU-time/wall-time, using >=60s samples
  at completions and each 15-minute active main review. Sleeping services, host CPU,
  checkpoint counts and incomplete accounting do not establish useful utilization.
  One owner can feed multiple processes; no agent-per-core requirement.
- Refill independent required work when capacity frees. Otherwise record the exact
  dependency/lock/admission/timing/permission constraint, owner and next action in
  the current lane brief. Resolve due reviews with `cpu-enforce review --project
  NAME --constraint CODE --next ACTION --evidence FILE`; the Stop hook checks a fresh
  acknowledgement. No idle wakeups, polling swarm, artificial load or passed sweeps.
- A guard can enforce admission and require a review, not infer scientific
  acceptance or guarantee useful work. Verify that the chosen correction took
  effect; do not report assigned/reserved CPUs as measured busy CPUs.
