from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="GameKnife Stable Audio SFX", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gameknife-stable-audio-sfx"}
