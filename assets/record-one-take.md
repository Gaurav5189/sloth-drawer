# One-take demo recording — Sloth Drawer

Everything below is scripted so it is one take, no filler. Total on-screen time ≈ 40 s.

## What to record (screen recorder, 80-col terminal, dark theme that matches the site)

```sh
# 1. The terminal run — it replays the checkpoint in ~3 s and prints the report (out/demo/terminal-resume.txt)
uv run sloth-drawer scan data/manuals --resume

# 2. One card, colour, 80 cols
uv run sloth-drawer card honeywell-hpa3000

# 3. The report table (same numbers the post quotes)
uv run sloth-drawer report
```

Transcripts of exactly these outputs are already captured in this folder:

- `terminal-resume.txt` — step 1 (resume + report)
- `card-and-report.txt` — steps 2–3 (terminal card + report)

## Screenshots (already captured, ready for the post)

- `device-list.png` — https://sloth-drawer.onrender.com/ (live, seeded state)
- `card-live.png` — the web card page with verified quotes + due dates
- `printable-card.png` — the A6 print card served live

The printable HTML written by the CLI lives in `out/cards/honeywell-hpa3000.html`
(byte-identical to the web card route — test-proved).

## Notes

- The live demo's *Mark done* writes shared state — take the screenshots first if you
  want the pristine seeded dates on camera.
- The full scan is 614 s (10:14) — too long for a one-take video. The `--resume` replay
  (3 s) plus-card plus report is the demo; the full run is linked as `out/scan-phase3.txt`.
