"""OCR results test: render synthetic post-match rankings screenshots that
mimic the real game UI (left #1/#2 panel + scrolling gold cards, overlapping
pages, a cut-off card), then verify parse -> merge -> roster matching."""

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

from core.ocr_results import (parse_results_screenshot, merge_result_cards,
                              match_cards_to_roster)

W, H = 1600, 720
FONT_DIR = Path("C:/Windows/Fonts")


def font(size):
    for name in ("bahnschrift.ttf", "arialbd.ttf", "arial.ttf"):
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


# rank -> (slot, [(player, kills), ...])
RESULTS = {
    1: (7,  [("GAZIN", 2), ("TC SUJAN", 1), ("S1 MANGO", 8), ("TC DJunG", 0)]),
    2: (3,  [("Saltpapii", 0), ("Ninjapapii", 4), ("Mahaapapii", 1), ("LTG SAMAR", 1)]),
    3: (15, [("MNG I JACKx", 4), ("MNG I SINZOx", 1), ("MNG I ZYREX9", 0), ("MNG I ACEx", 0)]),
    4: (1,  [("SE I KIMMY", 2), ("SE I RanaAR", 0), ("SE I Obito", 0), ("SE I KIYOO", 0)]),
    5: (9,  [("REMAN BOSS", 0), ("KillXFR", 1), ("FANTA OP", 3), ("MundreKO", 0)]),
    6: (2,  [("NPG I PiKA", 0), ("NPG I SHINY", 1), ("NPG I Snoff", 0)]),
    7: (11, [("TR NunniMen", 0), ("ApDr Sythe", 0), ("TR MAAHAAKAAL", 0), ("ApDr FLAWL3SS", 0)]),
    8: (5,  [("BOB HERO", 0), ("BOB VillanV2", 2), ("BOB FIGHTEr", 2), ("BOB NARUTO", 0)]),
    9: (20, [("HTxMRSLAYER", 1), ("HTxASHMIN", 6), ("HTxSNOW", 3), ("HTxBishal", 3)]),
    10: (13, [("90SVkEyYY", 1), ("90sRishab", 2), ("90sAjay", 1), ("90sKAJU", 0)]),
    11: (17, [("XzistDeMonV2", 1), ("XzistToxic", 3), ("XzistSLOW", 1), ("XzistLopshi", 3)]),
}

TEAM_NAMES = {7: "TC OFFICIAL", 3: "PAPII SQUAD", 15: "MNG ESPORTS",
              1: "SE UNITY", 9: "REMAN ARMY", 2: "NPG NEPAL", 11: "TR APDR MIX",
              5: "BOB LEGION", 20: "HT ESPORTS", 13: "90s CREW", 17: "XZIST"}


def elim_text(n):
    return f"{n} elimination" + ("" if n == 1 else "s")


def draw_left_panel(d):
    # 1 card (crown icon, no number)
    d.rectangle([210, 130, 820, 345], fill=(24, 20, 14), outline=(120, 100, 60))
    d.polygon([(238, 250), (250, 205), (262, 232), (274, 205), (286, 250)],
              fill=(212, 175, 55))
    for i, (name, kills) in enumerate(RESULTS[1][1]):
        y = 158 + i * 40
        d.text((340, y), name, font=font(20), fill=(230, 225, 215))
        d.text((790, y + 2), elim_text(kills), font=font(15),
               fill=(170, 160, 140), anchor="ra")
    # 2 card
    d.text((245, 430), "2", font=font(42), fill=(235, 230, 220))
    for i, (name, kills) in enumerate(RESULTS[2][1]):
        y = 388 + i * 40
        d.text((340, y), name, font=font(20), fill=(230, 225, 215))
        d.text((790, y + 2), elim_text(kills), font=font(15),
               fill=(170, 160, 140), anchor="ra")


def draw_right_card(d, top, rank, players, cut_after=None):
    bottom = min(H, top + 160)
    for yy in range(top, bottom):  # simple gold gradient
        t = (yy - top) / 160
        d.line([(840, yy), (1380, yy)],
               fill=(200 - int(40 * t), 165 - int(30 * t), 60))
    d.rectangle([840, top, 1380, bottom], outline=(60, 45, 10))
    if rank is not None:
        d.text((869, top + 56), str(rank), font=font(46), fill="white",
               stroke_width=2, stroke_fill=(60, 45, 10))
    rows = players if cut_after is None else players[:cut_after]
    for i, (name, kills) in enumerate(rows):
        y = top + 20 + i * 38
        if y + 24 > H:
            break
        d.text((955, y), name, font=font(19), fill=(25, 22, 12))
        d.text((1350, y + 3), elim_text(kills), font=font(14),
               fill=(60, 50, 25), anchor="ra")


def make_shot(path, right_cards):
    img = Image.new("RGB", (W, H), (12, 10, 8))
    d = ImageDraw.Draw(img)
    d.text((800, 30), "PUBG", font=font(40), fill=(240, 170, 20), anchor="ma")
    d.text((800, 80), "MOBILE", font=font(22), fill=(240, 170, 20), anchor="ma")
    d.text((1480, 665), "Continue", font=font(22), fill="white", anchor="ma")
    draw_left_panel(d)
    for top, rank, players, cut in right_cards:
        draw_right_card(d, top, rank, players, cut)
    img.save(path)


