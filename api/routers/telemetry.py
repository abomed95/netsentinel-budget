"""Routes /telemetry — ingestion et consultation des mesures réseau."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import NetworkMetrics, TelemetryAck

router = APIRouter(prefix="/telemetry", tags=["Télémétrie"])


@router.post("", response_model=TelemetryAck, status_code=202)
def ingest(batch: list[NetworkMetrics], store: DataStore = Depends(get_store)):
    """Ingestion d'un lot de mesures (poussées par les sondes des sites).

    En production, ce point d'entrée sera remplacé par un consommateur Kafka.
    """
    for metrics in batch:
        get_department_or_404(store, metrics.department_id)
        store.add_metrics(metrics)
    return TelemetryAck(
        accepted=len(batch),
        department_ids=sorted({m.department_id for m in batch}),
    )


@router.get("/{department_id}/latest", response_model=NetworkMetrics)
def latest(department_id: str, store: DataStore = Depends(get_store)):
    """Dernière mesure connue pour un département."""
    get_department_or_404(store, department_id)
    metrics = store.latest_metrics(department_id)
    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune télémétrie — envoyer des mesures ou appeler /simulate/tick",
        )
    return metrics


@router.get("/{department_id}/history", response_model=list[NetworkMetrics])
def history(
    department_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    store: DataStore = Depends(get_store),
):
    """Historique récent (jusqu'à 24 h glissantes)."""
    get_department_or_404(store, department_id)
    return store.series(department_id)[-limit:]
