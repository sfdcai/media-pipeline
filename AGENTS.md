# AGENTS

This project uses three logical agents. Tools may consult this file to determine roles and workflows.

## 1) Planner
- **Purpose:** Expand the Roadmap into actionable tasks; keep `/prompts/TASKS.md` prioritized and clean.
- **Reads:** `docs/ROADMAP.md`, `docs/API.md`, `docs/SCHEMAS.md`, `docs/CONFIG.md`
- **Writes:** Appends **TODO** items to `/prompts/TASKS.md` using the canonical task template.
- **Constraints:** No code changes. No API breaking changes. Each task must be < 15 lines.

## 2) Implementer
- **Purpose:** Deliver code for a single task ID.
- **Reads:** Minimal docs needed (API/SCHEMAS/CONFIG + module stubs).
- **Writes:** Code files, tests, short doc tweaks, CHANGELOG. May append follow-up tasks if truly needed.
- **Constraints:** Idempotent endpoints, config-driven, update CHANGELOG, add tests, keep diffs small.

## 3) Reviewer
- **Purpose:** Sanity check. Spot missing error handling, config violations, schema mismatches.
- **Reads:** The diff the Implementer produced + referenced docs.
- **Writes:** PR comment / summary; flips task state from REVIEW → DONE in `/prompts/TASKS.md`.

## Status Codes
- `TODO` → `DOING` → `REVIEW` → `DONE` (or `BLOCKED` with reason)

## Acceptable Task Template
- Title
- Context
- Acceptance Criteria
- Scope boundaries
- Status
- Owner (free text)
