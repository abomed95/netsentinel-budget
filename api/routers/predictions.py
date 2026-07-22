"""Routes /predict — cœur du service : probabilité de coupure H+1."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import DataStore, get_department_or_404, get_store
from api.schemas import NetworkMetrics, PredictionResponse
from api.services import predictor

router = APIRouter(prefix="/predict", tags=["Prédiction"])


@router.post("", response_model=PredictionResponse)
def predict_from_metrics(metrics: NetworkMetrics, store: DataStore = Depends(get_store)):
    """Prédit la probabilité de coupure dans les 60 min à partir d'une mesure fournie."""
    get_department_or_404(store, metrics.department_id)
    return predictor.predict_and_alert(metrics, store)


@router.post("/batch", response_model=list[PredictionResponse])
def predict_batch(batch: list[NetworkMetrics], store: DataStore = Depends(get_store)):
    """Prédiction pour plusieurs mesures en une seule requête."""
    for metrics in batch:
        get_department_or_404(store, metrics.department_id)
    return [predictor.predict_and_alert(m, store) for m in batch]


@router.get("/all", response_model=list[PredictionResponse])
def predict_all(store: DataStore = Depends(get_store)):
    """Prédiction pour les 6 départements à partir de leur dernière télémétrie."""
    results = []
    for dept_id in store.departments:
        latest = store.latest_metrics(dept_id)
        if latest is None:
            raise HTTPException(
                status_code=409,
                detail="Aucune télémétrie disponible — appeler d'abord /simulate/tick",
            )
        results.append(predictor.predict_and_alert(latest, store))
    return results


@router.get("/{department_id}", response_model=PredictionResponse)
def predict_department(department_id: str, store: DataStore = Depends(get_store)):
    """Prédiction pour un département à partir de sa dernière télémétrie."""
    get_department_or_404(store, department_id)
    latest = store.latest_metrics(department_id)
    if latest is None:
        raise HTTPException(
            status_code=409,
            detail="Aucune télémétrie disponible — appeler d'abord /simulate/tick",
        )
    return predictor.predict_and_alert(latest, store)
