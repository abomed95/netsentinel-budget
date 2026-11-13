"""
NetSentinel — API FastAPI de prédiction de coupures réseau H+1
Ministère du Budget

État réel du prototype : le score est une combinaison pondérée de cinq métriques
(heuristique à poids fixes). Aucun modèle entraîné n'est chargé ; l'emplacement
pour le brancher est `compute_contributions`.
"""
from __future__ import annotations

import hmac
import json
import logging
import math
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Configuration (variables d'environnement) ───────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = Path(os.getenv("NETSENTINEL_DATA_FILE", BASE_DIR / "data" / "arcep_sample.json"))
# Origines autorisées à appeler l'API depuis un navigateur, séparées par des
# virgules. Vide = aucune : « * » ouvrait l'API à n'importe quel site.
CORS_ORIGINS = [o.strip() for o in os.getenv("NETSENTINEL_CORS_ORIGINS", "").split(",") if o.strip()]
# Clé d'accès aux routes de prédiction. Vide = accès libre (développement).
API_KEY = os.getenv("NETSENTINEL_API_KEY", "")
# Refuse de démarrer sans clé quand on se déclare en production.
ENVIRONMENT = os.getenv("NETSENTINEL_ENV", "development")
MAX_BATCH_SIZE = int(os.getenv("NETSENTINEL_MAX_BATCH", "100"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("NETSENTINEL_RATE_LIMIT", "120"))
# Proxys de confiance devant l'API (1 sur Cloud Run en direct).
TRUSTED_PROXY_HOPS = max(1, int(os.getenv("NETSENTINEL_TRUSTED_PROXY_HOPS", "1")))


# ── Journalisation structurée (une ligne JSON, format Cloud Logging) ────────
class JsonFormatter(logging.Formatter):
    _standard = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        entry = {k: v for k, v in record.__dict__.items() if k not in self._standard}
        entry.update({
            "severity": record.levelname,
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        })
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logging.getLogger().handlers = [_handler]
logging.getLogger().setLevel(os.getenv("NETSENTINEL_LOG_LEVEL", "INFO").upper())
log = logging.getLogger("netsentinel")

if ENVIRONMENT == "production" and not API_KEY:
    raise RuntimeError(
        "NETSENTINEL_API_KEY est obligatoire en production : sans elle, n'importe qui "
        "peut interroger l'API de prédiction."
    )

app = FastAPI(
    title="NetSentinel API",
    description="API de prédiction de coupures réseau H+1 — Ministère du Budget",
    version="1.1.0",
)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    # Ignoré par les navigateurs en HTTP : sans effet en développement local.
    response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Erreurs de validation sans recopier la valeur reçue.

    Le gestionnaire par défaut renvoie l'entrée fautive : avec un `NaN`, la
    réponse elle-même n'était plus du JSON valide et l'API plantait (500).
    """
    errors = [{"champ": ".".join(str(part) for part in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Données invalides", "errors": errors})


# ── Accès : clé d'API et limitation de débit ────────────────────────────────
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
_MAX_KEYS = 20_000


def client_ip(request: Request) -> str:
    """IP cliente, lue à DROITE de X-Forwarded-For (la gauche est fournie par le client)."""
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if parts:
        return parts[max(0, len(parts) - TRUSTED_PROXY_HOPS)]
    return request.client.host if request.client else "inconnue"


def rate_limit(request: Request) -> None:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return
    now, key = time.monotonic(), client_ip(request)
    with _lock:
        # Borne la mémoire : sans purge, chaque nouvelle adresse resterait à vie.
        if len(_hits) > _MAX_KEYS:
            for stale in [k for k, v in _hits.items() if not v or now - v[-1] > 60]:
                del _hits[stale]
        stamps = _hits[key]
        while stamps and now - stamps[0] > 60:
            stamps.popleft()
        if len(stamps) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(429, "Trop de requêtes. Réessayez dans une minute.",
                                headers={"Retry-After": "60"})
        stamps.append(now)


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if not API_KEY:
        return
    # Comparaison à durée constante : ne révèle pas la clé caractère par caractère.
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), API_KEY.encode()):
        raise HTTPException(401, "Clé d'API absente ou invalide (en-tête X-API-Key).")


protected = [Depends(rate_limit), Depends(require_api_key)]


# ── Schémas ──────────────────────────────────────────────────────────────────
class NetworkMetrics(BaseModel):
    """Métriques d'un département. Les bornes rejettent les valeurs physiquement
    impossibles, qui produisaient auparavant un score faux sans aucune erreur."""
    model_config = ConfigDict(extra="forbid")

    department_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w .-]+$")
    latency_ms: float = Field(ge=0, le=60_000)
    packet_loss_pct: float = Field(ge=0, le=100)
    bandwidth_mbps: float = Field(ge=0, le=1_000_000)
    cpu_pct: float = Field(ge=0, le=100)
    temperature_celsius: float = Field(ge=-50, le=150)
    timestamp: str | None = Field(default=None, max_length=40)

    @field_validator("latency_ms", "packet_loss_pct", "bandwidth_mbps", "cpu_pct", "temperature_celsius")
    @classmethod
    def finite(cls, value: float) -> float:
        # NaN et l'infini passent les comparaisons ge/le et corrompraient le score.
        if not math.isfinite(value):
            raise ValueError("valeur numérique finie attendue")
        return value


class PredictionResponse(BaseModel):
    department_id: str
    outage_probability: float
    risk_level: str
    recommendation: str
    shap_values: dict[str, float]
    timestamp: str


# ── Logique de prédiction (remplacer par le vrai modèle LightGBM/LSTM) ───────
# Pondération de chaque métrique dans le score (à affiner avec les vraies données).
WEIGHTS = {
    "latence_reseau": 0.30,
    "perte_paquets": 0.25,
    "bande_passante": 0.20,
    "charge_cpu": 0.15,
    "temperature": 0.10,
}


def compute_contributions(metrics: NetworkMetrics) -> dict[str, float]:
    """Contribution de chaque métrique au score, entre 0 et son poids.

    C'est le point de branchement d'un modèle entraîné : en production, charger le
    modèle LightGBM depuis un fichier et renvoyer ses vraies valeurs SHAP.
    Chaque terme est borné entre 0 et 1 : une température négative ne doit pas
    faire BAISSER le risque global.
    """
    normalized = {
        "latence_reseau": metrics.latency_ms / 150,
        "perte_paquets": metrics.packet_loss_pct / 10,
        "bande_passante": 1 - metrics.bandwidth_mbps / 250,
        "charge_cpu": metrics.cpu_pct / 100,
        "temperature": metrics.temperature_celsius / 85,
    }
    return {name: round(WEIGHTS[name] * min(1.0, max(0.0, value)), 4) for name, value in normalized.items()}


def compute_risk_score(metrics: NetworkMetrics) -> float:
    """Score de risque composite : somme des contributions, borné à [0,01 ; 0,99]."""
    score = sum(compute_contributions(metrics).values())
    return round(min(0.99, max(0.01, score)), 4)


def get_risk_level(probability: float) -> tuple[str, str]:
    if probability > 0.70:
        return "CRITIQUE", "Intervention préventive immédiate recommandée"
    elif probability > 0.45:
        return "MODÉRÉ", "Surveillance renforcée conseillée"
    return "NORMAL", "Aucune action requise — réseau stable"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_prediction(metrics: NetworkMetrics) -> PredictionResponse:
    contributions = compute_contributions(metrics)
    probability = round(min(0.99, max(0.01, sum(contributions.values()))), 4)
    risk_level, recommendation = get_risk_level(probability)
    return PredictionResponse(
        department_id=metrics.department_id,
        outage_probability=probability,
        risk_level=risk_level,
        recommendation=recommendation,
        shap_values=contributions,
        timestamp=_now(),
    )


@lru_cache(maxsize=1)
def load_departments() -> list[dict]:
    """Départements surveillés, lus une fois (le fichier ne change pas à l'exécution)."""
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)["departments"]


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "NetSentinel API",
        "version": app.version,
        "status": "operational",
        "ministere": "Budget",
    }


@app.get("/health")
def health():
    """Sonde de santé : aucune dépendance externe."""
    return {"status": "ok", "timestamp": _now()}


@app.post("/predict", response_model=PredictionResponse, dependencies=protected)
def predict(metrics: NetworkMetrics):
    """
    Prédit la probabilité de coupure réseau dans les 60 prochaines minutes.
    """
    prediction = build_prediction(metrics)
    if prediction.risk_level == "CRITIQUE":
        log.warning("Risque critique", extra={"department_id": metrics.department_id,
                                              "probability": prediction.outage_probability})
    return prediction


@app.post("/predict/batch", response_model=list[PredictionResponse], dependencies=protected)
def predict_batch(metrics_list: Annotated[list[NetworkMetrics], Field(min_length=1, max_length=MAX_BATCH_SIZE)]):
    """Prédiction pour plusieurs départements en une seule requête."""
    return [build_prediction(m) for m in metrics_list]


@app.get("/departments", dependencies=protected)
def list_departments():
    """Liste des départements surveillés."""
    try:
        departments = load_departments()
    except (OSError, KeyError, json.JSONDecodeError):
        log.exception("Fichier des départements illisible", extra={"path": str(DATA_FILE)})
        raise HTTPException(503, "Référentiel des départements indisponible.")
    ids = [d["id"] for d in departments]
    return {"departments": ids, "count": len(ids)}


# ── Lancement ─────────────────────────────────────────────────────────────────
# uvicorn api.main:app --reload --port 8000
