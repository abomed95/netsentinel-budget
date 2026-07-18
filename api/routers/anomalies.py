"""Routes /anomalies — détection de comportements réseau hors profil."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import AnomalyResponse, NetworkMetrics
from api.services import anomaly

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.post("/detect", response_model=AnomalyResponse)
def detect(metrics: NetworkMetrics, store: DataStore = Depends(get_store)):
    """Analyse une mesure fournie (Isolation Forest)."""
    get_department_or_404(store, metrics.department_id)
    return anomaly.detect(metrics)


@router.get("/{department_id}", response_model=AnomalyResponse)
def detect_latest(department_id: str, store: DataStore = Depends(get_store)):
    """Analyse la dernière télémétrie connue du département."""
    get_department_or_404(store, department_id)
    latest = store.latest_metrics(department_id)
    if latest is None:
        raise HTTPException(
            status_code=409,
            detail="Aucune télémétrie disponible — appeler d'abord /simulate/tick",
        )
    return anomaly.detect(latest)
