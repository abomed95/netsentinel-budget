"""Routes /reports — synthèses pour le tableau de bord et le rapport Ministre."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import OverviewResponse
from api.services import predictor

router = APIRouter(prefix="/reports", tags=["Rapports"])

# Part des incidents jugés évitables par une action préventive déclenchée à H-1
PREVENTABLE_RATE = 0.60


@router.get("/overview", response_model=OverviewResponse)
def overview(store: DataStore = Depends(get_store)):
    """Vue d'ensemble du réseau : santé globale, risques, enjeux financiers."""
    predictions = []
    for dept_id in store.departments:
        latest = store.latest_metrics(dept_id)
        if latest is None:
            raise HTTPException(
                status_code=409,
                detail="Aucune télémétrie disponible — appeler d'abord /simulate/tick",
            )
        predictions.append(predictor.predict(latest, store))

    mean_risk = sum(p.outage_probability for p in predictions) / len(predictions)
    total_cost = sum(store.incident_cost(d) for d in store.departments)

    return OverviewResponse(
        generated_at=datetime.now(timezone.utc),
        network_health_score=round(100 * (1 - mean_risk), 1),
        departments_total=len(store.departments),
        departments_critical=sum(1 for p in predictions if p.risk_level == "CRITIQUE"),
        departments_moderate=sum(1 for p in predictions if p.risk_level == "MODÉRÉ"),
        active_alerts=sum(1 for a in store.alerts if not a.acknowledged),
        total_incident_cost_2025_eur=total_cost,
        expected_annual_savings_eur=round(total_cost * PREVENTABLE_RATE, 2),
        predictions=predictions,
    )


@router.get("/incidents")
def incidents(department_id: str | None = None, store: DataStore = Depends(get_store)):
    """Historique des incidents 2025 avec coûts (par département ou global)."""
    if department_id is not None:
        dept = get_department_or_404(store, department_id)
        items = [{**i, "department_id": department_id} for i in dept.get("incidents_2025", [])]
    else:
        items = [
            {**i, "department_id": dept_id}
            for dept_id, dept in store.departments.items()
            for i in dept.get("incidents_2025", [])
        ]
    items.sort(key=lambda i: i["date"])
    return {
        "count": len(items),
        "total_cost_eur": sum(i["cost_eur"] for i in items),
        "total_downtime_min": sum(i["duration_min"] for i in items),
        "incidents": items,
    }
