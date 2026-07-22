"""Dépendances FastAPI partagées (authentification, stockage)."""

from fastapi import Header, HTTPException, status

from api.config import get_settings
from api.store import DataStore, get_store


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Contrôle d'accès simple par clé API (activé si NETSENTINEL_API_KEY est défini).

    En production : SSO Agent Connect / OAuth2 + mTLS inter-services.
    """
    expected = get_settings().api_key
    if expected is not None and x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide ou absente (en-tête X-API-Key)",
        )


def get_department_or_404(store: DataStore, department_id: str) -> dict:
    dept = store.departments.get(department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail=f"Département inconnu : {department_id}")
    return dept


__all__ = ["require_api_key", "get_department_or_404", "get_store", "DataStore"]
