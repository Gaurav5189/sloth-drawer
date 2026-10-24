# Project Index & Map

## Active State
- **Current Phase:** Phase 5 — Write, show, publish → **in progress (2026-10-24)**. Post is WRITTEN and
  staged as a DEV draft (article 4909935, `edit_url` handed to the human; not published). Demo material
  captured in `out/demo/` (terminal takes + 3 live screenshots + recording script). Agent session 1115
  (public) embedded as `{% agent_session 1115 %}`. Remaining: human attaches screenshots, then publish
  + post-publish checks. Repo: https://github.com/Gaurav5189/sloth-drawer
- **Current Task:** Phase 5 finish — draft review, screenshot attachment, publish, comment on the
  challenge post
- **Category list (final):** Gemma, Tiger Data, Render, Entire/DEV. `.tech` (by decision 2026-10-23)
  and **Sentry (cancelled by decision 2026-10-24 — the screenshot task and the category are dropped;
  the optional tracing code stays in place, a no-op without a DSN)**
- **Screenshots to attach to the draft:** ① `out/demo/printable-card.png` ② `out/demo/card-live.png`
  ③ terminal card (`uv run sloth-drawer card honeywell-hpa3000`) ④ `out/demo/device-list.png`
  ⑤ report table (`uv run sloth-drawer report`) ⑥ closing report-table image — files marked ✓
  in `out/post-draft.md`'s header are captured already; ③ and ⑤ are 5-second terminal captures
- **Evidence:** live Tiger index 1323/1325 chunk writes (1305 distinct rows; 2 index_failed, recorded); parity run 4/4 PARITY (`out/parity-run.txt`); web UI byte-identical to the CLI card; live URL serving real due dates; 297 tests green
- **Deadline note (⚠):** the Events API returns Week 3 `ends_at` = **2026-10-25T06:59Z** while the
  challenge text says submissions due "October 25, 11:59 PM PDT" (= 2026-10-26T06:59Z). Plan against
  the earlier reading — publish Sun morning UTC at the latest

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