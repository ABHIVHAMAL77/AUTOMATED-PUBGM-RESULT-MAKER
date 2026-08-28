"""PUBGM Results Engine — automatic match results calculator.

Mode 1 (this version): live PUBG Mobile observer API polling, elimination
tracking, point calculation, event standings, and PNG result graphics.
Mode 2 (planned): OCR from Observe/Rank screenshots — see the Screenshot tab.

Run:  python app.py
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QListWidget, QMessageBox,
    QHeaderView, QGroupBox, QAbstractItemView, QFileDialog, QDialog,
    QInputDialog,
)

from core.api_client import ApiPoller, STATUS_LIVE, STATUS_MOCK, STATUS_ERROR
from core.match_tracker import MatchTracker
from core.event_manager import EventManager
from core.scoring import DEFAULT_POINT_SYSTEM
from core import result_graphic
from core.sheet_export import export_tournament_sheet
from core.auth import AuthManager, AuthError, ROLE_ADMIN, ROLE_OPERATOR
from core.remote_auth import RemoteAuthManager, configured_license_server_url

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "apiUrl": "http://127.0.0.1:10086/gettotalplayerlist",
    "pollingInterval": 2,
    "mockMode": True,
    "licenseServerUrl": "",
}

MAPS = ["Erangel", "Miramar", "Sanhok", "Vikendi", "Rondo", "Karakin", "Livik"]

DARK_STYLE = """
QMainWindow, QWidget { background-color: #14181f; color: #e8ebf0; font-size: 14px; }
QTabWidget::pane { border: 1px solid #2a3140; border-radius: 4px; }
QTabBar::tab { background: #1c222c; color: #aeb6c4; padding: 10px 24px; font-size: 15px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #2a3140; color: #e8be52; font-weight: bold; }
QGroupBox { border: 1px solid #2a3140; border-radius: 6px; margin-top: 12px; padding-top: 10px;
            font-weight: bold; color: #e8be52; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton { background: #2a3140; border: 1px solid #3a4356; border-radius: 6px;
              padding: 9px 18px; color: #e8ebf0; font-size: 14px; }
QPushButton:hover { background: #364057; border-color: #e8be52; }
QPushButton:pressed { background: #1c222c; }
QPushButton:disabled { color: #616a7a; background: #1a1f28; }
QPushButton#primary { background: #e8be52; color: #14181f; font-weight: bold; }
QPushButton#primary:hover { background: #f2cf70; }
QPushButton#danger { background: #7a2e2e; }
QLineEdit, QSpinBox, QComboBox { background: #1c222c; border: 1px solid #3a4356;
    border-radius: 5px; padding: 7px; color: #e8ebf0; font-size: 14px; }
QComboBox QAbstractItemView { background: #ffffff; color: #000000; font-size: 15px;
    selection-background-color: #e8be52; selection-color: #000000; }
QTableWidget { background: #181d26; alternate-background-color: #1c222c; gridline-color: #2a3140;
    border: 1px solid #2a3140; border-radius: 4px; font-size: 14px; }
QHeaderView::section { background: #232a37; color: #e8be52; padding: 8px; border: none;
    font-weight: bold; font-size: 13px; }
QListWidget { background: #181d26; border: 1px solid #2a3140; border-radius: 4px; font-size: 15px; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background: #e8be52; color: #14181f; }
QCheckBox { spacing: 8px; }
QLabel#status_live { color: #5fd47a; font-weight: bold; }
QLabel#status_mock { color: #e8be52; font-weight: bold; }
QLabel#status_err { color: #e06c6c; font-weight: bold; }
"""


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_SETTINGS.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


class FirstRunDialog(QDialog):
    """Shown when no accounts exist yet: create the admin account."""

    def __init__(self, auth: AuthManager):
        super().__init__()
        self.auth = auth
        self.user = None
        self.setWindowTitle("PUBGM Results Engine — First Run Setup")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<h2>Create your Admin account</h2>"
            "<p>This account has full access: event setup, exports, deleting "
            "matches and managing operator accounts. Remember the password — "
            "there is no recovery.</p>"))
        form = QGridLayout()
        form.addWidget(QLabel("Admin username:"), 0, 0)
        self.username_edit = QLineEdit()
        form.addWidget(self.username_edit, 0, 1)
        form.addWidget(QLabel("Password:"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.password_edit, 1, 1)
        form.addWidget(QLabel("Confirm password:"), 2, 0)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.confirm_edit, 2, 1)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("status_err")
        layout.addWidget(self.error_label)
        create_btn = QPushButton("Create Admin Account")
        create_btn.setObjectName("primary")
        create_btn.clicked.connect(self._create)
        layout.addWidget(create_btn)
        self.confirm_edit.returnPressed.connect(self._create)

    def _create(self):
        if self.password_edit.text() != self.confirm_edit.text():
            self.error_label.setText("Passwords do not match.")
            return
        try:
            self.auth.add_user(self.username_edit.text(),
                               self.password_edit.text(), ROLE_ADMIN)
        except AuthError as e:
            self.error_label.setText(str(e))
            return
        self.user = self.auth.verify(self.username_edit.text(),
                                     self.password_edit.text())
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, auth):
        super().__init__()
        self.auth = auth
        self.user = None
        self.setWindowTitle("PUBGM Results Engine — Login")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>🔒 PUBGM Results Engine</h2>"))
        hint = getattr(auth, "login_hint", "")
        if hint:
            help_label = QLabel(hint)
            help_label.setWordWrap(True)
            layout.addWidget(help_label)
        form = QGridLayout()
        form.addWidget(QLabel(getattr(auth, "login_label", "Username:")), 0, 0)
        self.username_edit = QLineEdit()
        form.addWidget(self.username_edit, 0, 1)
        form.addWidget(QLabel("Password:"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.password_edit, 1, 1)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setObjectName("status_err")
        layout.addWidget(self.error_label)
        login_btn = QPushButton("Log In")
        login_btn.setObjectName("primary")
        login_btn.clicked.connect(self._login)
        layout.addWidget(login_btn)
        self.password_edit.returnPressed.connect(self._login)
        self.username_edit.setFocus()

    def _login(self):
        user = self.auth.verify(self.username_edit.text(), self.password_edit.text())
        if user is None:
            msg = getattr(self.auth, "last_error", "") or "Wrong username or password."
            self.error_label.setText(msg)
            self.password_edit.clear()
            return
        self.user = user
        self.accept()


class MainWindow(QMainWindow):
    MAX_SLOTS = 25  # slot number = API team ID

    def __init__(self, user: dict | None = None, auth: "AuthManager | None" = None):
        super().__init__()
        # user is always provided by main(); the default keeps tests simple
        self.user = user or {"username": "admin", "role": ROLE_ADMIN}
        self.auth = auth
        self.is_admin = self.user.get("role") == ROLE_ADMIN
        self.wants_logout = False
        self.setWindowTitle(
            f"PUBGM Results Engine — {self.user['username']} ({self.user['role']})")
        self.resize(1380, 860)

        self.settings = load_settings()
        self.events = EventManager(DATA_DIR)
        self.tracker = MatchTracker()
        self.poller = ApiPoller(
            self.settings["apiUrl"],
            self.settings["pollingInterval"],
            self.settings["mockMode"],
        )
        self._match_over_notified = False

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_live_tab(), "Live Match")
        event_tab = self._build_event_tab()  # always built (widgets are shared)
        if self.is_admin:
            self.tabs.addTab(event_tab, "Event Setup")
        self.tabs.addTab(self._build_results_tab(), "Results && Export")
        self.tabs.addTab(self._build_player_stats_tab(), "Player Stats")
        self.tabs.addTab(self._build_ocr_tab(), "Screenshot OCR")
        if self.is_admin and self.auth is not None:
            self.tabs.addTab(self._build_admin_tab(), "🔑 Admin Panel")

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        top = QHBoxLayout()
        role_icon = "🔑" if self.is_admin else "👤"
        top.addWidget(QLabel(
            f"{role_icon} Logged in as <b>{self.user['username']}</b> "
            f"({self.user['role']})"))
        top.addStretch()
        logout_btn = QPushButton("Log Out")
        logout_btn.clicked.connect(self._logout)
        top.addWidget(logout_btn)
        root.addLayout(top)
        root.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(central)

        if not self.is_admin:
            self._apply_operator_restrictions()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh_live)
        self.ui_timer.start(1000)

        self._reload_event_tab()
        self._reload_results_tab()

    def _logout(self):
        self.wants_logout = True
        self.close()

    def closeEvent(self, event):  # noqa: N802 (Qt naming)
        self.poller.stop()
        super().closeEvent(event)

    def _apply_operator_restrictions(self):
        """Operators may run matches and save results — nothing else."""
        for btn in (self.export_match_btn, self.export_overall_btn,
                    self.sheet_btn, self.open_exports_btn,
                    self.del_match_btn, self.roster_apply_btn):
            btn.setEnabled(False)
            btn.setToolTip("Admin only")

    # ------------------------------------------------------------------ LIVE
    def _build_live_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        conn = QGroupBox("Connection")
        cg = QGridLayout(conn)
        cg.addWidget(QLabel("Observer API URL:"), 0, 0)
        self.api_url_edit = QLineEdit(self.settings["apiUrl"])
        cg.addWidget(self.api_url_edit, 0, 1, 1, 3)
        cg.addWidget(QLabel("Poll every (sec):"), 1, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 30)
        self.interval_spin.setValue(int(self.settings["pollingInterval"]))
        cg.addWidget(self.interval_spin, 1, 1)
        self.mock_check = QCheckBox("Mock mode (fake match for testing, no API needed)")
        self.mock_check.setChecked(bool(self.settings["mockMode"]))
        cg.addWidget(self.mock_check, 1, 2, 1, 2)

        self.start_btn = QPushButton("▶  Start Polling")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._toggle_polling)
        cg.addWidget(self.start_btn, 2, 0)
        self.status_label = QLabel("Stopped")
        cg.addWidget(self.status_label, 2, 1)
        self.update_label = QLabel("Last update: —")
        cg.addWidget(self.update_label, 2, 2)
        self.alive_label = QLabel("Teams alive: —")
        cg.addWidget(self.alive_label, 2, 3)
        layout.addWidget(conn)

        match_box = QGroupBox("Current Match")
        mg = QHBoxLayout(match_box)
        mg.addWidget(QLabel("Match #:"))
        self.match_spin = QSpinBox()
        self.match_spin.setRange(1, 99)
        self.match_spin.setValue(self.events.next_match_number())
        mg.addWidget(self.match_spin)
        self.match_progress_label = QLabel("")
        mg.addWidget(self.match_progress_label)
        mg.addWidget(QLabel("Map:"))
        self.map_combo = QComboBox()
        self.map_combo.addItems(MAPS)
        mg.addWidget(self.map_combo)
        mg.addStretch()
        self.reset_btn = QPushButton("Reset Match Tracking")
        self.reset_btn.clicked.connect(self._reset_tracker)
        mg.addWidget(self.reset_btn)
        self.finalize_btn = QPushButton("✔  Finalize && Save Match Result")
        self.finalize_btn.setObjectName("primary")
        self.finalize_btn.clicked.connect(self._finalize_match)
        mg.addWidget(self.finalize_btn)
        layout.addWidget(match_box)

        self.live_table = QTableWidget(0, 7)
        self.live_table.setHorizontalHeaderLabels(
            ["Rank", "Team", "Alive", "Elims", "Place Pts", "Elim Pts", "Total"])
        self.live_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.live_table.verticalHeader().setVisible(False)
        self.live_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.live_table.setAlternatingRowColors(True)
        layout.addWidget(self.live_table, stretch=1)
        return w

    def _toggle_polling(self):
        if self.poller.running:
            self.poller.stop()
            self.start_btn.setText("▶  Start Polling")
            return
        # apply connection settings
        self.settings["apiUrl"] = self.api_url_edit.text().strip()
        self.settings["pollingInterval"] = self.interval_spin.value()
        self.settings["mockMode"] = self.mock_check.isChecked()
        save_settings(self.settings)
        self.poller.api_url = self.settings["apiUrl"]
        self.poller.interval = self.settings["pollingInterval"]
        self.poller.mock_mode = self.settings["mockMode"]
        self._reset_tracker()
        self.poller.start()
        self.start_btn.setText("■  Stop Polling")

    def _reset_tracker(self):
        self.tracker.reset()
        self._match_over_notified = False
        if self.poller.mock_mode:
            self.poller._mock.reset()
        self.live_table.setRowCount(0)

    def _refresh_live(self):
        snap, status, last_update, error = self.poller.latest()
        if status == STATUS_LIVE:
            self.status_label.setText("● LIVE — API connected")
            self.status_label.setObjectName("status_live")
        elif status == STATUS_MOCK:
            self.status_label.setText("● MOCK DATA")
            self.status_label.setObjectName("status_mock")
        elif status == STATUS_ERROR:
            self.status_label.setText(f"● API ERROR — {error[:60]}")
            self.status_label.setObjectName("status_err")
        else:
            self.status_label.setText("Stopped")
            self.status_label.setObjectName("")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        if last_update:
            ago = int(time.time() - last_update)
            self.update_label.setText(f"Last update: {ago}s ago")

        if snap is None or not self.poller.running:
            return

        self.tracker.update(snap.team_states())
        self.alive_label.setText(f"Teams alive: {self.tracker.alive_team_count}")

        results = self.tracker.build_results(
            self.events.event.get("pointSystem", DEFAULT_POINT_SYSTEM),
            self.events.team_name_overrides(),
        )
        self._fill_live_table(results)

        if self.tracker.is_match_over and not self._match_over_notified:
            self._match_over_notified = True
            reply = QMessageBox.question(
                self, "Match Ended",
                "Only one team is left alive — the match looks finished.\n\n"
                f"Save this as Match {self.match_spin.value()} "
                f"({self.map_combo.currentText()})?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._finalize_match()

    def _fill_live_table(self, results: list):
        alive_ids = {tid for tid, st in self.tracker.latest_states.items() if st.alive_count > 0}
        self.live_table.setRowCount(len(results))
        for row, r in enumerate(results):
            alive_n = self.tracker.latest_states[r["teamId"]].alive_count
            values = [f"#{r['placement']}", r["teamName"], str(alive_n),
                      str(r["kills"]), str(r["placementPoints"]),
                      str(r["killPoints"]), str(r["totalPoints"])]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col != 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if r["teamId"] not in alive_ids:
                    item.setForeground(QColor("#6a7385"))
                elif r["placement"] == 1:
                    item.setForeground(QColor("#e8be52"))
                if col == 6:
                    f = QFont()
                    f.setBold(True)
                    item.setFont(f)
                self.live_table.setItem(row, col, item)

    def _finalize_match(self):
        if not self.tracker.seen_any_data:
            QMessageBox.warning(self, "No Data",
                                "No match data received yet. Start polling first.")
            return
        results = self.tracker.build_results(
            self.events.event.get("pointSystem", DEFAULT_POINT_SYSTEM),
            self.events.team_name_overrides(),
        )
        num = self.match_spin.value()
        if self.events.load_match(num):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Match {num} already has a saved result. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self._persist_match(num, self.map_combo.currentText(), results)
        self.match_spin.setValue(self.events.next_match_number())

    def _persist_match(self, num: int, map_name: str, results: list):
        """Shared save path for API mode and OCR mode: write the match file,
        rebuild the tournament sheet + CSVs, refresh every tab."""
        path = self.events.save_match_result(num, map_name, results)
        sheet_msg = ""
        try:
            sheet_path = export_tournament_sheet(self.events)
            sheet_msg = f"\nTournament sheet auto-updated:\n{sheet_path}"
        except Exception as e:  # noqa: BLE001 — export must never block saving
            sheet_msg = f"\nSheet export failed: {e}"
        self._reload_results_tab()
        played = len(self.events.list_match_numbers())
        total = int(self.events.event.get("totalMatches", 0) or 0)
        QMessageBox.information(
            self, "Saved",
            f"Match {num} result saved ({played} of {total} matches played):\n{path}\n"
            f"{sheet_msg}\n\n"
            "Standings, player stats and CSVs are already updated.\n"
            "Use the 'Results & Export' tab for the PNG graphic.")

    # ----------------------------------------------------------------- EVENT
    def _build_event_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QGroupBox("Event")
        ig = QGridLayout(info)
        ig.addWidget(QLabel("Event name:"), 0, 0)
        self.event_name_edit = QLineEdit()
        ig.addWidget(self.event_name_edit, 0, 1)
        ig.addWidget(QLabel("Stage (e.g. Open Qualifiers):"), 0, 2)
        self.stage_edit = QLineEdit()
        ig.addWidget(self.stage_edit, 0, 3)
        ig.addWidget(QLabel("Placement points (1st,2nd,...):"), 1, 0)
        self.placement_edit = QLineEdit()
        ig.addWidget(self.placement_edit, 1, 1)
        ig.addWidget(QLabel("Points per elimination:"), 1, 2)
        self.killpoint_spin = QSpinBox()
        self.killpoint_spin.setRange(0, 10)
        ig.addWidget(self.killpoint_spin, 1, 3)
        ig.addWidget(QLabel("Total matches in event:"), 2, 0)
        self.total_matches_spin = QSpinBox()
        self.total_matches_spin.setRange(1, 99)
        self.total_matches_spin.setValue(6)
        ig.addWidget(self.total_matches_spin, 2, 1)
        ig.addWidget(QLabel("(long tournaments supported — e.g. 30 matches)"), 2, 2, 1, 2)

        # Result-graphic template. The full picker with previews and custom
        # artwork lives in the web app; here it is a plain dropdown so a
        # desktop-only operator is not stuck on the default look.
        from core.graphic_themes import catalogue as graphic_catalogue
        ig.addWidget(QLabel("Result graphic template:"), 3, 0)
        self.template_combo = QComboBox()
        for entry in graphic_catalogue():
            self.template_combo.addItem(entry["name"], entry["key"])
        ig.addWidget(self.template_combo, 3, 1)
        ig.addWidget(QLabel("(upload your own background in the web app)"), 3, 2, 1, 2)
        layout.addWidget(info)

        teams_box = QGroupBox(
            f"Teams — Slot 1 to {self.MAX_SLOTS} (slot number = API team ID; "
            "leave unused slots empty)")
        tg = QVBoxLayout(teams_box)
        self.teams_table = QTableWidget(self.MAX_SLOTS, 3)
        self.teams_table.setHorizontalHeaderLabels(["Slot No", "Team Name", "Team Tag"])
        self.teams_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.teams_table.verticalHeader().setVisible(False)
        tg.addWidget(self.teams_table)

        btns = QHBoxLayout()
        import_btn = QPushButton("⇩ Fill Slots From Live Data")
        import_btn.clicked.connect(self._import_teams_from_live)
        btns.addWidget(import_btn)
        clear_btn = QPushButton("✕ Clear All Slots")
        clear_btn.clicked.connect(self._clear_team_slots)
        btns.addWidget(clear_btn)
        btns.addStretch()
        save_btn = QPushButton("💾  Save Event")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_event)
        btns.addWidget(save_btn)
        tg.addLayout(btns)
        layout.addWidget(teams_box, stretch=1)
        return w

    def _reload_event_tab(self):
        ev = self.events.event
        self.event_name_edit.setText(ev.get("eventName", ""))
        self.stage_edit.setText(ev.get("stage", ""))
        self.total_matches_spin.setValue(int(ev.get("totalMatches", 6) or 6))
        ps = ev.get("pointSystem", DEFAULT_POINT_SYSTEM)
        self.placement_edit.setText(",".join(str(p) for p in ps.get("placementPoints", [])))
        self.killpoint_spin.setValue(int(ps.get("killPoint", 1)))
        current_template = (self.events.event.get("graphics") or {}).get("template", "")
        index = self.template_combo.findData(current_template)
        self.template_combo.setCurrentIndex(index if index >= 0 else 0)
        by_slot = {int(t.get("teamId", 0)): t for t in ev.get("teams", [])}
        self.teams_table.setRowCount(self.MAX_SLOTS)
        for row in range(self.MAX_SLOTS):
            slot = row + 1
            slot_item = QTableWidgetItem(str(slot))
            slot_item.setFlags(slot_item.flags() & ~Qt.ItemIsEditable)  # read-only
            slot_item.setTextAlignment(Qt.AlignCenter)
            slot_item.setForeground(QColor("#e8be52"))
            self.teams_table.setItem(row, 0, slot_item)
            t = by_slot.get(slot, {})
            self.teams_table.setItem(row, 1, QTableWidgetItem(t.get("teamName", "")))
            self.teams_table.setItem(row, 2, QTableWidgetItem(t.get("shortName", "")))

    def _clear_team_slots(self):
        reply = QMessageBox.question(
            self, "Clear Slots", "Clear all team names and tags from every slot?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for row in range(self.teams_table.rowCount()):
            self.teams_table.setItem(row, 1, QTableWidgetItem(""))
            self.teams_table.setItem(row, 2, QTableWidgetItem(""))

    def _import_teams_from_live(self):
        snap, _, _, _ = self.poller.latest()
        if snap is None:
            QMessageBox.warning(self, "No Data",
                                "Start polling on the Live Match tab first, then import.")
            return
        states = snap.team_states()
        filled = 0
        for tid, st in sorted(states.items()):
            if not 1 <= tid <= self.MAX_SLOTS:
                continue
            row = tid - 1
            name_item = self.teams_table.item(row, 1)
            if name_item and name_item.text().strip():
                continue  # do not overwrite names the user already typed
            self.teams_table.setItem(row, 1, QTableWidgetItem(st.teamName))
            filled += 1
        QMessageBox.information(
            self, "Slots Filled",
            f"Filled {filled} empty slot(s) with team names from live data.\n"
            "Slots that already had a name were left unchanged.")

    def _save_event(self):
        try:
            placements = [int(x) for x in self.placement_edit.text().replace(" ", "").split(",") if x]
        except ValueError:
            QMessageBox.warning(self, "Invalid Points",
                                "Placement points must be numbers separated by commas, e.g. 10,6,5,4,3,2,1,1")
            return
        old_by_slot = {int(t.get("teamId", 0)): t
                       for t in self.events.event.get("teams", [])}
        teams = []
        for row in range(self.teams_table.rowCount()):
            slot = row + 1
            name_item = self.teams_table.item(row, 1)
            tag_item = self.teams_table.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            tag = tag_item.text().strip() if tag_item else ""
            if not name and not tag and not old_by_slot.get(slot, {}).get("players"):
                continue  # unused slot
            entry = dict(old_by_slot.get(slot, {}))  # keep OCR'd players etc.
            entry.update({"teamId": slot, "teamName": name, "shortName": tag})
            teams.append(entry)
        self.events.event.update({
            "eventName": self.event_name_edit.text().strip() or "My PUBGM Event",
            "stage": self.stage_edit.text().strip(),
            "totalMatches": self.total_matches_spin.value(),
            "pointSystem": {"placementPoints": placements or DEFAULT_POINT_SYSTEM["placementPoints"],
                            "killPoint": self.killpoint_spin.value()},
            "teams": teams,
        })
        graphics = dict(self.events.event.get("graphics") or {})
        graphics["template"] = self.template_combo.currentData()
        self.events.event["graphics"] = graphics
        self.events.save_event()
        self._update_match_progress()
        QMessageBox.information(self, "Saved", "Event settings saved.")

    # --------------------------------------------------------------- RESULTS
    def _build_results_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)

        left = QVBoxLayout()
        left.addWidget(QLabel("Saved matches:"))
        self.match_list = QListWidget()
        self.match_list.currentRowChanged.connect(self._show_selected_match)
        left.addWidget(self.match_list, stretch=1)
        self.del_match_btn = QPushButton("🗑  Delete Selected Match")
        self.del_match_btn.setObjectName("danger")
        self.del_match_btn.clicked.connect(self._delete_selected_match)
        left.addWidget(self.del_match_btn)
        layout.addLayout(left, stretch=1)

        right = QVBoxLayout()
        self.result_title = QLabel("Select a match on the left, or see overall standings below.")
        right.addWidget(self.result_title)
        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(
            ["Rank", "Team", "Elims", "Place Pts", "Elim Pts", "Total"])
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right.addWidget(self.result_table, stretch=1)

        self.standings_header = QLabel("Overall standings (all saved matches):")
        right.addWidget(self.standings_header)
        self.standings_table = QTableWidget(0, 7)
        self.standings_table.setHorizontalHeaderLabels(
            ["Rank", "Team", "Matches", "WWCD", "Elims", "Place Pts", "Total"])
        self.standings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.standings_table.verticalHeader().setVisible(False)
        self.standings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right.addWidget(self.standings_table, stretch=1)

        btns = QHBoxLayout()
        self.export_match_btn = QPushButton("🖼  Export Selected Match PNG")
        self.export_match_btn.setObjectName("primary")
        self.export_match_btn.clicked.connect(self._export_match_png)
        btns.addWidget(self.export_match_btn)
        self.export_overall_btn = QPushButton("🖼  Export Overall Standings PNG")
        self.export_overall_btn.setObjectName("primary")
        self.export_overall_btn.clicked.connect(self._export_overall_png)
        btns.addWidget(self.export_overall_btn)
        self.sheet_btn = QPushButton("📊  Open Tournament Sheet (xlsx)")
        self.sheet_btn.clicked.connect(self._open_tournament_sheet)
        btns.addWidget(self.sheet_btn)
        self.open_exports_btn = QPushButton("📂  Open Exports Folder")
        self.open_exports_btn.clicked.connect(lambda: os.startfile(self.events.exports_dir))
        btns.addWidget(self.open_exports_btn)
        btns.addStretch()
        right.addLayout(btns)
        layout.addLayout(right, stretch=3)
        return w

    def _reload_results_tab(self):
        self.match_list.clear()
        for num in self.events.list_match_numbers():
            match = self.events.load_match(num)
            map_name = match.get("map", "") if match else ""
            self.match_list.addItem(f"Match {num}  —  {map_name}")
        self._refresh_standings()
        self._refresh_player_stats()
        self._update_match_progress()

    def _update_match_progress(self):
        total = int(self.events.event.get("totalMatches", 0) or 0)
        played = len(self.events.list_match_numbers())
        self.match_progress_label.setText(f"of {total}  •  {played} played")
        self.standings_header.setText(
            f"Overall standings — after {played} of {total} matches:")

    def _selected_match_number(self) -> int | None:
        row = self.match_list.currentRow()
        nums = self.events.list_match_numbers()
        if row < 0 or row >= len(nums):
            return None
        return nums[row]

    def _show_selected_match(self):
        num = self._selected_match_number()
        if num is None:
            return
        match = self.events.load_match(num)
        if not match:
            return
        self.result_title.setText(
            f"Match {num} — {match.get('map', '')} — finalized {match.get('finalizedAt', '')}")
        results = match.get("results", [])
        self.result_table.setRowCount(len(results))
        for row, r in enumerate(results):
            name = r["teamName"] + ("   👑 WWCD" if r.get("wwcd") else "")
            values = [f"#{r['placement']}", name, str(r["kills"]),
                      str(r["placementPoints"]), str(r["killPoints"]), str(r["totalPoints"])]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col != 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if r["placement"] == 1:
                    item.setForeground(QColor("#e8be52"))
                self.result_table.setItem(row, col, item)

    def _refresh_standings(self):
        standings = self.events.overall_standings()
        self.standings_table.setRowCount(len(standings))
        for row, a in enumerate(standings):
            values = [f"#{a['rank']}", a["teamName"], str(a["matches"]), str(a["wwcd"]),
                      str(a["kills"]), str(a["placementPoints"]), str(a["totalPoints"])]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col != 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if a["rank"] <= 3:
                    item.setForeground(QColor("#e8be52"))
                self.standings_table.setItem(row, col, item)

    def _delete_selected_match(self):
        num = self._selected_match_number()
        if num is None:
            return
        reply = QMessageBox.question(self, "Delete Match",
                                     f"Delete the saved result for Match {num}?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.events.delete_match(num)
            try:
                export_tournament_sheet(self.events)
            except Exception:  # noqa: BLE001
                pass
            self._reload_results_tab()

    def _open_tournament_sheet(self):
        path = self.events.exports_dir / "Tournament Sheet.xlsx"
        if not path.exists():
            try:
                export_tournament_sheet(self.events)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Export Failed", str(e))
                return
        os.startfile(path)

    def _export_match_png(self):
        num = self._selected_match_number()
        if num is None:
            QMessageBox.warning(self, "No Match Selected",
                                "Select a saved match in the list first.")
            return
        match = self.events.load_match(num)
        out = self.events.exports_dir / f"match_{num:02d}_results.png"
        path = result_graphic.render_match_results(match, out, self.events.branding())
        QMessageBox.information(self, "Exported", f"Saved:\n{path}")
        os.startfile(path)

    def _export_overall_png(self):
        standings = self.events.overall_standings()
        if not standings:
            QMessageBox.warning(self, "No Results",
                                "No saved matches yet — finalize a match first.")
            return
        matches = len(self.events.list_match_numbers())
        out = self.events.exports_dir / "overall_standings.png"
        path = result_graphic.render_overall_standings(
            standings, self.events.event.get("eventName", ""), matches, out,
            self.events.branding())
        QMessageBox.information(self, "Exported", f"Saved:\n{path}")
        os.startfile(path)

    # ---------------------------------------------------------- PLAYER STATS
    def _build_player_stats_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        top = QHBoxLayout()
        self.player_stats_header = QLabel("Player leaderboard across all saved matches:")
        top.addWidget(self.player_stats_header)
        top.addStretch()
        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.clicked.connect(self._refresh_player_stats)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        cols = ["Rank", "Player IGN", "Team", "Matches", "Elims", "Damage",
                "Headshots", "Assists", "Knockouts", "Dmg Recv", "Survival",
                "Heal", "Rescues", "Longest Elim", "MVP Rating"]
        self.player_table = QTableWidget(0, len(cols))
        self.player_table.setHorizontalHeaderLabels(cols)
        self.player_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.player_table.verticalHeader().setVisible(False)
        self.player_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.player_table.setAlternatingRowColors(True)
        self.player_table.setSortingEnabled(True)
        layout.addWidget(self.player_table, stretch=1)
        return w

    def _refresh_player_stats(self):
        stats = self.events.player_stats()
        played = len(self.events.list_match_numbers())
        self.player_stats_header.setText(
            f"Player leaderboard — after {played} match{'es' if played != 1 else ''} "
            "(sorted by elims, click any column header to re-sort):")
        self.player_table.setSortingEnabled(False)
        self.player_table.setRowCount(len(stats))
        for row, a in enumerate(stats):
            mins = int(a["survivalTime"]) // 60
            secs = int(a["survivalTime"]) % 60
            values = [a["rank"], a["playerName"], a["teamName"], a["matches"],
                      a["kills"], a["damage"], a["headshots"], a["assists"],
                      a["knockouts"], a["damageReceived"], f"{mins}:{secs:02d}",
                      a["heal"], a["rescues"], a["longestKill"],
                      f"{a['mvpRating']:.4f}"]
            for col, val in enumerate(values):
                item = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    item.setData(Qt.DisplayRole, val)  # numeric sort
                else:
                    item.setText(str(val))
                if col != 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if a["rank"] <= 3:
                    item.setForeground(QColor("#e8be52"))
                self.player_table.setItem(row, col, item)
        self.player_table.setSortingEnabled(True)

    # ----------------------------------------------------------------- ADMIN
    def _build_admin_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        users_box = QGroupBox("User Accounts")
        ug = QVBoxLayout(users_box)
        self.users_table = QTableWidget(0, 3)
        self.users_table.setHorizontalHeaderLabels(["Username", "Role", "Created"])
        self.users_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        ug.addWidget(self.users_table)

        ubtns = QHBoxLayout()
        reset_btn = QPushButton("🔁 Reset Password of Selected")
        reset_btn.clicked.connect(self._reset_user_password)
        ubtns.addWidget(reset_btn)
        del_user_btn = QPushButton("🗑 Delete Selected User")
        del_user_btn.setObjectName("danger")
        del_user_btn.clicked.connect(self._delete_user)
        ubtns.addWidget(del_user_btn)
        ubtns.addStretch()
        ug.addLayout(ubtns)
        layout.addWidget(users_box, stretch=1)

        add_box = QGroupBox("Add New User")
        ag = QGridLayout(add_box)
        ag.addWidget(QLabel("Username:"), 0, 0)
        self.new_user_edit = QLineEdit()
        ag.addWidget(self.new_user_edit, 0, 1)
        ag.addWidget(QLabel("Password:"), 0, 2)
        self.new_pass_edit = QLineEdit()
        self.new_pass_edit.setEchoMode(QLineEdit.Password)
        ag.addWidget(self.new_pass_edit, 0, 3)
        ag.addWidget(QLabel("Role:"), 0, 4)
        self.new_role_combo = QComboBox()
        self.new_role_combo.addItems([ROLE_OPERATOR, ROLE_ADMIN])
        ag.addWidget(self.new_role_combo, 0, 5)
        add_user_btn = QPushButton("＋ Add User")
        add_user_btn.setObjectName("primary")
        add_user_btn.clicked.connect(self._add_user)
        ag.addWidget(add_user_btn, 0, 6)
        ag.addWidget(QLabel(
            "operator = run matches && save results only  •  "
            "admin = full access including this panel"), 1, 0, 1, 7)
        layout.addWidget(add_box)

        me_box = QGroupBox("My Account")
        mg = QHBoxLayout(me_box)
        change_btn = QPushButton("🔑 Change My Password")
        change_btn.clicked.connect(self._change_own_password)
        mg.addWidget(change_btn)
        mg.addStretch()
        layout.addWidget(me_box)

        self._reload_users_table()
        return w

    def _reload_users_table(self):
        users = self.auth.list_users()
        self.users_table.setRowCount(len(users))
        for row, u in enumerate(users):
            for col, val in enumerate([u["username"], u["role"], u["createdAt"]]):
                item = QTableWidgetItem(val)
                if u["role"] == ROLE_ADMIN and col == 1:
                    item.setForeground(QColor("#e8be52"))
                self.users_table.setItem(row, col, item)

    def _selected_username(self) -> str | None:
        row = self.users_table.currentRow()
        if row < 0:
            return None
        return self.users_table.item(row, 0).text()

    def _add_user(self):
        try:
            self.auth.add_user(self.new_user_edit.text(),
                               self.new_pass_edit.text(),
                               self.new_role_combo.currentText())
        except AuthError as e:
            QMessageBox.warning(self, "Cannot Add User", str(e))
            return
        self.new_user_edit.clear()
        self.new_pass_edit.clear()
        self._reload_users_table()
        QMessageBox.information(self, "User Added",
                                "Account created. Share the username and "
                                "password with your operator.")

    def _reset_user_password(self):
        username = self._selected_username()
        if not username:
            QMessageBox.warning(self, "No Selection", "Select a user in the table first.")
            return
        new_pass, ok = QInputDialog.getText(
            self, "Reset Password", f"New password for '{username}':",
            QLineEdit.Password)
        if not ok or not new_pass:
            return
        try:
            self.auth.set_password(username, new_pass)
        except AuthError as e:
            QMessageBox.warning(self, "Cannot Reset", str(e))
            return
        QMessageBox.information(self, "Done", f"Password for '{username}' changed.")

    def _delete_user(self):
        username = self._selected_username()
        if not username:
            QMessageBox.warning(self, "No Selection", "Select a user in the table first.")
            return
        reply = QMessageBox.question(self, "Delete User",
                                     f"Delete the account '{username}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self.auth.remove_user(username, self.user["username"])
        except AuthError as e:
            QMessageBox.warning(self, "Cannot Delete", str(e))
            return
        self._reload_users_table()

    def _change_own_password(self):
        new_pass, ok = QInputDialog.getText(
            self, "Change My Password",
            f"New password for '{self.user['username']}':", QLineEdit.Password)
        if not ok or not new_pass:
            return
        try:
            self.auth.set_password(self.user["username"], new_pass)
        except AuthError as e:
            QMessageBox.warning(self, "Cannot Change", str(e))
            return
        QMessageBox.information(self, "Done", "Your password has been changed.")

    # ------------------------------------------------------------------- OCR
    def _build_ocr_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        intro = QLabel(
            "<b>Step 1 — Team Roster from lobby screenshots.</b> "
            "Load the in-game team list screenshots (big colored slot number + "
            "4 players per card). The app reads every card; fix any mistakes "
            "directly in the table, then apply to the event slots. "
            "This roster is what the post-match rankings screenshots will be "
            "matched against.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        btns = QHBoxLayout()
        load_btn = QPushButton("📷  Load Slot Screenshot(s)…")
        load_btn.setObjectName("primary")
        load_btn.clicked.connect(self._load_roster_screenshots)
        btns.addWidget(load_btn)
        clear_btn = QPushButton("✕ Clear Table")
        clear_btn.clicked.connect(lambda: self.roster_table.setRowCount(0))
        btns.addWidget(clear_btn)
        btns.addStretch()
        self.roster_apply_btn = QPushButton("💾  Apply Roster To Event Slots")
        self.roster_apply_btn.setObjectName("primary")
        self.roster_apply_btn.clicked.connect(self._apply_roster_to_event)
        btns.addWidget(self.roster_apply_btn)
        layout.addLayout(btns)

        self.ocr_status = QLabel("No screenshots loaded yet.")
        layout.addWidget(self.ocr_status)

        cols = ["Slot", "Player 1", "Player 2", "Player 3", "Player 4", "Team Tag"]
        self.roster_table = QTableWidget(0, len(cols))
        self.roster_table.setHorizontalHeaderLabels(cols)
        for c in range(1, 5):
            self.roster_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        self.roster_table.verticalHeader().setVisible(False)
        self.roster_table.setAlternatingRowColors(True)
        layout.addWidget(self.roster_table, stretch=1)

        self._ocr_result = None
        self._ocr_poll = QTimer(self)
        self._ocr_poll.setInterval(200)
        self._ocr_poll.timeout.connect(self._check_ocr_done)

        # ---- Step 2: match results from rankings screenshots ----
        step2 = QGroupBox("Step 2 — Match Results from post-match rankings screenshots")
        s2 = QVBoxLayout(step2)
        intro2 = QLabel(
            "Load ALL pages of the end-of-match rankings screen (the gold "
            "cards). The app reads rank + player eliminations, merges "
            "overlapping pages, and matches every card to a team slot using "
            "the roster above. Check/fix the table, then save the match.")
        intro2.setWordWrap(True)
        s2.addWidget(intro2)

        rbtns = QHBoxLayout()
        rload_btn = QPushButton("🏆  Load Result Screenshot(s)…")
        rload_btn.setObjectName("primary")
        rload_btn.clicked.connect(self._load_result_screenshots)
        rbtns.addWidget(rload_btn)
        rclear_btn = QPushButton("✕ Clear")
        rclear_btn.clicked.connect(self._clear_result_table)
        rbtns.addWidget(rclear_btn)
        rbtns.addStretch()
        rbtns.addWidget(QLabel("Match #:"))
        self.ocr_match_spin = QSpinBox()
        self.ocr_match_spin.setRange(1, 99)
        self.ocr_match_spin.setValue(self.events.next_match_number())
        rbtns.addWidget(self.ocr_match_spin)
        rbtns.addWidget(QLabel("Map:"))
        self.ocr_map_combo = QComboBox()
        self.ocr_map_combo.addItems(MAPS)
        rbtns.addWidget(self.ocr_map_combo)
        rsave_btn = QPushButton("✔  Save As Match Result")
        rsave_btn.setObjectName("primary")
        rsave_btn.clicked.connect(self._save_ocr_match)
        rbtns.addWidget(rsave_btn)
        s2.addLayout(rbtns)

        self.results_ocr_status = QLabel("No result screenshots loaded yet.")
        s2.addWidget(self.results_ocr_status)

        rcols = ["Rank", "Slot", "Team Name", "Team Elims", "Players (elims)", "Confidence"]
        self.result_ocr_table = QTableWidget(0, len(rcols))
        self.result_ocr_table.setHorizontalHeaderLabels(rcols)
        self.result_ocr_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.result_ocr_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.result_ocr_table.verticalHeader().setVisible(False)
        self.result_ocr_table.setAlternatingRowColors(True)
        s2.addWidget(self.result_ocr_table, stretch=1)
        layout.addWidget(step2, stretch=1)

        self._results_ocr_output = None
        self._result_cards = []
        self._results_ocr_poll = QTimer(self)
        self._results_ocr_poll.setInterval(200)
        self._results_ocr_poll.timeout.connect(self._check_results_ocr_done)
        return w

    def _clear_result_table(self):
        self.result_ocr_table.setRowCount(0)
        self._result_cards = []

    def _load_result_screenshots(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select ALL rankings screenshot pages", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not files:
            return
        self.results_ocr_status.setText(
            f"Reading {len(files)} screenshot(s) and matching against the roster…")
        self._results_ocr_output = None
        teams = self.events.event.get("teams", [])

        def work():
            from core.ocr_pipeline import run_results_ocr
            self._results_ocr_output = run_results_ocr(files, teams)

        threading.Thread(target=work, daemon=True).start()
        self._results_ocr_poll.start()

    def _check_results_ocr_done(self):
        if self._results_ocr_output is None:
            return
        self._results_ocr_poll.stop()
        parsed = self._results_ocr_output
        self._results_ocr_output = None
        cards = parsed["cards"]
        self._fill_result_table(cards)

        msg = f"Read {len(cards)} team(s) with the {parsed['engineUsed']} engine."
        if parsed["problems"]:
            msg += "  ⚠ " + "  •  ".join(parsed["problems"])
        else:
            msg += "  Everything matched — check the numbers, then click " \
                   "'Save As Match Result'."
        self.results_ocr_status.setText(msg)

    def _fill_result_table(self, cards: list):
        from core.ocr_pipeline import score_cards

        cards = sorted(cards, key=lambda c: (c["rank"] is None, c["rank"] or 99))
        self._result_cards = cards
        verdicts = score_cards(cards)
        self.result_ocr_table.setRowCount(len(cards))
        for row, (c, verdict) in enumerate(zip(cards, verdicts)):
            team_kills = sum(p["kills"] for p in c["players"])
            players_txt = ",  ".join(f"{p['name']} ({p['kills']})" for p in c["players"])
            values = ["" if c["rank"] is None else str(c["rank"]),
                      "" if c.get("slot") is None else str(c["slot"]),
                      c.get("teamName", ""), str(team_kills), players_txt,
                      f"{int(verdict['score'] * 100)}%"]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in (4, 5):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col != 4:
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 5:
                    # the confidence column explains itself on hover rather than
                    # just glowing red, so the operator knows what to look at
                    item.setToolTip("\n".join(verdict["reasons"]) or "No problems found.")
                    if verdict["needsReview"]:
                        item.setForeground(QColor("#e06c6c"))
                self.result_ocr_table.setItem(row, col, item)

    def _save_ocr_match(self):
        from core.scoring import placement_points
        if not self._result_cards:
            QMessageBox.warning(self, "No Data", "Load result screenshots first.")
            return
        entries = []
        problems = []
        for row in range(self.result_ocr_table.rowCount()):
            def cell(col):
                item = self.result_ocr_table.item(row, col)
                return item.text().strip() if item else ""
            rank_t, slot_t, name, kills_t = cell(0), cell(1), cell(2), cell(3)
            if not rank_t.isdigit():
                problems.append(f"row {row + 1}: missing rank")
                continue
            if not slot_t.isdigit():
                problems.append(f"row {row + 1}: missing slot")
                continue
            entries.append({
                "rank": int(rank_t), "slot": int(slot_t),
                "teamName": name or f"Team {slot_t}",
                "kills": int(kills_t) if kills_t.isdigit() else 0,
                "players": self._result_cards[row]["players"]
                if row < len(self._result_cards) else [],
            })
        if problems:
            QMessageBox.warning(self, "Fix These First", "\n".join(problems))
            return
        ranks = [e["rank"] for e in entries]
        slots = [e["slot"] for e in entries]
        if len(set(ranks)) != len(ranks) or len(set(slots)) != len(slots):
            QMessageBox.warning(self, "Duplicates",
                                "Two rows share the same rank or slot — fix them first.")
            return

        ps = self.events.event.get("pointSystem", DEFAULT_POINT_SYSTEM)
        kill_point = int(ps.get("killPoint", 1))
        results = []
        for e in sorted(entries, key=lambda e: e["rank"]):
            pp = placement_points(e["rank"], ps)
            kp = e["kills"] * kill_point
            results.append({
                "teamId": e["slot"], "teamName": e["teamName"],
                "placement": e["rank"], "kills": e["kills"],
                "placementPoints": pp, "killPoints": kp,
                "totalPoints": pp + kp, "wwcd": e["rank"] == 1,
                "players": [{
                    "playerName": p["name"], "uId": "", "kills": p["kills"],
                    "damage": 0, "knockouts": 0, "headshots": 0, "assists": 0,
                    "damageReceived": 0, "survivalTime": 0, "heal": 0,
                    "rescues": 0, "longestKill": 0, "grenadeKills": 0, "raw": {},
                } for p in e["players"]],
            })

        num = self.ocr_match_spin.value()
        if self.events.load_match(num):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Match {num} already has a saved result. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self._persist_match(num, self.ocr_map_combo.currentText(), results)
        self.ocr_match_spin.setValue(self.events.next_match_number())

    def _load_roster_screenshots(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select slot list screenshot(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not files:
            return
        self.ocr_status.setText(
            f"Reading {len(files)} screenshot(s)… first run loads the OCR "
            "engine, this can take ~10-20 seconds.")
        self._ocr_result = None

        def work():
            from core.ocr_pipeline import run_roster_ocr
            parsed = run_roster_ocr(files)
            self._ocr_result = (parsed["cards"], parsed["errors"])

        threading.Thread(target=work, daemon=True).start()
        self._ocr_poll.start()

    def _check_ocr_done(self):
        if self._ocr_result is None:
            return
        self._ocr_poll.stop()
        cards, errors = self._ocr_result
        self._ocr_result = None
        self._add_roster_cards(cards)
        missing = sum(1 for c in cards if c["slot"] is None)
        msg = f"Read {len(cards)} team card(s)."
        if missing:
            msg += f"  ⚠ {missing} card(s) have no slot number — type it in the Slot column."
        if errors:
            msg += "  Errors: " + "; ".join(errors)
        msg += "  Check the names, then click 'Apply Roster To Event Slots'."
        self.ocr_status.setText(msg)

    def _add_roster_cards(self, cards: list):
        from core.ocr_roster import suggest_tag
        # replace existing rows that have the same slot number
        existing = {}
        for row in range(self.roster_table.rowCount()):
            item = self.roster_table.item(row, 0)
            if item and item.text().strip().isdigit():
                existing[int(item.text().strip())] = row
        for c in cards:
            slot = c["slot"]
            row = existing.get(slot, -1) if slot is not None else -1
            if row < 0:
                row = self.roster_table.rowCount()
                self.roster_table.insertRow(row)
            values = [str(slot) if slot is not None else ""]
            players = (c["players"] + ["", "", "", ""])[:4]
            values += players
            values.append(suggest_tag(c["players"]))
            for col, val in enumerate(values):
                self.roster_table.setItem(row, col, QTableWidgetItem(val))
        self.roster_table.sortItems(0)

    def _apply_roster_to_event(self):
        by_slot = {int(t.get("teamId", 0)): t
                   for t in self.events.event.get("teams", [])}
        applied, skipped = 0, 0
        for row in range(self.roster_table.rowCount()):
            def cell(col):
                item = self.roster_table.item(row, col)
                return item.text().strip() if item else ""
            slot_text = cell(0)
            if not slot_text.isdigit() or not 1 <= int(slot_text) <= self.MAX_SLOTS:
                skipped += 1
                continue
            slot = int(slot_text)
            players = [cell(c) for c in range(1, 5) if cell(c)]
            tag = cell(5)
            entry = by_slot.setdefault(slot, {"teamId": slot, "teamName": "", "shortName": ""})
            entry["players"] = players
            if tag and not entry.get("shortName"):
                entry["shortName"] = tag
            if not entry.get("teamName"):
                entry["teamName"] = tag  # placeholder until real name is typed
            applied += 1
        self.events.event["teams"] = [by_slot[k] for k in sorted(by_slot)]
        self.events.save_event()
        self._reload_event_tab()
        msg = (f"Roster applied to {applied} slot(s) and saved to the event.\n"
               "Team names/tags can be edited on the Event Setup tab.")
        if skipped:
            msg += f"\n⚠ {skipped} row(s) skipped — missing or invalid slot number."
        QMessageBox.information(self, "Roster Saved", msg)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    settings = load_settings()
    license_server_url = configured_license_server_url(settings)
    remote_auth = (RemoteAuthManager(DATA_DIR, license_server_url)
                   if license_server_url else None)
    auth = None if remote_auth else AuthManager(DATA_DIR)

    while True:
        if remote_auth:
            dlg = LoginDialog(remote_auth)
            window_auth = None
        elif not auth.has_users():
            dlg = FirstRunDialog(auth)
            window_auth = auth
        else:
            dlg = LoginDialog(auth)
            window_auth = auth
        if dlg.exec() != QDialog.Accepted or dlg.user is None:
            return  # closed the login window
        win = MainWindow(dlg.user, window_auth)
        win.show()
        app.exec()
        if not win.wants_logout:
            return


if __name__ == "__main__":
    main()
