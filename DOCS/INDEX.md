# Project Index & Map

## Active State
- **Current Phase:** Phase 3 — Batch, tracing, and the offline proof (in progress)
- **Current Task:** the batch runner (`batch.py`), `observability/sentry.py`, the offline proof, the benchmark re-run, and `README.md`. The backend parity run is deferred to Phase 4, where the Tiger backend lands
- **Blocked:** none. 19-manual corpus scans unattended in 614 s (35 found / 22 PASS / 13 REPAIR / 7 REJECT); `scan --resume` skips a finished corpus in 0.5 s; cards render

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