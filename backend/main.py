"""
IgniteAds backend — FastAPI app shell.

Phase A is CLI-driven (scripts/ads/); this service exists so the Cloud Run
target, deploy scripts, and health checks are in place from day one.
Phase B registers routers here: accounts (OAuth), campaigns (launch/manage),
metrics (Cloud Scheduler sync).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="IgniteAds", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:4200,https://ads.igniteai.in,https://igniteai-ads.web.app",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers import campaigns  # noqa: E402

app.include_router(campaigns.router, prefix="/api/ads", tags=["campaigns"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "ignite-ads"}
