# Project Index & Map

## Active State
- **Current Phase:** Phase 4 — Surface & partner categories → **backend, parity diff, web UI complete** (2026-10-23). Render deploy, `.tech` domain, category confirmation remain
- **Current Task:** Phase 4 remainder — Render deploy (tolerate the free-tier cold start), `.tech` domain claim, finalise the category list; then Phase 5 (demo recording, Sentry screenshot, the post)
- **Blocked:** the Sentry trace screenshot needs a real `SLOTH_SENTRY_DSN` (Phase 5); the Render deploy needs an account/token. Evidence so far: live Tiger index 1323/1325 chunks (2 index_failed, recorded); parity run 4/4 PARITY (`out/parity-run.txt`); web UI serves the exact CLI card; 297 tests green

## Doc Map
> **Restructure applied at kickoff (2026-10-22).** The docs now live in `DOCS/` and `MEMORY.md` lives
> in `.agents/`. `PLAN.md` stayed at the project root, next to `README.md`.

- **`RULES.md`**: Code formatting, framework rules, strict constraints. (path: DOCS/)
- **`PRD.md`**: Product features, user flows, acceptance criteria. (DOCS/)
- **`ARCHITECTURE.md`**: Database schema, API endpoints, folder structure, system flow. (DOCS/)
- **`DESIGN.md`**: UI component rules, color palettes, visual tokens, layout specs. (DOCS/)
- **`PHASES.md`**: Roadmap breakdown, current phase deliverables, completed milestones. (DOCS/)
- **`PLAN.md`**: The 4-day schedule, model benchmarks, risk register, post outline. (project root)
- **`MEMORY.md`**: Architectural decisions, past bugs, lessons learned. (.agents/)

## Retrieval Guidelines
1. Working on UI/Layout? -> Read `DESIGN.md`.
2. Modifying DB/API/Endpoints? -> Read relevant sections in `ARCHITECTURE.md`.
3. Updating roadmap or status? -> Check `PHASES.md`.
4. Stuck on an edge-case bug? -> Grep `MEMORY.md` for related issues.
5. Touching the model, the retrieval backend, or the cloud boundary? -> Read `RULES.md` §1.3, §1.4 and §3
   before writing a line.
6. Need the schedule, the benchmark numbers, or the post outline? -> Read `PLAN.md`.