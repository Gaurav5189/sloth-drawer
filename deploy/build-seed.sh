#!/usr/bin/env sh
# Refresh the committed deploy seed from the local scan state.
#
# The container serves `out/sloth.db` exactly as your last local `scan` wrote
# it — the deploy shows the machine's real verified intervals, not a copy the
# cloud re-derived. Run this (and commit) whenever a scan produced new state
# you want on the demo:
#
#     uv run sloth-drawer index data/manuals    # optional: refresh the cloud index
#     deploy/build-seed.sh && git add deploy/seed && git commit
#
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$ROOT/out/sloth.db" ]; then
    echo "out/sloth.db not found — run \`sloth-drawer scan <dir>\` first." >&2
    exit 2
fi

mkdir -p "$ROOT/deploy/seed"
cp "$ROOT/out/sloth.db" "$ROOT/deploy/seed/sloth.db"
cp "$ROOT/out/report.json" "$ROOT/deploy/seed/report.json" 2>/dev/null || true

# Guard against committing anything secret: the seed must carry no DSN, no
# token, no .env — just the scan's own SQLite file (and report, if present).
if grep -rlq "postgresql://" "$ROOT/deploy/seed/" 2>/dev/null; then
    echo "refusing: a PostgreSQL DSN string appeared in deploy/seed/" >&2
    exit 1
fi

sha256sum "$ROOT/out/sloth.db" "$ROOT/deploy/seed/sloth.db"
echo "Seed refreshed (data/ and deploy/ only — the manuals are never shipped)."
