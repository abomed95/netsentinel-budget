"""
NetSentinel — API FastAPI de prédiction de coupures réseau H+1
Ministère du Budget
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import numpy as np
from datetime import datetime
import json

app = FastAPI(
    title="NetSentinel API",
    description="API de prédiction de coupures réseau H+1 — Ministère du Budget",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schémas ──────────────────────────────────────────────────────────────────
class NetworkMetrics(BaseModel):
    department_id: str
    latency_ms: float
    packet_loss_pct: float
    bandwidth_mbps: float
    cpu_pct: float
    temperature_celsius: float
    timestamp: Optional[str] = None

class PredictionResponse(BaseModel):
    department_id: str
    outage_probability: float
    risk_level: str
    recommendation: str
    shap_values: dict
    timestamp: str

# ── Logique de prédiction (remplacer par le vrai modèle LightGBM/LSTM) ───────
def compute_risk_score(metrics: NetworkMetrics) -> float:
    """
    Calcul du score de risque composite.
    En production : charger le modèle LightGBM entraîné depuis un fichier .pkl
    """
    latency_score   = min(1.0, metrics.latency_ms / 150)
    loss_score      = min(1.0, metrics.packet_loss_pct / 10)
    bandwidth_score = max(0.0, 1 - metrics.bandwidth_mbps / 250)
    cpu_score       = min(1.0, metrics.cpu_pct / 100)
    temp_score      = min(1.0, metrics.temperature_celsius / 85)

    # Pondération SHAP (à affiner avec les vraies données)
    score = (
        0.30 * latency_score +
        0.25 * loss_score +
        0.20 * bandwidth_score +
        0.15 * cpu_score +
        0.10 * temp_score
    )
    return round(min(0.99, max(0.01, score)), 4)

def get_risk_level(probability: float) -> tuple[str, str]:
    if probability > 0.70:
        return "CRITIQUE", "Intervention préventive immédiate recommandée"
    elif probability > 0.45:
        return "MODÉRÉ", "Surveillance renforcée conseillée"
    return "NORMAL", "Aucune action requise — réseau stable"

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "NetSentinel API",
        "version": "1.0.0",
        "status": "operational",
        "ministere": "Budget"
    }

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/predict", response_model=PredictionResponse)
def predict(metrics: NetworkMetrics):
    """
    Prédit la probabilité de coupure réseau dans les 60 prochaines minutes.
    """
    probability = compute_risk_score(metrics)
    risk_level, recommendation = get_risk_level(probability)

    shap_values = {
        "latence_reseau":      round(0.30 * min(1, metrics.latency_ms / 150), 4),
        "perte_paquets":       round(0.25 * min(1, metrics.packet_loss_pct / 10), 4),
        "bande_passante":      round(0.20 * max(0, 1 - metrics.bandwidth_mbps / 250), 4),
        "charge_cpu":          round(0.15 * min(1, metrics.cpu_pct / 100), 4),
        "temperature":         round(0.10 * min(1, metrics.temperature_celsius / 85), 4),
    }

    return PredictionResponse(
        department_id=metrics.department_id,
        outage_probability=probability,
        risk_level=risk_level,
        recommendation=recommendation,
        shap_values=shap_values,
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/predict/batch")
def predict_batch(metrics_list: list[NetworkMetrics]):
    """Prédiction pour plusieurs départements en une seule requête."""
    return [predict(m) for m in metrics_list]

@app.get("/departments")
def list_departments():
    """Liste des départements surveillés."""
    with open("data/arcep_sample.json") as f:
        data = json.load(f)
    return {"departments": [d["id"] for d in data["departments"]], "count": 5}

# ── Lancement ─────────────────────────────────────────────────────────────────
# uvicorn api.main:app --reload --port 8000
