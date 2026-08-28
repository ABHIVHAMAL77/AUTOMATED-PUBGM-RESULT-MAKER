"""Run the website and Discord bot together for cloud hosting.

Cloud hosts usually run one start command. This runner starts the FastAPI website
and, when DISCORD_BOT_TOKEN is present, the Discord bot in the same container.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for env_name in (".env", ".env.discord", ".env.hostinger", ".env.cloud"):
    load_env_file(APP_DIR / env_name)


def start_process(name: str, args: list[str], env: dict[str, str]) -> subprocess.Popen:
    print(f"Starting {name}: {' '.join(args)}", flush=True)
    return subprocess.Popen(args, cwd=APP_DIR, env=env)


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return


def main() -> int:
    env = os.environ.copy()
    data_dir = Path(env.get("EC_DATA_DIR") or (APP_DIR / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    env["EC_DATA_DIR"] = str(data_dir)
    env.setdefault("PYTHONUNBUFFERED", "1")

    port = env.get("PORT", "8080")
    processes: list[tuple[str, subprocess.Popen]] = []
    stopping = False

    def shutdown(signum: int, _frame) -> None:
        nonlocal stopping
        stopping = True
        print(f"Received signal {signum}. Stopping services...", flush=True)
        for _, process in processes:
            stop_process(process)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown)
        except (AttributeError, ValueError):
            pass

    processes.append((
        "website",
        start_process(
            "website",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "web_app:app",
                "--host",
                "0.0.0.0",
                "--port",
                port,
            ],
            env,
        ),
    ))

    if env.get("DISCORD_BOT_TOKEN", "").strip():
        processes.append(("discord bot", start_process("discord bot", [sys.executable, "discord_bot.py"], env)))
    else:
        print("DISCORD_BOT_TOKEN is not set, so only the website is running.", flush=True)

    while processes:
        if stopping:
            break
        for name, process in list(processes):
            code = process.poll()
            if code is not None:
                print(f"{name} exited with code {code}. Stopping the app.", flush=True)
                for other_name, other in processes:
                    if other_name != name:
                        stop_process(other)
                for _, other in processes:
                    try:
                        other.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        other.kill()
                return int(code or 0)
        time.sleep(1)

    for _, process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

