"""Offscreen test: OCR results table -> save as match result end-to-end."""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

import app as m

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

qapp = QApplication.instance() or QApplication(sys.argv)
win = m.MainWindow()
win.show()

TEST_MATCH = 98  # away from real data; deleted at the end

cards = [
    {"rank": 1, "slot": 7, "teamName": "TC OFFICIAL", "matchScore": 1.0,
     "players": [{"name": "GAZIN", "kills": 2}, {"name": "TC SUJAN", "kills": 1},
                 {"name": "S1 MANGO", "kills": 8}, {"name": "TC DJunG", "kills": 0}]},
    {"rank": 2, "slot": 3, "teamName": "PAPII SQUAD", "matchScore": 0.95,
     "players": [{"name": "Saltpapii", "kills": 0}, {"name": "Ninjapapii", "kills": 4}]},
    {"rank": None, "slot": None, "teamName": "", "matchScore": 0.0,
     "players": [{"name": "MNG JACKx", "kills": 4}]},
]
win._fill_result_table(cards)
assert win.result_ocr_table.rowCount() == 3

# saving with missing rank/slot must be blocked (warning, no save)
before = set(win.events.list_match_numbers())
win.ocr_match_spin.setValue(TEST_MATCH)
win._save_ocr_match()
assert set(win.events.list_match_numbers()) == before, "should not have saved"

# operator fills in the missing rank + slot
win.result_ocr_table.setItem(2, 0, QTableWidgetItem("3"))
win.result_ocr_table.setItem(2, 1, QTableWidgetItem("15"))
win.result_ocr_table.setItem(2, 2, QTableWidgetItem("MNG ESPORTS"))
win._save_ocr_match()

match = win.events.load_match(TEST_MATCH)
assert match is not None, "match not saved"
res = match["results"]
assert [r["placement"] for r in res] == [1, 2, 3]
assert res[0]["teamId"] == 7 and res[0]["wwcd"] is True
assert res[0]["kills"] == 11 and res[0]["placementPoints"] == 10
assert res[0]["totalPoints"] == 21
assert res[1]["kills"] == 4 and res[1]["placementPoints"] == 6
assert res[2]["teamName"] == "MNG ESPORTS" and res[2]["placementPoints"] == 5
assert res[0]["players"][2]["playerName"] == "S1 MANGO"
assert res[0]["players"][2]["kills"] == 8

# player stats must include OCR players
stats = {p["playerName"]: p for p in win.events.player_stats()}
assert "S1 MANGO" in stats and stats["S1 MANGO"]["kills"] >= 8

# clean up the test match
win.events.delete_match(TEST_MATCH)
from core.sheet_export import export_tournament_sheet
export_tournament_sheet(win.events)
win._reload_results_tab()

QTimer.singleShot(300, qapp.quit)
qapp.exec()
print("RESULTS GUI TEST PASSED")


def test_results_gui_smoke_script_completed():
    pass
