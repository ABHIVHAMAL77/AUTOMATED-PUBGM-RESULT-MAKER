"""Offscreen test: roster table fill, apply to event, and save preservation."""

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

saved_teams = [dict(t) for t in win.events.event.get("teams", [])]

cards = [
    {"slot": 15, "players": ["Wz Lynx", "Wz Kuku", "Wz StayHumble", "Wz AyUsh"]},
    {"slot": 16, "players": ["SC-MSTRhyunn", "SC-RAMBO", "SC-TOJI", "SC-RealEyesss"]},
    {"slot": None, "players": ["TLxMijung", "TLxPO1SON", "TLxMarco", "TLxGhyampe"]},
]
win._add_roster_cards(cards)
assert win.roster_table.rowCount() == 3

# loading the same slot again must replace, not duplicate
win._add_roster_cards([{"slot": 15, "players": ["Wz Lynx", "Wz Kuku",
                                                "Wz StayHumble", "Wz AyUsh"]}])
assert win.roster_table.rowCount() == 3, win.roster_table.rowCount()

# operator fixes the missing slot number by hand
for row in range(win.roster_table.rowCount()):
    if not win.roster_table.item(row, 0).text().strip():
        win.roster_table.setItem(row, 0, QTableWidgetItem("22"))

win._apply_roster_to_event()
teams = {t["teamId"]: t for t in win.events.event["teams"]}
assert 15 in teams and 16 in teams and 22 in teams, sorted(teams)
assert teams[15]["players"] == ["Wz Lynx", "Wz Kuku", "Wz StayHumble", "Wz AyUsh"]
assert teams[15]["shortName"] == "Wz"
assert teams[16]["shortName"] == "SC"
assert teams[22]["players"][0] == "TLxMijung"

# editing a name on the Event Setup tab must NOT lose the players list
win._reload_event_tab()
win.teams_table.setItem(14, 1, QTableWidgetItem("WOLVES OFFICIAL"))
win._save_event()
teams = {t["teamId"]: t for t in win.events.event["teams"]}
assert teams[15]["teamName"] == "WOLVES OFFICIAL"
assert teams[15]["players"] == ["Wz Lynx", "Wz Kuku", "Wz StayHumble", "Wz AyUsh"]

# restore whatever the user had before the test
win.events.event["teams"] = saved_teams
win.events.save_event()

QTimer.singleShot(300, qapp.quit)
qapp.exec()
print("ROSTER GUI TEST PASSED")


def test_roster_gui_smoke_script_completed():
    pass
