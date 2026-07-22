"""Stockage en mémoire du prototype.

En production, ce module sera remplacé par TimescaleDB / Kafka. L'interface
(`DataStore`) est volontairement minimale pour rendre le remplacement trivial.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from itertools import count
from threading import Lock

from api.config import get_settings
from api.schemas import Alert, NetworkMetrics


class DataStore:
    def __init__(self) -> None:
        settings = get_settings()
        raw = json.loads(settings.data_file.read_text())
        self.departments: dict[str, dict] = {d["id"]: d for d in raw["departments"]}
        self.history: dict[str, deque[NetworkMetrics]] = {
            dept_id: deque(maxlen=settings.history_maxlen) for dept_id in self.departments
        }
        self.alerts: list[Alert] = []
        self._alert_ids = count(1)
        self._lock = Lock()

    # ── Télémétrie ────────────────────────────────────────────────────────────
    def add_metrics(self, metrics: NetworkMetrics) -> None:
        if metrics.department_id not in self.departments:
            raise KeyError(metrics.department_id)
        if metrics.timestamp is None:
            metrics.timestamp = datetime.now(timezone.utc)
        with self._lock:
            self.history[metrics.department_id].append(metrics)

    def latest_metrics(self, department_id: str) -> NetworkMetrics | None:
        series = self.history.get(department_id)
        return series[-1] if series else None

    def series(self, department_id: str) -> list[NetworkMetrics]:
        return list(self.history.get(department_id, []))

    # ── Alertes ───────────────────────────────────────────────────────────────
    def add_alert(self, department_id: str, level: str, message: str, probability: float) -> Alert:
        with self._lock:
            alert = Alert(
                id=next(self._alert_ids),
                department_id=department_id,
                level=level,
                message=message,
                outage_probability=probability,
                created_at=datetime.now(timezone.utc),
            )
            self.alerts.append(alert)
            return alert

    def acknowledge_alert(self, alert_id: int) -> Alert | None:
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return alert
        return None

    # ── Incidents historiques ────────────────────────────────────────────────
    def incident_cost(self, department_id: str) -> float:
        incidents = self.departments[department_id].get("incidents_2025", [])
        return float(sum(i["cost_eur"] for i in incidents))

    def mean_incident_cost(self, department_id: str) -> float:
        incidents = self.departments[department_id].get("incidents_2025", [])
        if not incidents:
            return 15_000.0  # coût moyen national par défaut
        return float(sum(i["cost_eur"] for i in incidents) / len(incidents))


_store: DataStore | None = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store


def reset_store() -> None:
    """Réinitialise le stockage (utilisé par les tests)."""
    global _store
    _store = None
