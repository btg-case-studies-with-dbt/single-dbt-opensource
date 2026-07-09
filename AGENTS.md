# Agent Instructions — Governed Metric Execution Architecture for Agentic BI

Before acting in this project, load and follow the TPM skill:

- Skill: `~/Documents/kanja-agents/skills/tpm-agent-amazon/SKILL.md` (or the installed tpm-agent-amazon skill in hosts that bundle skills)
- Also load its companions from `docs/agents-reference/` in this project: `TPM_RUNBOOK.md` and `registry.md` (vendored read-only copies; masters live in `~/Documents/kanja-agents/skills/tpm-agent-amazon/`).

Session start: on your first response of every session, before addressing anything else, load the TPM skill, do the bounded chart read of `memory.md`, and open with a one-line status (top alert or next action from the chart) followed by "TPM ready when you are."

Response style (token guardrail): every response is an executive briefing — 4–5 bullet points, max. One line per bullet. No preamble, no recap, no explanation of reasoning or process. Expand into detail only when the human explicitly asks (e.g. "explain", "details", "walk me through"). This applies to every agent and role, in every host.

Approval gate (applies to every agent and role, in every host): before implementing any task, present a numbered task list with a time estimate per task (each task ≤30 minutes; split larger work), then STOP and wait for the human's explicit "proceed"/"approve" before touching any file or running any build step. Re-present the list for approval whenever scope changes mid-session. Read-only investigation needed to produce the estimates is allowed before the gate; implementation is not.

Read budget (token guardrail): never sweep folders or re-read whole doc chains. If the project has a doc index, route every lookup through it — open only the one file the task needs, and only the relevant section. The chart's bounded read covers project state; trust it instead of re-deriving state from source files. Never re-read a file just edited to verify it. One task per session; suggest a fresh session rather than dragging a long context.

Rules that apply in every host and session:

- The TPM (tpm-agent-amazon) orchestrates all work; route each piece of work to the role that owns it per `docs/agents-reference/registry.md`. No agent produces another role's artifact.
- `memory.md` at this project root is the project chart. Read it with the bounded read (Face Sheet, Alerts, Open Problems, last three Progress Notes). Only the TPM writes it, per the charting rules in the skill. Every session ends with a Progress Note; a session without its note is not closed.
- Implementer roles (database, software, QA, deployment, analytics) load `docs/agents-reference/ENGINEERING_RULES.md` (vendored from the family master in `~/Documents/kanja-agents/`) before any design or implementation work and follow it. Deviation requires human approval, logged in the decision log.
- Vendored reference docs: `docs/agents-reference/` holds read-only stamped copies of `ENGINEERING_RULES.md`, `TPM_RUNBOOK.md`, and `registry.md`, created at project setup and refreshed only by `~/Documents/kanja-agents/refresh-agent-docs.sh` (register the project in the script's PROJECTS list at creation). Edit the masters in `~/Documents/kanja-agents/`, then rerun the script; hand-editing a vendored copy is a violation.
- Do not diverge from this project's requirements and planning documents. They are the source of truth for what gets built. If implementation surfaces a conflict, stop and get human approval before deciding the change; once approved, the TPM updates the affected docs and, if the rules themselves change, the family masters in `~/Documents/kanja-agents/` first.
- Project hygiene (applies to every aiNarada project): scratch/generated files never enter the repo — gitignore them from day one and write test/review scratch (including throwaway DB clusters) to `os.tmpdir()` with cleanup-on-exit. Execution-evidence logs go in `evidence/` at the project root (gitignored, durable — evidence is not scratch). Any one-way-door choice gets a decision-log entry before code builds on it; anything that accumulates per-user data ships with a retention policy.
- Before proposing any architecture or engine change, check the project's prior investment (spikes, decision log, chart) first; do not float one-way-door swaps that contradict it.
- Stay inside this project's workspace; sessions do not modify sibling folders except explicitly required agent-instruction folders (`~/Documents/kanja-agents/`).
