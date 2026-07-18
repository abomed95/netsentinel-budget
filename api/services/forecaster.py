"""Prévision court terme des métriques réseau.

Méthode : tendance linéaire pondérée sur l'historique récent + intervalle de
confiance qui s'élargit avec l'horizon. Suffisant pour un prototype ; sera
remplacé par le LSTM entraîné sur l'historique réel du Ministère.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from api.config import get_settings
from api.schemas import ForecastPoint, ForecastResponse, NetworkMetrics

FORECASTABLE_METRICS = {
    "latency_ms",
    "packet_loss_pct",
    "bandwidth_mbps",
    "cpu_pct",
    "temperature_celsius",
}


def forecast(
    department_id: str,
    series: list[NetworkMetrics],
    metric: str,
    horizon_minutes: int,
) -> ForecastResponse:
    if metric not in FORECASTABLE_METRICS:
        raise ValueError(f"Métrique inconnue : {metric}")
    if len(series) < 3:
        raise ValueError("Historique insuffisant (minimum 3 points) — lancer /simulate/tick")

    settings = get_settings()
    values = np.array([getattr(m, metric) for m in series][-48:])  # 4 dernières heures
    t = np.arange(len(values), dtype=float)

    # Régression linéaire pondérée (les points récents comptent davantage)
    weights = np.linspace(0.3, 1.0, len(values))
    slope, intercept = np.polyfit(t, values, deg=1, w=weights)
    residuals = values - (slope * t + intercept)
    sigma = float(np.std(residuals)) or 1e-6

    step = settings.sample_interval_min
    n_steps = max(1, horizon_minutes // step)
    now = series[-1].timestamp or datetime.now(timezone.utc)

    points = []
    for k in range(1, n_steps + 1):
        value = float(slope * (len(values) - 1 + k) + intercept)
        value = max(0.0, value)
        spread = 1.96 * sigma * np.sqrt(k)  # incertitude croissante avec l'horizon
        points.append(
            ForecastPoint(
                timestamp=now + timedelta(minutes=step * k),
                value=round(value, 2),
                lower=round(max(0.0, value - spread), 2),
                upper=round(value + spread, 2),
            )
        )

    return ForecastResponse(
        department_id=department_id,
        metric=metric,
        horizon_minutes=horizon_minutes,
        method="weighted_linear_trend",
        points=points,
    )
