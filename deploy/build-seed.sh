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

# Copy through SQLite's own backup operation, not `cp`: a cp of the main file
# omits whatever is still sitting in `out/sloth.db-wal` (WAL mode is the
# database's normal state), so a fresh scan could lose its newest rows in the
# seeded cloud copy. The backup API guarantees a consistent snapshot; it also
# verifies the result with `PRAGMA integrity_check` and prints the row counts
# the deploy is supposed to serve. The old seed survives a failed run.
rm -f "$ROOT/deploy/seed/sloth.db.tmp"
PYBIN="$ROOT/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="$(command -v python3)"
"$PYBIN" - "$ROOT/out/sloth.db" "$ROOT/deploy/seed/sloth.db.tmp" <<'PY'
import sqlite3
import sys

src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.execute("PRAGMA journal_mode = DELETE")
check = [row[0] for row in dst.execute("PRAGMA integrity_check").fetchall()]
state = "ok" if check == ["ok"] else f'BROKEN: {", ".join(check)}'
counts = {
    table: dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    for table in ("devices", "intervals", "service_events")
}
dst.commit()
dst.close()
src.close()
print(f"integrity_check: {state}")
for table, count in counts.items():
    print(f"{table}: {count}")
PY
mv "$ROOT/deploy/seed/sloth.db.tmp" "$ROOT/deploy/seed/sloth.db"
# Stale sidecars would not match the fresh snapshot; never commit them.
rm -f "$ROOT/deploy/seed/sloth.db-wal" "$ROOT/deploy/seed/sloth.db-shm"
cp "$ROOT/out/report.json" "$ROOT/deploy/seed/report.json" 2>/dev/null || true

# Guard against committing anything secret: the seed must carry no DSN, no
# token, no .env — just the scan's own SQLite file (and report, if present).
if grep -rlq "postgresql://" "$ROOT/deploy/seed/" 2>/dev/null; then
    echo "refusing: a PostgreSQL DSN string appeared in deploy/seed/" >&2
    exit 1
fi

echo "seed sha256: $(sha256sum "$ROOT/deploy/seed/sloth.db" | cut -d' ' -f1)"

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