tmp = Path(tempfile.mkdtemp(prefix="pubgm_res_"))
shots = []
# page 1: ranks 3,4,5
make_shot(tmp / "r1.png", [
    (128, 3, RESULTS[3][1], None),
    (292, 4, RESULTS[4][1], None),
    (456, 5, RESULTS[5][1], None),
])
# page 2: ranks 6,7,8 + rank 9 cut off at the bottom (no number, 2 rows)
make_shot(tmp / "r2.png", [
    (128, 6, RESULTS[6][1], None),
    (292, 7, RESULTS[7][1], None),
    (456, 8, RESULTS[8][1], None),
    (620, None, RESULTS[9][1], 2),
])
# page 3: ranks 9 (complete), 10, 11
make_shot(tmp / "r3.png", [
    (128, 9, RESULTS[9][1], None),
    (292, 10, RESULTS[10][1], None),
    (456, 11, RESULTS[11][1], None),
])

all_cards = []
for f in ("r1.png", "r2.png", "r3.png"):
    cards = parse_results_screenshot(tmp / f)
    print(f"{f}: {len(cards)} cards, ranks {[c['rank'] for c in cards]}")
    all_cards.append(cards)

merged = merge_result_cards(all_cards)
print(f"merged: {len(merged)} cards")

teams = [{"teamId": slot, "teamName": TEAM_NAMES[slot],
          "players": [p for p, _ in players]}
         for slot, players in (RESULTS[r] for r in RESULTS)]
match_cards_to_roster(merged, teams)

ok_slots = 0
for c in merged:
    total = sum(p["kills"] for p in c["players"])
    print(f"  rank {c['rank']}: slot={c['slot']} ({c['teamName']}, "
          f"score {c['matchScore']}) elims={total} players={len(c['players'])}")

assert len(merged) == 11, f"expected 11 cards, got {len(merged)}"
ranks = [c["rank"] for c in merged]
assert ranks == list(range(1, 12)), f"ranks wrong: {ranks}"
for c in merged:
    exp_slot, exp_players = RESULTS[c["rank"]]
    assert c["slot"] == exp_slot, f"rank {c['rank']}: slot {c['slot']} != {exp_slot}"
    assert len(c["players"]) == len(exp_players), \
        f"rank {c['rank']}: {len(c['players'])} players"
    exp_kills = sum(k for _, k in exp_players)
    got_kills = sum(p["kills"] for p in c["players"])
    assert got_kills == exp_kills, \
        f"rank {c['rank']}: kills {got_kills} != {exp_kills}"
print("RESULTS OCR TEST PASSED")

# --- stress: different resolution + JPEG compression --------------------------
src = Image.open(tmp / "r1.png")
big = src.resize((int(W * 1.5), int(H * 1.5)), Image.LANCZOS)
big.save(tmp / "r1_big.jpg", "JPEG", quality=70)
small = src.resize((1280, 576), Image.LANCZOS)
small.save(tmp / "r1_small.jpg", "JPEG", quality=75)

for variant in ("r1_big.jpg", "r1_small.jpg"):
    cards = parse_results_screenshot(tmp / variant)
    ranks = sorted(c["rank"] for c in cards if c["rank"] is not None)
    print(f"{variant}: ranks {ranks}")
    assert ranks == [1, 2, 3, 4, 5], f"{variant}: {ranks}"
    for c in cards:
        if c["rank"] in (3, 4, 5):
            exp = sum(k for _, k in RESULTS[c["rank"]][1])
            got = sum(p["kills"] for p in c["players"])
            assert got == exp, f"{variant} rank {c['rank']}: {got} != {exp}"
print("STRESS TEST PASSED (resolution + JPEG)")

# --- name matching stress: symbols and OCR-confused characters ---------------
noisy_cards = [
    {"rank": 1, "players": [
        {"name": "TLxP01S0N", "kills": 4},
        {"name": "TLx Marco", "kills": 1},
        {"name": "TLx Ghyanpe", "kills": 0},
    ]},
    {"rank": 2, "players": [
        {"name": "SC\u2605MSTRhyunn", "kills": 2},
        {"name": "SC RAMB0", "kills": 1},
        {"name": "SC-T0JI", "kills": 1},
    ]},
    {"rank": 3, "players": [
        {"name": "MNG I JACKx", "kills": 3},
        {"name": "MNG l SINZOx", "kills": 1},
    ]},
]
noisy_teams = [
    {"teamId": 22, "teamName": "TLX", "players": [
        "TLxMijung", "TLxPO1SON", "TLxMarco", "TLxGhyampe"]},
    {"teamId": 16, "teamName": "SC", "players": [
        "SC-MSTRhyunn", "SC-RAMBO", "SC-TOJI", "SC-RealEyesss"]},
    {"teamId": 15, "teamName": "MNG", "players": [
        "MNG JACKx", "MNG SINZOx", "MNG ZYREX9", "MNG ACEx"]},
]
match_cards_to_roster(noisy_cards, noisy_teams)
assert [c["slot"] for c in noisy_cards] == [22, 16, 15], noisy_cards
print("NOISY NAME MATCH TEST PASSED")


def test_ocr_results_smoke_script_completed():
    pass
