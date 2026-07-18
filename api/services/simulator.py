"""Simulateur de télémétrie.

Tant que les données réelles ne sont pas branchées, ce module génère un flux
réaliste : cycle journalier, bruit, et scénarios de dégradation déclenchables
à la demande pour la démonstration (POST /api/v1/simulate/scenario).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from api.schemas import NetworkMetrics
from api.store import DataStore

# Scénarios de dégradation actifs : dept_id -> intensité restante
_active_scenarios: dict[str, float] = {}


def trigger_scenario(department_id: str, scenario: str, intensity: float) -> None:
    if scenario == "degradation":
        _active_scenarios[department_id] = intensity
    else:  # recovery
        _active_scenarios.pop(department_id, None)


def reset_scenarios() -> None:
    _active_scenarios.clear()


def _diurnal_factor(hour: float) -> float:
    """Charge plus élevée aux heures ouvrées (pic vers 10 h et 15 h)."""
    return 1.0 + 0.25 * math.sin((hour - 6) * math.pi / 12) if 7 <= hour <= 19 else 0.85


def generate_sample(store: DataStore, department_id: str, when: datetime | None = None) -> NetworkMetrics:
    baseline = store.departments[department_id]["baseline"]
    now = when or datetime.now(timezone.utc)
    load = _diurnal_factor(now.hour + now.minute / 60)
    noise = lambda s: random.lognormvariate(0, s)  # noqa: E731

    latency = baseline["latency_ms"] * load * noise(0.15)
    loss = baseline["packet_loss_pct"] * load * noise(0.25)
    bandwidth = baseline["bandwidth_mbps"] / load * noise(0.10)
    cpu = baseline["cpu_pct"] * load * noise(0.10)
    temp = baseline["temp_celsius"] * noise(0.05)

    # Application d'un scénario de dégradation (démo / test de bout en bout)
    intensity = _active_scenarios.get(department_id, 0.0)
    if intensity > 0:
        latency *= 1 + 2.5 * intensity
        loss *= 1 + 4.0 * intensity
        bandwidth *= max(0.15, 1 - 0.7 * intensity)
        cpu = min(100.0, cpu * (1 + 0.35 * intensity))
        temp *= 1 + 0.25 * intensity

    return NetworkMetrics(
        department_id=department_id,
        latency_ms=round(latency, 2),
        packet_loss_pct=round(min(100.0, loss), 3),
        bandwidth_mbps=round(bandwidth, 2),
        cpu_pct=round(min(100.0, cpu), 2),
        temperature_celsius=round(min(120.0, temp), 2),
        timestamp=now,
    )


def tick(store: DataStore, n: int = 1) -> list[str]:
    """Génère `n` nouveaux points de mesure pour chaque département."""
    for _ in range(n):
        for dept_id in store.departments:
            store.add_metrics(generate_sample(store, dept_id))
    return list(store.departments)
