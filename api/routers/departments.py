"""Routes /departments — référentiel et état courant des 6 départements."""

from fastapi import APIRouter, Depends

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import DepartmentInfo, DepartmentStatus
from api.services import predictor

router = APIRouter(prefix="/departments", tags=["Départements"])


def _to_info(dept: dict, store: DataStore) -> DepartmentInfo:
    incidents = dept.get("incidents_2025", [])
    return DepartmentInfo(
        id=dept["id"],
        name=dept["name"],
        region=dept["region"],
        baseline=dept["baseline"],
        incident_count_2025=len(incidents),
        incident_cost_2025_eur=store.incident_cost(dept["id"]),
    )


@router.get("", response_model=list[DepartmentInfo])
def list_departments(store: DataStore = Depends(get_store)):
    """Liste des départements supervisés."""
    return [_to_info(d, store) for d in store.departments.values()]


@router.get("/{department_id}", response_model=DepartmentStatus)
def department_status(department_id: str, store: DataStore = Depends(get_store)):
    """Fiche complète : référentiel, dernière télémétrie et prédiction courante."""
    dept = get_department_or_404(store, department_id)
    latest = store.latest_metrics(department_id)
    prediction = predictor.predict(latest, store) if latest else None
    return DepartmentStatus(
        department=_to_info(dept, store),
        latest_metrics=latest,
        prediction=prediction,
    )
