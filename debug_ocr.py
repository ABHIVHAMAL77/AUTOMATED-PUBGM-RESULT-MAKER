import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from core.ocr_roster import ocr_boxes

boxes, w, h = ocr_boxes(sys.argv[1])
print(f"image {w}x{h}, {len(boxes)} boxes")
for b in sorted(boxes, key=lambda b: (round(b.y0 / 20), b.x0)):
    print(f"  x0={b.x0:6.0f} y0={b.y0:6.0f} h={b.h:5.1f} conf={b.score:.2f}  {b.text!r}")
