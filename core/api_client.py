"""Background poller for the PUBG Mobile observer API.

Runs in its own thread so the GUI never freezes. The GUI reads the latest
snapshot/status through thread-safe accessors. Falls back to mock data when
mock mode is enabled or the API is unreachable (if fallback is allowed).
"""

import json
import threading
import time

import requests

from .models import Snapshot, parse_snapshot
from .mock_data import MockDataGenerator

STATUS_STOPPED = "Stopped"
STATUS_LIVE = "Live (API)"
STATUS_MOCK = "Mock Data"
STATUS_ERROR = "API Error"


class ApiPoller:
    def __init__(self, api_url: str, interval: float = 2.0, mock_mode: bool = False):
        self.api_url = api_url
        self.interval = interval
        self.mock_mode = mock_mode
        self._mock = MockDataGenerator()
        self._lock = threading.Lock()
        self._snapshot = None
        self._status = STATUS_STOPPED
        self._last_error = ""
        self._last_update = 0.0
        self._thread = None
        self._stop = threading.Event()

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        if self.mock_mode:
            self._mock.reset()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            self._status = STATUS_STOPPED

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    # ---- thread-safe accessors ------------------------------------------
    def latest(self):
        with self._lock:
            return self._snapshot, self._status, self._last_update, self._last_error

    # ---- polling loop ----------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            snap = None
            status = STATUS_ERROR
            error = ""
            if self.mock_mode:
                snap = self._mock.fetch()
                status = STATUS_MOCK
            else:
                try:
                    resp = requests.get(self.api_url, timeout=3)
                    resp.raise_for_status()
                    snap = parse_snapshot(resp.json())
                    status = STATUS_LIVE
                except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                    error = str(e)

            with self._lock:
                if snap is not None:
                    self._snapshot = snap
                    self._last_update = time.time()
                self._status = status
                self._last_error = error

            self._stop.wait(self.interval)
