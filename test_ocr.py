"""OCR test: render a synthetic slot-list screenshot that mimics the real
game UI, then check the parser recovers slots, players and tags."""

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

from core.ocr_roster import parse_slot_screenshot, suggest_tag

W, H = 1600, 720
FONT_DIR = Path("C:/Windows/Fonts")


def font(size):
    for name in ("bahnschrift.ttf", "arialbd.ttf", "arial.ttf"):
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


TEAMS = {
    15: ["Wz Lynx", "Wz Kuku", "Wz StayHumble", "Wz AyUsh"],
    16: ["SC-MSTRhyunn", "SC-RAMBO", "SC-TOJI", "SC-RealEyesss"],
    17: ["HKKH-De-OggY", "HKKH-MrSpiky", "Different69", "RahulZZ"],
    18: ["SuyogSOLTI", "tantanSOLTI", "Choco Fun", "Ms Harley"],
    19: ["WG-OBITO", "WG-AaaGoo", "WG-RasIL07", "WG-Supreme"],
    20: ["OLDs-Anoopsir", "OLDs-Mizzuu69", "OLDs-PoiZonX", "OLDs-JONyV7"],
    22: ["TLxMijung", "TLxPO1SON", "TLxMarco", "TLxGhyampe"],
    23: ["4GrEAGLE922", "4GrGrooott", "Aeffex4Gr", "Odix4Gr"],
}
SLOT_COLORS = ["#8ab4f8", "#f28bc2", "#4fd8c8", "#e8a24b", "#9ee84b",
               "#b48af8", "#4bc2e8", "#e84b6a"]

img = Image.new("RGB", (W, H), (38, 36, 34))
d = ImageDraw.Draw(img)
# header like the real screenshot
d.text((185, 45), "Remaining", font=font(28), fill="white")
d.text((330, 38), "67", font=font(40), fill="white")
d.text((405, 45), "Team", font=font(28), fill="white")
d.text((480, 38), "17", font=font(40), fill="white")

grid = list(TEAMS.items())
CARD_W, CARD_H = 365, 190
for i, (slot, players) in enumerate(grid):
    col, row = i % 3, i // 3
    x = 185 + col * (CARD_W + 25)
    y = 105 + row * (CARD_H + 16)
    d.rectangle([x, y, x + CARD_W, y + CARD_H], fill=(16, 16, 16))
    d.text((x + 18, y + 12), f"{slot}", font=font(38),
           fill=SLOT_COLORS[i % len(SLOT_COLORS)])
    for j, name in enumerate(players):
        ry = y + 18 + j * 42
        d.text((x + 75, ry), name, font=font(20), fill=(235, 235, 235))
        d.text((x + CARD_W - 115, ry + 2), "/0 Eliminations", font=font(15),
               fill=(150, 150, 150))

path = Path(tempfile.mkdtemp(prefix="pubgm_ocr_")) / "slots.png"
img.save(path)
print(f"synthetic screenshot: {path}")

cards = parse_slot_screenshot(path)
print(f"parsed {len(cards)} cards")
for c in cards:
    print(f"  slot {c['slot']}: {c['players']}  tag={suggest_tag(c['players'])!r}")

assert len(cards) == len(TEAMS), f"expected {len(TEAMS)} cards, got {len(cards)}"
found_slots = [c["slot"] for c in cards]
assert found_slots == sorted(TEAMS), f"slots wrong: {found_slots}"
ok_names = 0
for c in cards:
    expected = TEAMS[c["slot"]]
    assert len(c["players"]) == 4, f"slot {c['slot']}: {c['players']}"
    for got, exp in zip(c["players"], expected):
        if got.replace(" ", "").lower() == exp.replace(" ", "").lower():
            ok_names += 1
total = sum(len(v) for v in TEAMS.values())
print(f"exact name matches: {ok_names}/{total}")
assert ok_names >= total * 0.85, "too many OCR name errors"
assert suggest_tag(TEAMS[15]) == "Wz"
assert suggest_tag(TEAMS[16]) == "SC"
assert suggest_tag(TEAMS[22]) == "TLx"
print("OCR TEST PASSED")


def test_ocr_smoke_script_completed():
    pass
