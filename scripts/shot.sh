#!/usr/bin/env bash
# Headless render smoke test.
#
#   ./scripts/shot.sh [out.png]
#
# Catches the failure mode automated checks miss entirely: the app serves 200,
# every endpoint answers, typecheck is clean, and the map is a blank rectangle.
# That happened once already — an explicit `glyphs: undefined` in the style spec
# failed validation, so MapLibre never fired "load" and never painted.
#
# Asserts the map canvas actually rendered the style background rather than
# letting the page background show through.

set -uo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-.run/ui.png}"
URL="${URL:-http://localhost:5173/}"
PY=backend/.venv/bin/python

BROWSER=$(command -v chromium || command -v chromium-browser || command -v google-chrome-stable || true)
[ -z "$BROWSER" ] && { echo "no chromium found, skipping render check"; exit 0; }

mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
timeout 90 "$BROWSER" --headless --disable-gpu --no-sandbox --enable-unsafe-swiftshader \
  --hide-scrollbars --virtual-time-budget=15000 --window-size=1600,900 \
  --screenshot="$OUT" "$URL" >/dev/null 2>&1

[ -f "$OUT" ] || { echo "  ✗ screenshot failed"; exit 1; }

"$PY" - "$OUT" <<'PY'
import sys
from PIL import Image

im = Image.open(sys.argv[1]).convert("RGB")
w, h = im.size
MAP_BG = (10, 21, 38)     # the style's background-color, when no imagery is loaded
PAGE_BG = (7, 11, 18)     # ink-950; seeing this in the map pane means blank

samples = [im.getpixel(p) for p in ((400, 300), (600, 500), (300, 700), (800, 400))]
ok = sum(1 for s in samples if s != PAGE_BG)

def near(a, b, tol=6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))

# The SAR overlay paints a blue-steel sea over the style background, so a
# painted map is either the flat background OR imagery sitting above it.
def is_sar(c):
    r, g, b = c
    return b > r and 25 < b < 210 and g >= r

if ok == 0:
    print(f"  \033[31m✗\033[0m map pane is blank — canvas never painted (all samples {PAGE_BG})")
    sys.exit(1)
if any(is_sar(s) for s in samples):
    print(f"  \033[32m✓\033[0m SAR overlay rendered ({ok}/{len(samples)} samples painted)")
elif any(near(s, MAP_BG) for s in samples):
    print(f"  \033[33m!\033[0m map painted but no SAR imagery — overlay may have failed to load")
else:
    print(f"  \033[33m!\033[0m map painted, unexpected colours: {samples[:2]}")

# The slick is amber; if detection warm-start worked it should be on screen.
px = im.load()
amber = sum(
    1 for y in range(80, h, 3) for x in range(0, 1200, 3)
    if px[x, y][0] > 120 and px[x, y][1] > 70 and px[x, y][2] < 90
)
if amber > 40:
    print(f"  \033[32m✓\033[0m slick rendered ({amber} amber pixels)")
else:
    print(f"  \033[33m!\033[0m no slick on the map ({amber} amber pixels) — warm-start detection may have failed")
PY
code=$?
echo "  screenshot: $OUT"
exit $code
