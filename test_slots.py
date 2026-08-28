"""Offscreen test of the 25-slot team table (dialogs stubbed out)."""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

import app as m

# modal dialogs would block the offscreen test
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

qapp = QApplication.instance() or QApplication(sys.argv)
win = m.MainWindow()
win.show()

t = win.teams_table
assert t.rowCount() == 25, t.rowCount()
assert t.item(0, 0).text() == "1" and t.item(24, 0).text() == "25"
assert not (t.item(0, 0).flags() & Qt.ItemIsEditable), "slot col must be read-only"

saved_teams = win.events.event.get("teams", [])  # restore afterwards

t.setItem(2, 1, QTableWidgetItem("ALPHA ESPORTS"))
t.setItem(2, 2, QTableWidgetItem("ALPHA"))
t.setItem(24, 1, QTableWidgetItem("SLOT25 SQUAD"))
win._save_event()
teams = win.events.event["teams"]
assert teams == [
    {"teamId": 3, "teamName": "ALPHA ESPORTS", "shortName": "ALPHA"},
    {"teamId": 25, "teamName": "SLOT25 SQUAD", "shortName": ""},
], teams

win._reload_event_tab()
assert t.item(2, 1).text() == "ALPHA ESPORTS" and t.item(2, 2).text() == "ALPHA"
assert t.item(24, 1).text() == "SLOT25 SQUAD"

# clear slots and confirm empty save
win._clear_team_slots()
win._save_event()
assert win.events.event["teams"] == []

# restore original event teams
win.events.event["teams"] = saved_teams
win.events.save_event()

QTimer.singleShot(300, qapp.quit)
qapp.exec()
print("SLOT TABLE TEST PASSED")


def test_slots_smoke_script_completed():
    pass
