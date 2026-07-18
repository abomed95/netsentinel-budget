"""Schémas Pydantic partagés par l'API."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Télémétrie ────────────────────────────────────────────────────────────────
class NetworkMetrics(BaseModel):
    """Mesure instantanée remontée par les sondes d'un département."""

    department_id: str = Field(examples=["A"])
    latency_ms: float = Field(ge=0, examples=[95.0])
    packet_loss_pct: float = Field(ge=0, le=100, examples=[4.2])
    bandwidth_mbps: float = Field(ge=0, examples=[45.0])
    cpu_pct: float = Field(ge=0, le=100, examples=[78.0])
    temperature_celsius: float = Field(ge=-20, le=150, examples=[68.0])
    timestamp: datetime | None = None


class TelemetryAck(BaseModel):
    accepted: int
    department_ids: list[str]


# ── Prédiction ────────────────────────────────────────────────────────────────
class PredictionResponse(BaseModel):
    department_id: str
    outage_probability: float = Field(description="Probabilité de coupure dans les 60 min")
    risk_level: str = Field(description="NORMAL | MODÉRÉ | CRITIQUE")
    recommendation: str
    expected_loss_eur: float = Field(
        description="Perte attendue = probabilité × coût moyen d'un incident du département"
    )
    feature_contributions: dict[str, float] = Field(
        description="Contribution locale de chaque métrique au score (méthode d'occlusion)"
    )
    model_version: str
    timestamp: datetime


# ── Anomalies ─────────────────────────────────────────────────────────────────
class AnomalyResponse(BaseModel):
    department_id: str
    is_anomaly: bool
    anomaly_score: float = Field(description="0 = normal, 1 = très anormal")
    method: str = "isolation_forest"
    timestamp: datetime


# ── Prévision ─────────────────────────────────────────────────────────────────
class ForecastPoint(BaseModel):
    timestamp: datetime
    value: float
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    department_id: str
    metric: str
    horizon_minutes: int
    method: str
    points: list[ForecastPoint]


# ── Alertes ───────────────────────────────────────────────────────────────────
class Alert(BaseModel):
    id: int
    department_id: str
    level: str
    message: str
    outage_probability: float
    acknowledged: bool = False
    created_at: datetime


# ── Départements & rapports ───────────────────────────────────────────────────
class DepartmentBaseline(BaseModel):
    latency_ms: float
    packet_loss_pct: float
    bandwidth_mbps: float
    cpu_pct: float
    temp_celsius: float


class DepartmentInfo(BaseModel):
    id: str
    name: str
    region: str
    baseline: DepartmentBaseline
    incident_count_2025: int
    incident_cost_2025_eur: float


class DepartmentStatus(BaseModel):
    department: DepartmentInfo
    latest_metrics: NetworkMetrics | None
    prediction: PredictionResponse | None


class OverviewResponse(BaseModel):
    generated_at: datetime
    network_health_score: float = Field(description="0–100, 100 = réseau parfaitement sain")
    departments_total: int
    departments_critical: int
    departments_moderate: int
    active_alerts: int
    total_incident_cost_2025_eur: float
    expected_annual_savings_eur: float = Field(
        description="Estimation : coût incidents × taux d'incidents évitables par action préventive"
    )
    predictions: list[PredictionResponse]


# ── Simulation ────────────────────────────────────────────────────────────────
class ScenarioRequest(BaseModel):
    department_id: str
    scenario: str = Field(
        default="degradation",
        description="degradation | recovery",
        examples=["degradation"],
    )
    intensity: float = Field(default=1.0, ge=0.1, le=2.0)


class TickResponse(BaseModel):
    ticks: int
    departments: list[str]
    timestamp: datetime
