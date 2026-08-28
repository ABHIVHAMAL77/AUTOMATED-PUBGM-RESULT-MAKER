"""Auth manager unit test + offscreen role-restriction test."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from core.auth import AuthManager, AuthError, ROLE_ADMIN, ROLE_OPERATOR

tmp = Path(tempfile.mkdtemp(prefix="pubgm_auth_"))
auth = AuthManager(tmp)
assert not auth.has_users()

auth.add_user("worka", "secret123", ROLE_ADMIN)
auth.add_user("caster1", "pass1234", ROLE_OPERATOR)
assert auth.has_users() and auth.admin_count() == 1

assert auth.verify("worka", "secret123")["role"] == ROLE_ADMIN
assert auth.verify("WORKA", "secret123") is not None          # case-insensitive name
assert auth.verify("worka", "wrong") is None
assert auth.verify("nobody", "secret123") is None

# passwords are hashed, never stored in plain text
raw = (tmp / "users.json").read_text(encoding="utf-8")
assert "secret123" not in raw and "pass1234" not in raw

# persistence
auth2 = AuthManager(tmp)
assert auth2.verify("caster1", "pass1234")["role"] == ROLE_OPERATOR

# guards
try:
    auth2.remove_user("worka", acting_user="worka")
    raise SystemExit("should not delete own account")
except AuthError:
    pass
auth2.add_user("admin2", "abcd1234", ROLE_ADMIN)
auth2.remove_user("admin2", acting_user="worka")
try:
    auth2.add_user("worka", "x" * 8, ROLE_OPERATOR)
    raise SystemExit("duplicate username allowed")
except AuthError:
    pass

auth2.set_password("caster1", "newpass99")
assert auth2.verify("caster1", "pass1234") is None
assert auth2.verify("caster1", "newpass99") is not None
print("AUTH UNIT TEST PASSED")

# ---- role restrictions in the GUI -------------------------------------------
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

import app as m

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

qapp = QApplication.instance() or QApplication(sys.argv)

admin_win = m.MainWindow({"username": "worka", "role": ROLE_ADMIN}, auth2)
tab_names = [admin_win.tabs.tabText(i) for i in range(admin_win.tabs.count())]
assert any("Event Setup" in t for t in tab_names), tab_names
assert any("Admin Panel" in t for t in tab_names), tab_names
assert admin_win.export_match_btn.isEnabled()
assert admin_win.users_table.rowCount() == 2  # worka + caster1
admin_win.close()

op_win = m.MainWindow({"username": "caster1", "role": ROLE_OPERATOR}, auth2)
tab_names = [op_win.tabs.tabText(i) for i in range(op_win.tabs.count())]
assert not any("Event Setup" in t for t in tab_names), tab_names
assert not any("Admin Panel" in t for t in tab_names), tab_names
for btn in (op_win.export_match_btn, op_win.export_overall_btn,
            op_win.sheet_btn, op_win.open_exports_btn,
            op_win.del_match_btn, op_win.roster_apply_btn):
    assert not btn.isEnabled(), "operator button should be disabled"
# operators can still run matches: polling + finalize + OCR-save stay enabled
assert op_win.start_btn.isEnabled()
assert op_win.finalize_btn.isEnabled()
op_win.close()

QTimer.singleShot(200, qapp.quit)
qapp.exec()
print("ROLE RESTRICTION TEST PASSED")


def test_auth_smoke_script_completed():
    pass
