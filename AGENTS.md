# Agent Instructions — aiTechne: Governed Metric Execution Architecture for Agentic BI

Before acting in this project, load and follow the TPM skill:

- Skill: the installed/symlinked `tpm-agent-amazon` skill (masters live in `~/data-projects/kanja-agents/skills/`).
- Also load its companions from this project: `docs/tpm-reference/TPM_RUNBOOK.md` and `docs/tpm-reference/registry.md`.

Session start: on your first response of every session, before addressing anything else, load the TPM skill, do the bounded chart read of `memory.md`, and open with a one-line status (top alert or next action from the chart) followed by "TPM ready when you are."

Response style (token guardrail): every response is an executive briefing — 4–5 bullet points, max. One line per bullet. No preamble, no recap, no explanation of reasoning or process. Expand into detail only when the human explicitly asks (e.g. "explain", "details", "walk me through"). This applies to every agent and role, in every host.

Approval gate (applies to every agent and role, in every host): before implementing any task, present a numbered task list grouped into the next two-hour block or less, with a time estimate per task (each task 15 minutes or less; split larger work), then STOP and wait for the human's explicit "proceed"/"approve" before touching any file or running any build step. A two-hour block contains at most eight 15-minute tasks; overflow becomes the next block or backlog. Re-present the list for approval whenever scope changes mid-session. Read-only investigation needed to produce the estimates is allowed before the gate; implementation is not.

Loop breaker (applies to every agent and role, in every host): do not repeat the same action after the same result. Before retrying a command, edit, prompt, search, or plan, state what changed: new evidence, a new hypothesis, a different file, a different command, or a different owner. If nothing changed, do not retry. After three failed attempts on the same subtask, stop and summarize the attempt ledger (what you tried, what happened, what you learned), then choose a different approach, route to the owning role, or ask the human/TPM for the next decision. Never spend a full 15-minute block on the same failed cycle.

Read budget (token guardrail): never sweep folders or re-read whole doc chains. If the project has a doc index, route every lookup through it — open only the one file the task needs, and only the relevant section. The chart's bounded read covers project state; trust it instead of re-deriving state from source files. Never re-read a file just edited to verify it. One task per session; suggest a fresh session rather than dragging a long context.

Rules that apply in every host and session:

- The TPM (tpm-agent-amazon) orchestrates all work; route each piece of work to the role that owns it per `docs/tpm-reference/registry.md`. No agent produces another role's artifact.
- `memory.md` at this project root is the project chart. Read it with the bounded read (Face Sheet, Alerts, Open Problems, last three Progress Notes). Only the TPM writes it, per the charting rules in the skill. Every session ends with a Progress Note; a session without its note is not closed.
- Implementer roles (database, software, QA, deployment, analytics) load `docs/guardrails/2.ENGINEERING_RULES.md` — and `docs/guardrails/1.TOOLSTACK.md` for stack decisions — before any design or implementation work and follow them. Deviation requires human approval, logged in the decision log.
- Shared agent instructions live in their canonical skill folders under `~/data-projects/kanja-agents/skills/` and are consumed through installed or symlinked skills. Do not require or refresh `docs/agents-reference/` vendored copies.
- Do not diverge from this project's requirements and planning documents. They are the source of truth for what gets built. If implementation surfaces a conflict, stop and get human approval before deciding the change; once approved, the TPM updates the affected docs and, if the rules themselves change, the family masters in `~/data-projects/kanja-agents/` first.
- Project hygiene (applies to every aiTechne project): scratch/generated files never enter the repo — gitignore them from day one and write test/review scratch (including throwaway DB clusters) to `os.tmpdir()` with cleanup-on-exit. Execution-evidence logs go in `evidence/` at the project root (gitignored, durable — evidence is not scratch). Any one-way-door choice gets a decision-log entry before code builds on it; anything that accumulates per-user data ships with a retention policy.
- Before proposing any architecture or engine change, check the project's prior investment (spikes, decision log, chart) first; do not float one-way-door swaps that contradict it.
- Stay inside this project's workspace; sessions do not modify sibling folders except explicitly required agent-instruction folders (`~/data-projects/kanja-agents/`).
