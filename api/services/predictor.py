"""Service de prédiction de coupure H+1.

Charge le modèle entraîné (ml/models/outage_model.joblib) ; s'il est absent,
il est entraîné automatiquement au premier démarrage sur les données
synthétiques — le prototype fonctionne donc sans étape manuelle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

import joblib
import numpy as np

from api.config import get_settings
from api.schemas import NetworkMetrics, PredictionResponse
from api.store import DataStore
from ml.train import FEATURES, MODEL_VERSION, train

# Valeurs "réseau sain" utilisées comme référence pour l'attribution locale
HEALTHY_REFERENCE = {
    "latency_ms": 20.0,
    "packet_loss_pct": 0.2,
    "bandwidth_mbps": 200.0,
    "cpu_pct": 25.0,
    "temperature_celsius": 40.0,
}

FEATURE_LABELS = {
    "latency_ms": "latence_reseau",
    "packet_loss_pct": "perte_paquets",
    "bandwidth_mbps": "bande_passante",
    "cpu_pct": "charge_cpu",
    "temperature_celsius": "temperature",
}

_lock = Lock()
_model = None


def get_model():
    """Charge (ou entraîne puis charge) le classifieur de coupure."""
    global _model
    with _lock:
        if _model is None:
            path = get_settings().model_dir / "outage_model.joblib"
            if not path.exists():
                train(save=True)
            _model = joblib.load(path)
        return _model


def _to_features(metrics: NetworkMetrics) -> np.ndarray:
    ts = metrics.timestamp or datetime.now(timezone.utc)
    return np.array(
        [
            [
                metrics.latency_ms,
                metrics.packet_loss_pct,
                metrics.bandwidth_mbps,
                metrics.cpu_pct,
                metrics.temperature_celsius,
                float(ts.hour),
            ]
        ]
    )


def _risk_level(probability: float) -> tuple[str, str]:
    settings = get_settings()
    if probability > settings.critical_threshold:
        return "CRITIQUE", "Intervention préventive immédiate recommandée (basculement lien de secours, délestage)"
    if probability > settings.moderate_threshold:
        return "MODÉRÉ", "Surveillance renforcée conseillée — vérifier charge CPU et température des équipements"
    return "NORMAL", "Aucune action requise — réseau stable"


def _feature_contributions(model, x: np.ndarray, probability: float) -> dict[str, float]:
    """Attribution locale par occlusion : pour chaque métrique, on mesure la
    baisse de probabilité si elle était à sa valeur « réseau sain ».
    """
    contributions: dict[str, float] = {}
    for i, feature in enumerate(FEATURES[:5]):
        x_ref = x.copy()
        x_ref[0, i] = HEALTHY_REFERENCE[feature]
        p_ref = float(model.predict_proba(x_ref)[0, 1])
        contributions[FEATURE_LABELS[feature]] = round(probability - p_ref, 4)
    return contributions


def predict(metrics: NetworkMetrics, store: DataStore) -> PredictionResponse:
    model = get_model()
    x = _to_features(metrics)
    probability = round(float(model.predict_proba(x)[0, 1]), 4)
    level, recommendation = _risk_level(probability)

    return PredictionResponse(
        department_id=metrics.department_id,
        outage_probability=probability,
        risk_level=level,
        recommendation=recommendation,
        expected_loss_eur=round(probability * store.mean_incident_cost(metrics.department_id), 2),
        feature_contributions=_feature_contributions(model, x, probability),
        model_version=MODEL_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


def predict_and_alert(metrics: NetworkMetrics, store: DataStore) -> PredictionResponse:
    """Prédit puis journalise une alerte si le seuil MODÉRÉ/CRITIQUE est franchi."""
    result = predict(metrics, store)
    if result.risk_level != "NORMAL":
        dept_name = store.departments[metrics.department_id]["name"]
        store.add_alert(
            department_id=metrics.department_id,
            level=result.risk_level,
            message=f"{dept_name} — risque de coupure H+1 à {result.outage_probability:.0%}. {result.recommendation}",
            probability=result.outage_probability,
        )
    return result
