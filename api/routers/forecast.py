"""Routes /forecast — prévision court terme d'une métrique réseau."""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import ForecastResponse
from api.services import forecaster

router = APIRouter(prefix="/forecast", tags=["Prévision"])


@router.get("/{department_id}", response_model=ForecastResponse)
def forecast_metric(
    department_id: str,
    metric: str = Query(default="bandwidth_mbps", description="Métrique à prévoir"),
    horizon_minutes: int = Query(default=60, ge=5, le=240),
    store: DataStore = Depends(get_store),
):
    """Prévision d'une métrique (tendance + intervalle de confiance 95 %)."""
    get_department_or_404(store, department_id)
    try:
        return forecaster.forecast(
            department_id, store.series(department_id), metric, horizon_minutes
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
