"""NetSentinel — API de supervision et de prédiction de coupures réseau H+1.

Ministère du Budget — réseau des 6 départements.

Lancement :
    uvicorn api.main:app --reload --port 8000

Documentation interactive : http://localhost:8000/docs
Tableau de bord de démonstration : http://localhost:8000/dashboard
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.config import get_settings
from api.deps import require_api_key
from api.routers import (
    alerts,
    anomalies,
    departments,
    forecast,
    predictions,
    reports,
    simulation,
    telemetry,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=settings.description,
        version=settings.version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # prototype — restreindre aux domaines DSI en production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        departments.router,
        telemetry.router,
        predictions.router,
        anomalies.router,
        forecast.router,
        alerts.router,
        reports.router,
        simulation.router,
    ):
        app.include_router(router, prefix="/api/v1", dependencies=[Depends(require_api_key)])

    @app.get("/", tags=["Système"])
    def root():
        return {
            "service": settings.app_name,
            "version": settings.version,
            "status": "operational",
            "ministere": "Budget",
            "departments_monitored": 6,
            "docs": "/docs",
            "dashboard": "/dashboard",
        }

    @app.get("/health", tags=["Système"])
    def health():
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/dashboard", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_DIR / "dashboard.html")

    return app


app = create_app()
