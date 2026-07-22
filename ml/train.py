"""Entraînement du modèle de prédiction de coupure H+1.

Le prototype s'entraîne sur des données synthétiques générées à partir des
baselines des départements (data/departments.json). Lorsque les données
réelles du Ministère seront disponibles, il suffira de remplacer
`generate_dataset` par un chargeur de l'historique télémétrie + incidents,
sans toucher à l'API.

Usage en ligne de commande :
    python -m ml.train
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "departments.json"
MODEL_DIR = BASE_DIR / "ml" / "models"

FEATURES = [
    "latency_ms",
    "packet_loss_pct",
    "bandwidth_mbps",
    "cpu_pct",
    "temperature_celsius",
    "hour_of_day",
]

MODEL_VERSION = "proto-hgb-1"


def _latent_risk(x: np.ndarray) -> np.ndarray:
    """Risque latent utilisé pour étiqueter les données synthétiques.

    Reproduit la physique attendue d'une coupure : latence et pertes élevées,
    bande passante effondrée, CPU et température proches des limites matérielles,
    avec un effet heure de pointe.
    """
    latency, loss, bandwidth, cpu, temp, hour = x.T
    score = (
        0.30 * np.clip(latency / 150, 0, 1)
        + 0.25 * np.clip(loss / 10, 0, 1)
        + 0.20 * np.clip(1 - bandwidth / 250, 0, 1)
        + 0.15 * np.clip(cpu / 100, 0, 1) ** 2
        + 0.10 * np.clip((temp - 30) / 55, 0, 1) ** 2
    )
    peak = np.isin(hour, [9, 10, 11, 14, 15, 16]).astype(float)
    return np.clip(score + 0.05 * peak, 0, 1)


def generate_dataset(n_samples: int = 20_000, seed: int = 42):
    """Génère un jeu de données synthétique réaliste autour des baselines."""
    rng = np.random.default_rng(seed)
    departments = json.loads(DATA_FILE.read_text())["departments"]
    baselines = np.array(
        [
            [
                d["baseline"]["latency_ms"],
                d["baseline"]["packet_loss_pct"],
                d["baseline"]["bandwidth_mbps"],
                d["baseline"]["cpu_pct"],
                d["baseline"]["temp_celsius"],
            ]
            for d in departments
        ]
    )

    idx = rng.integers(0, len(baselines), size=n_samples)
    base = baselines[idx]

    # Bruit multiplicatif quotidien + épisodes de dégradation (queues lourdes)
    noise = rng.lognormal(mean=0.0, sigma=0.25, size=base.shape)
    x = base * noise
    degraded = rng.random(n_samples) < 0.18
    x[degraded, 0] *= rng.uniform(1.5, 3.5, degraded.sum())   # latence
    x[degraded, 1] *= rng.uniform(2.0, 6.0, degraded.sum())   # pertes
    x[degraded, 2] *= rng.uniform(0.2, 0.6, degraded.sum())   # bande passante
    x[degraded, 3] = np.clip(x[degraded, 3] * rng.uniform(1.2, 1.6, degraded.sum()), 0, 100)
    x[degraded, 4] *= rng.uniform(1.1, 1.4, degraded.sum())   # température

    hour = rng.integers(0, 24, size=n_samples).astype(float)
    x = np.column_stack([x, hour])
    x[:, 1] = np.clip(x[:, 1], 0, 100)
    x[:, 3] = np.clip(x[:, 3], 0, 100)

    risk = _latent_risk(x)
    y = (rng.random(n_samples) < np.clip(risk * 1.15 - 0.08, 0, 1)).astype(int)
    return x, y


def train(save: bool = True, verbose: bool = False) -> dict:
    """Entraîne le classifieur de coupure et le détecteur d'anomalies."""
    x, y = generate_dataset()
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, max_depth=6, random_state=42
    )
    clf.fit(x_train, y_train)

    proba = clf.predict_proba(x_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {
        "model_version": MODEL_VERSION,
        "n_train": len(x_train),
        "n_test": len(x_test),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "f1": round(float(f1_score(y_test, pred)), 4),
    }

    # Détecteur d'anomalies entraîné sur le trafic "normal" uniquement
    iso = IsolationForest(n_estimators=150, contamination=0.05, random_state=42)
    iso.fit(x_train[y_train == 0][:, :5])

    if save:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(clf, MODEL_DIR / "outage_model.joblib")
        joblib.dump(iso, MODEL_DIR / "anomaly_model.joblib")
        (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    if verbose:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return metrics


if __name__ == "__main__":
    train(verbose=True)
