"""FastAPI app for MiMo web chat."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

MIMO_API_KEY = os.environ.get("MIMO_API_KEY")
if not MIMO_API_KEY:
    raise RuntimeError(
        "MIMO_API_KEY is required. Put it in .env or export it before launching."
    )

app = FastAPI(title="AIIC MiMo Chat", version="1.0.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
