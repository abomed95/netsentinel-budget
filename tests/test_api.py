"""Tests de bout en bout de l'API NetSentinel."""

import random

import pytest
from fastapi.testclient import TestClient

from api import store as store_module
from api.main import create_app
from api.services import simulator

DEGRADED_METRICS = {
    "department_id": "A",
    "latency_ms": 320.0,
    "packet_loss_pct": 18.0,
    "bandwidth_mbps": 12.0,
    "cpu_pct": 97.0,
    "temperature_celsius": 84.0,
}

HEALTHY_METRICS = {
    "department_id": "E",
    "latency_ms": 15.0,
    "packet_loss_pct": 0.1,
    "bandwidth_mbps": 220.0,
    "cpu_pct": 18.0,
    "temperature_celsius": 36.0,
}


@pytest.fixture()
def client():
    store_module.reset_store()
    simulator.reset_scenarios()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_root_and_health(client):
    assert client.get("/").json()["departments_monitored"] == 6
    assert client.get("/health").json()["status"] == "ok"


def test_lists_six_departments(client):
    departments = client.get("/api/v1/departments").json()
    assert len(departments) == 6
    assert {d["id"] for d in departments} == {"A", "B", "C", "D", "E", "F"}


def test_department_detail_and_404(client):
    detail = client.get("/api/v1/departments/A").json()
    assert detail["department"]["name"] == "Département Alpha"
    assert client.get("/api/v1/departments/Z").status_code == 404


def test_predict_degraded_vs_healthy(client):
    degraded = client.post("/api/v1/predict", json=DEGRADED_METRICS).json()
    healthy = client.post("/api/v1/predict", json=HEALTHY_METRICS).json()

    assert degraded["outage_probability"] > healthy["outage_probability"]
    assert degraded["risk_level"] == "CRITIQUE"
    assert healthy["risk_level"] == "NORMAL"
    assert degraded["expected_loss_eur"] > 0
    assert set(degraded["feature_contributions"]) == {
        "latence_reseau", "perte_paquets", "bande_passante", "charge_cpu", "temperature",
    }


def test_predict_batch(client):
    results = client.post(
        "/api/v1/predict/batch", json=[DEGRADED_METRICS, HEALTHY_METRICS]
    ).json()
    assert [r["department_id"] for r in results] == ["A", "E"]


def test_predict_unknown_department(client):
    response = client.post("/api/v1/predict", json={**HEALTHY_METRICS, "department_id": "Z"})
    assert response.status_code == 404


def test_telemetry_ingest_and_history(client):
    ack = client.post("/api/v1/telemetry", json=[HEALTHY_METRICS]).json()
    assert ack["accepted"] == 1
    latest = client.get("/api/v1/telemetry/E/latest").json()
    assert latest["latency_ms"] == 15.0
    assert len(client.get("/api/v1/telemetry/E/history").json()) == 1


def test_predict_all_requires_telemetry(client):
    assert client.get("/api/v1/predict/all").status_code == 409
    client.post("/api/v1/simulate/tick")
    results = client.get("/api/v1/predict/all").json()
    assert len(results) == 6


def test_anomaly_detection(client):
    degraded = client.post("/api/v1/anomalies/detect", json=DEGRADED_METRICS).json()
    healthy = client.post("/api/v1/anomalies/detect", json=HEALTHY_METRICS).json()
    assert degraded["anomaly_score"] > healthy["anomaly_score"]
    assert degraded["is_anomaly"] is True


def test_forecast(client):
    client.post("/api/v1/simulate/tick", params={"n": 12})
    forecast = client.get(
        "/api/v1/forecast/B", params={"metric": "bandwidth_mbps", "horizon_minutes": 60}
    ).json()
    assert forecast["metric"] == "bandwidth_mbps"
    assert len(forecast["points"]) == 12
    point = forecast["points"][0]
    assert point["lower"] <= point["value"] <= point["upper"]


def test_forecast_unknown_metric(client):
    client.post("/api/v1/simulate/tick", params={"n": 5})
    assert client.get("/api/v1/forecast/B", params={"metric": "nope"}).status_code == 422


def test_scenario_raises_risk_and_creates_alert(client):
    random.seed(0)
    client.post("/api/v1/simulate/tick", params={"n": 3})
    baseline_risk = client.get("/api/v1/predict/A").json()["outage_probability"]

    client.post(
        "/api/v1/simulate/scenario",
        json={"department_id": "A", "scenario": "degradation", "intensity": 2.0},
    )
    client.post("/api/v1/simulate/tick", params={"n": 3})
    degraded = client.get("/api/v1/predict/A").json()

    assert degraded["outage_probability"] > baseline_risk
    assert degraded["risk_level"] == "CRITIQUE"

    alerts = client.get(
        "/api/v1/alerts", params={"department_id": "A", "level": "CRITIQUE"}
    ).json()
    assert alerts, "une alerte doit être générée après franchissement de seuil"

    acked = client.post(f"/api/v1/alerts/{alerts[0]['id']}/acknowledge").json()
    assert acked["acknowledged"] is True


def test_overview_report(client):
    client.post("/api/v1/simulate/tick")
    overview = client.get("/api/v1/reports/overview").json()
    assert overview["departments_total"] == 6
    assert 0 <= overview["network_health_score"] <= 100
    assert overview["expected_annual_savings_eur"] > 0


def test_incidents_report(client):
    report = client.get("/api/v1/reports/incidents").json()
    assert report["count"] == 18  # 5+2+3+3+1+4 incidents 2025
    single = client.get("/api/v1/reports/incidents", params={"department_id": "E"}).json()
    assert single["count"] == 1


def test_api_key_enforced(monkeypatch):
    from api import config

    monkeypatch.setenv("NETSENTINEL_API_KEY", "secret-key")
    config.get_settings.cache_clear()
    store_module.reset_store()
    try:
        with TestClient(create_app()) as protected:
            assert protected.get("/api/v1/departments").status_code == 401
            ok = protected.get("/api/v1/departments", headers={"X-API-Key": "secret-key"})
            assert ok.status_code == 200
    finally:
        config.get_settings.cache_clear()
