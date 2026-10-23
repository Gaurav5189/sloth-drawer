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

# The 2026-10-23 Render failure class: a global .gitignore rule (*.db) can
# silently swallow the seed, and the deploy then fails with "not found" in its
# build context. Fail HERE, loudly, if the seed is ignored or not tracked.
if git -C "$ROOT" check-ignore -q deploy/seed/sloth.db 2>/dev/null; then
    echo "refusing: deploy/seed/sloth.db is still gitignored (check .gitignore)" >&2
    exit 1
fi
if ! git -C "$ROOT" ls-files --error-unmatch deploy/seed/sloth.db >/dev/null 2>&1; then
    echo "NOT yet committed: run  git add deploy/seed/sloth.db && git commit" >&2
    exit 1
fi

echo "Seed refreshed, tracked, and DSN-free (data/ and deploy/ only — the manuals are never shipped)."
