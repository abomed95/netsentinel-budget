"""Routes /alerts — journal des alertes générées par le moteur de prédiction."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import DataStore, get_store
from api.schemas import Alert

router = APIRouter(prefix="/alerts", tags=["Alertes"])


@router.get("", response_model=list[Alert])
def list_alerts(
    department_id: str | None = None,
    level: str | None = Query(default=None, description="CRITIQUE | MODÉRÉ"),
    include_acknowledged: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    store: DataStore = Depends(get_store),
):
    """Alertes les plus récentes en premier."""
    alerts = store.alerts
    if department_id:
        alerts = [a for a in alerts if a.department_id == department_id]
    if level:
        alerts = [a for a in alerts if a.level == level.upper()]
    if not include_acknowledged:
        alerts = [a for a in alerts if not a.acknowledged]
    return sorted(alerts, key=lambda a: a.id, reverse=True)[:limit]


@router.post("/{alert_id}/acknowledge", response_model=Alert)
def acknowledge(alert_id: int, store: DataStore = Depends(get_store)):
    """Acquitte une alerte (prise en compte par l'équipe DSI)."""
    alert = store.acknowledge_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alerte inconnue : {alert_id}")
    return alert
