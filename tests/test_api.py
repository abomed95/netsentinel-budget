"""Tests de l'API NetSentinel : score, seuils, validation, accès."""
import importlib

import pytest
from fastapi.testclient import TestClient

import api.main as main

SAIN = {"department_id": "A", "latency_ms": 20, "packet_loss_pct": 0.1,
        "bandwidth_mbps": 240, "cpu_pct": 20, "temperature_celsius": 35}
CRITIQUE = {"department_id": "B", "latency_ms": 400, "packet_loss_pct": 12,
            "bandwidth_mbps": 5, "cpu_pct": 97, "temperature_celsius": 84}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "")
    main._hits.clear()
    return TestClient(main.app)


# ── Score ────────────────────────────────────────────────────────────────────
class TestScore:
    def test_reseau_sain_est_normal(self, client):
        body = client.post("/predict", json=SAIN).json()
        assert body["risk_level"] == "NORMAL"
        assert body["outage_probability"] < 0.45

    def test_reseau_degrade_est_critique(self, client):
        body = client.post("/predict", json=CRITIQUE).json()
        assert body["risk_level"] == "CRITIQUE"
        assert body["outage_probability"] > 0.70

    def test_le_score_est_la_somme_des_contributions(self, client):
        body = client.post("/predict", json=CRITIQUE).json()
        assert round(sum(body["shap_values"].values()), 4) == pytest.approx(body["outage_probability"], abs=1e-3)
        assert set(body["shap_values"]) == set(main.WEIGHTS)

    def test_les_poids_somment_a_un(self):
        assert sum(main.WEIGHTS.values()) == pytest.approx(1.0)

    def test_chaque_contribution_reste_entre_zero_et_son_poids(self):
        extreme = main.NetworkMetrics(department_id="X", latency_ms=60_000, packet_loss_pct=100,
                                      bandwidth_mbps=0, cpu_pct=100, temperature_celsius=150)
        for name, value in main.compute_contributions(extreme).items():
            assert 0 <= value <= main.WEIGHTS[name]
        # Une température négative ne doit pas faire BAISSER le risque global.
        froid = main.NetworkMetrics(**{**SAIN, "temperature_celsius": -40})
        assert main.compute_contributions(froid)["temperature"] == 0

    def test_score_borne(self):
        assert main.compute_risk_score(main.NetworkMetrics(**CRITIQUE)) <= 0.99
        parfait = main.NetworkMetrics(department_id="X", latency_ms=0, packet_loss_pct=0,
                                      bandwidth_mbps=1000, cpu_pct=0, temperature_celsius=0)
        assert main.compute_risk_score(parfait) == 0.01

    @pytest.mark.parametrize("probabilite,niveau", [
        (0.71, "CRITIQUE"), (0.70, "MODÉRÉ"), (0.46, "MODÉRÉ"), (0.45, "NORMAL"), (0.0, "NORMAL"),
    ])
    def test_seuils_de_risque(self, probabilite, niveau):
        assert main.get_risk_level(probabilite)[0] == niveau

    def test_horodatage_avec_fuseau(self, client):
        assert client.post("/predict", json=SAIN).json()["timestamp"].endswith("+00:00")


# ── Validation ───────────────────────────────────────────────────────────────
class TestValidation:
    @pytest.mark.parametrize("champ,valeur", [
        ("latency_ms", -1), ("packet_loss_pct", 101), ("cpu_pct", 500),
        ("bandwidth_mbps", -5), ("temperature_celsius", 1000), ("department_id", ""),
        ("department_id", "<script>"),
    ])
    def test_valeur_impossible_refusee(self, client, champ, valeur):
        assert client.post("/predict", json={**SAIN, champ: valeur}).status_code == 422

    def test_nan_et_infini_refuses(self, client):
        for valeur in ("NaN", "Infinity"):
            brut = '{"department_id":"A","latency_ms":%s,"packet_loss_pct":1,"bandwidth_mbps":100,' \
                   '"cpu_pct":10,"temperature_celsius":30}' % valeur
            response = client.post("/predict", content=brut, headers={"content-type": "application/json"})
            assert response.status_code == 422

    def test_champ_inconnu_refuse(self, client):
        assert client.post("/predict", json={**SAIN, "admin": True}).status_code == 422

    def test_lot_vide_ou_trop_grand_refuse(self, client):
        assert client.post("/predict/batch", json=[]).status_code == 422
        trop = [SAIN] * (main.MAX_BATCH_SIZE + 1)
        assert client.post("/predict/batch", json=trop).status_code == 422

    def test_lot_valide(self, client):
        body = client.post("/predict/batch", json=[SAIN, CRITIQUE]).json()
        assert [p["risk_level"] for p in body] == ["NORMAL", "CRITIQUE"]


# ── Routes de service ────────────────────────────────────────────────────────
class TestRoutes:
    def test_sante_et_racine(self, client):
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/").json()["service"] == "NetSentinel API"

    def test_departements_lus_dans_le_fichier(self, client):
        body = client.get("/departments").json()
        assert body["count"] == len(body["departments"]) == 5
        assert "A" in body["departments"]

    def test_referentiel_absent_donne_une_erreur_propre(self, client, monkeypatch, tmp_path):
        main.load_departments.cache_clear()
        monkeypatch.setattr(main, "DATA_FILE", tmp_path / "absent.json")
        response = client.get("/departments")
        main.load_departments.cache_clear()
        assert response.status_code == 503
        assert "absent.json" not in response.text

    def test_en_tetes_de_securite(self, client):
        headers = client.get("/health").headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert "max-age=" in headers["strict-transport-security"]

    def test_aucune_origine_tierce_par_defaut(self, client):
        response = client.get("/health", headers={"Origin": "https://pirate.example"})
        assert "access-control-allow-origin" not in response.headers


# ── Accès ────────────────────────────────────────────────────────────────────
class TestAcces:
    def test_cle_d_api_exigee_quand_elle_est_configuree(self, client, monkeypatch):
        monkeypatch.setattr(main, "API_KEY", "cle-de-test-0123456789")
        assert client.post("/predict", json=SAIN).status_code == 401
        assert client.post("/predict", json=SAIN, headers={"X-API-Key": "fausse"}).status_code == 401
        assert client.get("/departments").status_code == 401
        ok = client.post("/predict", json=SAIN, headers={"X-API-Key": "cle-de-test-0123456789"})
        assert ok.status_code == 200
        # La sonde de santé reste accessible sans clé.
        assert client.get("/health").status_code == 200

    def test_limitation_de_debit_par_adresse(self, client, monkeypatch):
        monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 3)
        entetes = lambda n: {"X-Forwarded-For": f"10.0.0.{n}, 203.0.113.7"}  # noqa: E731
        # La partie gauche de l'en-tête change à chaque appel : elle ne doit pas compter.
        codes = [client.post("/predict", json=SAIN, headers=entetes(n)).status_code for n in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        # Une autre adresse réelle n'est pas pénalisée.
        autre = client.post("/predict", json=SAIN, headers={"X-Forwarded-For": "203.0.113.8"})
        assert autre.status_code == 200

    def test_production_sans_cle_refuse_de_demarrer(self, monkeypatch):
        monkeypatch.setenv("NETSENTINEL_ENV", "production")
        monkeypatch.delenv("NETSENTINEL_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="NETSENTINEL_API_KEY"):
            importlib.reload(main)
        monkeypatch.undo()
        importlib.reload(main)
