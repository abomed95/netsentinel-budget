# NetSentinel — image de conteneur pour Google Cloud Run
FROM python:3.11-slim

# Bonnes pratiques Python en conteneur
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances d'abord (cache de couche Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY api/ ./api/
COPY ml/ ./ml/
COPY data/ ./data/

# Pré-entraîne les modèles dans l'image pour éviter l'entraînement au 1er appel
# (démarrage à froid plus rapide sur Cloud Run). Les artefacts sont écrits dans ml/models/.
RUN python -m ml.train

# Cloud Run fournit le port via la variable d'environnement PORT (8080 par défaut).
ENV PORT=8080
EXPOSE 8080

# Un seul worker : le stockage est EN MÉMOIRE (api/store.py), donc non partagé
# entre workers. Pour scaler horizontalement, brancher d'abord un stockage externe.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1
