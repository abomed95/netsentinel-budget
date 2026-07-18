"""Détection d'anomalies réseau (Isolation Forest).

Détecte les comportements hors profil qui ne correspondent pas forcément à un
risque de coupure imminent : dérives lentes, valeurs incohérentes de sondes,
attaques (ex. DDoS) modifiant la signature du trafic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

import joblib
import numpy as np

from api.config import get_settings
from api.schemas import AnomalyResponse, NetworkMetrics
from ml.train import train

_lock = Lock()
_model = None


def get_model():
    global _model
    with _lock:
        if _model is None:
            path = get_settings().model_dir / "anomaly_model.joblib"
            if not path.exists():
                train(save=True)
            _model = joblib.load(path)
        return _model


def detect(metrics: NetworkMetrics) -> AnomalyResponse:
    model = get_model()
    x = np.array(
        [
            [
                metrics.latency_ms,
                metrics.packet_loss_pct,
                metrics.bandwidth_mbps,
                metrics.cpu_pct,
                metrics.temperature_celsius,
            ]
        ]
    )
    # score_samples : proche de 0 = normal, très négatif = anormal
    raw = float(model.score_samples(x)[0])
    score = float(np.clip(-raw * 2 - 0.4, 0, 1))
    return AnomalyResponse(
        department_id=metrics.department_id,
        is_anomaly=bool(model.predict(x)[0] == -1),
        anomaly_score=round(score, 4),
        timestamp=datetime.now(timezone.utc),
    )
