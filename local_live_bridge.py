"""Local bridge for browser-based PUBG Mobile live feed reads.

The hosted result maker cannot make the VPS read http://127.0.0.1 on the
operator PC. This helper runs on the operator PC, reads the in-game observer
endpoint locally, and exposes a browser-readable local URL with the CORS headers
Chrome expects.
"""

from __future__ import annotations

import os

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

UPSTREAM_URL = os.environ.get(
    "EC_OBSERVER_URL",
    "http://127.0.0.1:10086/gettotalplayerlist",
)
BRIDGE_HOST = os.environ.get("EC_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("EC_BRIDGE_PORT", "8765"))
TIMEOUT_SECONDS = float(os.environ.get("EC_BRIDGE_TIMEOUT", "2.5"))

app = FastAPI(title="ESPORTS COUNTY Local Live Feed Bridge")


@app.middleware("http")
async def cors_for_local_browser(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = request.headers.get(
        "access-control-request-headers",
        "content-type",
    )
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict:
    return {"ok": True, "upstream": UPSTREAM_URL}


@app.get("/")
def home() -> dict:
    return {
        "ok": True,
        "useThisUrlInWebsite": f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/gettotalplayerlist",
        "upstream": UPSTREAM_URL,
    }


@app.get("/gettotalplayerlist")
def get_total_player_list() -> Response:
    try:
        upstream = requests.get(UPSTREAM_URL, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not read PUBG Mobile observer feed: {exc}",
        ) from exc

    media_type = upstream.headers.get("content-type") or "application/json"
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=media_type.split(";", 1)[0],
    )


if __name__ == "__main__":
    print("ESPORTS COUNTY local live feed bridge")
    print(f"Reading: {UPSTREAM_URL}")
    print(f"Website URL: http://{BRIDGE_HOST}:{BRIDGE_PORT}/gettotalplayerlist")
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT, log_level="info")
