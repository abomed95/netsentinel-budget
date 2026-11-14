# syntax=docker/dockerfile:1
# NetSentinel — image pour Cloud Run : l'API, et le tableau de bord sous /dashboard/.
#   docker build -t netsentinel-api .

# ---- Tableau de bord React compilé.
FROM node:22-alpine AS dashboard
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html index.js App.js reseau-prediction.jsx vite.config.js ./
COPY dashboard ./dashboard
COPY data ./data
RUN npm run build

FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH PORT=8080 \
    # En production la clé d'API est obligatoire : l'image refuse de démarrer sans elle.
    NETSENTINEL_ENV=production
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin netsentinel
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY --chown=netsentinel:netsentinel api ./api
COPY --chown=netsentinel:netsentinel data ./data
# Servi par l'API sous /dashboard/.
COPY --from=dashboard --chown=netsentinel:netsentinel /app/build ./build
USER netsentinel
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
