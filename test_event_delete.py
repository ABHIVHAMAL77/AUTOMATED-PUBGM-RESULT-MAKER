import importlib
import sys

import pytest
from fastapi import HTTPException


def fresh_web_app(monkeypatch, tmp_path):
    monkeypatch.setenv("EC_DATA_DIR", str(tmp_path))
    sys.modules.pop("web_app", None)
    return importlib.import_module("web_app")


def test_delete_owned_event_removes_event_folder(monkeypatch, tmp_path):
    web_app = fresh_web_app(monkeypatch, tmp_path)
    owner = "owner@example.com"

    event_id, em = web_app.create_event_workspace(owner, "Delete Me", "Finals", 6)
    em.save_match_result(
        1,
        "Erangel",
        [{"teamId": 1, "teamName": "Alpha", "placement": 1, "kills": 3, "placementPoints": 10, "killPoints": 3, "totalPoints": 13, "wwcd": True}],
    )

    assert em.data_dir.exists()
    web_app.delete_event_workspace(owner, event_id)

    assert not em.data_dir.exists()
    assert web_app.events_payload(owner) == {"activeEventId": None, "events": []}


def test_shared_user_cannot_delete_owner_event(monkeypatch, tmp_path):
    web_app = fresh_web_app(monkeypatch, tmp_path)
    owner = "owner@example.com"
    worker = "worker@example.com"
    web_app.save_json(web_app.USERS_FILE, [{"email": owner}, {"email": worker}])

    event_id, em = web_app.create_event_workspace(owner, "Shared Event", "League", 6)
    web_app.save_event_access(em.data_dir, owner, {worker})
    shared_ref = web_app.event_ref_id(owner, event_id, worker)

    with pytest.raises(HTTPException) as caught:
        web_app.delete_event_workspace(worker, shared_ref)

    assert caught.value.status_code == 403
    assert em.data_dir.exists()
