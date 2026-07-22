"""Configuration centrale de NetSentinel."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    app_name: str = "NetSentinel API"
    description: str = (
        "Prédiction de coupures réseau H+1 et supervision des 6 départements "
        "du Ministère du Budget"
    )
    version: str = "2.0.0"

    data_file: Path = BASE_DIR / "data" / "departments.json"
    model_dir: Path = BASE_DIR / "ml" / "models"

    # Clé API optionnelle : si NETSENTINEL_API_KEY est défini, l'en-tête
    # X-API-Key devient obligatoire sur les routes /api/v1.
    api_key: str | None = Field(
        default_factory=lambda: os.getenv("NETSENTINEL_API_KEY") or None
    )

    # Historique conservé par département (288 points × 5 min = 24 h)
    history_maxlen: int = 288
    sample_interval_min: int = 5

    # Seuils de risque
    critical_threshold: float = 0.70
    moderate_threshold: float = 0.45


@lru_cache
def get_settings() -> Settings:
    return Settings()
