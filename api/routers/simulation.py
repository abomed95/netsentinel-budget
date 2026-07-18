"""Routes /simulate — génération de télémétrie synthétique pour la démo.

Ces routes disparaîtront lorsque les sondes réelles alimenteront /telemetry.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import ScenarioRequest, TickResponse
from api.services import simulator

router = APIRouter(prefix="/simulate", tags=["Simulation"])


@router.post("/tick", response_model=TickResponse)
def tick(
    n: int = Query(default=1, ge=1, le=100, description="Nombre de pas de 5 min à générer"),
    store: DataStore = Depends(get_store),
):
    """Génère de nouvelles mesures pour les 6 départements."""
    departments = simulator.tick(store, n=n)
    return TickResponse(ticks=n, departments=departments, timestamp=datetime.now(timezone.utc))


@router.post("/scenario")
def scenario(request: ScenarioRequest, store: DataStore = Depends(get_store)):
    """Déclenche (ou arrête) une dégradation progressive sur un département.

    Exemple démo : `{"department_id": "A", "scenario": "degradation", "intensity": 1.0}`
    puis appeler /simulate/tick et /predict/A pour voir le risque monter.
    """
    get_department_or_404(store, request.department_id)
    simulator.trigger_scenario(request.department_id, request.scenario, request.intensity)
    return {
        "department_id": request.department_id,
        "scenario": request.scenario,
        "intensity": request.intensity,
        "status": "armed" if request.scenario == "degradation" else "cleared",
    }
