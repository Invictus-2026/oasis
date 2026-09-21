#!/usr/bin/env bash
# OASIS health check.
#
#   ./scripts/check.sh              verify everything
#   ./scripts/check.sh --serve      verify, then start both dev servers
#
# Exits non-zero if anything required is broken. In Phase 8 this becomes the
# pre-demo checklist.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PY=backend/.venv/bin/python
PASS=0; FAIL=0; WARN=0

g() { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
r() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
y() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=$((WARN+1)); }
h() { printf "\n\033[1m%s\033[0m\n" "$1"; }

h "Toolchain"
[ -x "$PY" ] && g "backend venv ($($PY --version 2>&1))" || r "backend venv missing — see README quick start"
[ -d frontend/node_modules ] && g "frontend deps installed" || r "frontend deps missing — cd frontend && npm install"

h "Case bundle"
if [ -f data/case/case.json ]; then
  $PY - <<'PY'
import json, pathlib
m = json.loads(pathlib.Path("data/case/case.json").read_text())
real = [s for s in m["sources"] if not s["is_synthetic"]]
syn  = [s for s in m["sources"] if s["is_synthetic"]]
print(f"  \033[32m✓\033[0m case {m['id']}: {len(real)} real, {len(syn)} synthesised inputs")
for s in real: print(f"      real   {s['name'][:66]}")
for s in syn:  print(f"      synth  {s['name'][:66]}")
gt = m["ground_truth"]
print(f"  \033[32m✓\033[0m ground truth: {gt['polluter_name']} ({gt['polluter_mmsi']}) "
      f"@ {gt['origin'][0]:.4f},{gt['origin'][1]:.4f}")
print(f"  \033[32m✓\033[0m slick {m['slick']['area_km2']:.1f} km2, bearing {m['slick']['orientation_deg']:.0f} deg")
PY
else
  r "case bundle missing — run: $PY scripts/build_case.py"
fi

h "Tests"
if [ -x "$PY" ]; then
  OUT=$(cd backend && ../$PY -m pytest -q 2>&1 | tail -1)
  echo "$OUT" | grep -qE "^[0-9]+ (passed|passed,)" && g "pytest: $OUT" || r "pytest: $OUT"
else
  r "cannot run tests, no venv"
fi

h "Frontend typecheck"
if [ -d frontend/node_modules ]; then
  if (cd frontend && npx tsc --noEmit 2>&1 | head -5) | grep -q .; then
    r "typecheck failed — run: cd frontend && npx tsc --noEmit"
  else
    g "no type errors"
  fi
fi

h "API"
if curl -sf -m 3 localhost:8000/health >/dev/null 2>&1; then
  g "backend up on :8000"
  for ep in "GET /api/case" "POST /api/detect" "POST /api/drift/hindcast" \
            "POST /api/drift/forecast" "POST /api/attribute" "GET /api/pipeline/run"; do
    m=${ep%% *}; u=${ep##* }
    if [ "$m" = GET ]; then
      code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "localhost:8000$u")
    else
      body='{"slick_id":"slick-001","method":"classical","origin":[-90.0777,28.5267],"origin_time_utc":"2023-06-15T04:00:00Z"}'
      code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -X POST "localhost:8000$u" \
             -H 'Content-Type: application/json' -d "$body")
    fi
    [ "$code" = 200 ] && g "$ep → $code" || r "$ep → $code"
  done
else
  y "backend not running — start it with: ./scripts/check.sh --serve"
fi

if curl -sf -m 3 -o /dev/null localhost:5173/ 2>/dev/null; then
  g "frontend up on :5173"
  curl -sf -m 5 localhost:5173/api/case >/dev/null 2>&1 \
    && g "vite → backend proxy works" || y "proxy not reaching backend"
else
  y "frontend not running"
fi

h "Render"
if curl -sf -m 3 -o /dev/null localhost:5173/ 2>/dev/null; then
  if ./scripts/shot.sh .run/ui.png; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
else
  y "frontend not running, skipping render check"
fi

h "Background download"
F=data/raw/02_Test_images_and_ground_truth.7z
if [ -f "$F" ]; then
  S=$(stat -c%s "$F"); T=9859650011
  printf "  \033[33m!\033[0m Zenodo Part II: %.2f / 9.86 GB (%.1f%%)\n" \
    "$(echo "$S/1073741824" | bc -l)" "$(echo "$S*100/$T" | bc -l)"
  pgrep -f fetch_zenodo_test >/dev/null \
    && echo "      still downloading" \
    || echo "      stalled — resume: nohup data/raw/fetch_zenodo_test.sh &"
  [ "$S" -ge "$T" ] && echo "      COMPLETE — extract, then re-run build_case.py for real imagery"
fi

h "Summary"
printf "  %d passed, %d failed, %d warnings\n" "$PASS" "$FAIL" "$WARN"

if [ "${1:-}" = "--serve" ]; then
  h "Starting servers"
  mkdir -p .run
  # setsid + nohup so the servers outlive this shell. A plain "&" leaves them
  # as children that die when the invoking shell exits.
  pkill -f "uvicorn app.main" 2>/dev/null; pkill -f "vite" 2>/dev/null; sleep 1
  setsid nohup env -C "$ROOT/backend" "$ROOT/$PY" -m uvicorn app.main:app --port 8000 \
    > .run/backend.log 2>&1 < /dev/null &
  echo "  backend  pid $! → .run/backend.log"
  setsid nohup env -C "$ROOT/frontend" npm run dev \
    > .run/frontend.log 2>&1 < /dev/null &
  echo "  frontend pid $! → .run/frontend.log"
  sleep 6
  curl -sf -m 3 localhost:8000/health >/dev/null && g "backend ready" || r "backend failed, see .run/backend.log"
  curl -sf -m 3 -o /dev/null localhost:5173/ && g "frontend ready" || r "frontend failed, see .run/frontend.log"
  printf "\n  Open \033[36mhttp://localhost:5173\033[0m\n"
  printf "  Stop with: pkill -f 'uvicorn app.main' ; pkill -f 'vite'\n\n"
fi

[ "$FAIL" -eq 0 ]
