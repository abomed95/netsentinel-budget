# CLAUDE.md

Guide pour travailler dans ce dépôt. Réponds en français (langue du projet).

## Projet

**NetSentinel** — prototype d'API pour la supervision du réseau des **6 départements**
du Ministère du Budget : prédiction de coupures réseau H+1, détection d'anomalies,
prévision de métriques, alertes et rapports financiers.

⚠️ **Toutes les données sont synthétiques** (générées à partir de baselines réalistes).
Le branchement des données réelles du Ministère est prévu mais pas encore fait — voir
la section « Passage aux données réelles » du README.

## Commandes

```bash
pip install -r requirements.txt              # dépendances
python -m ml.train                           # entraîne les modèles (auto au 1er démarrage sinon)
uvicorn api.main:app --reload --port 8000    # lance l'API
python -m pytest tests/ -v                   # tests (15 tests de bout en bout)
```

- Documentation interactive (Swagger) : http://localhost:8000/docs
- Tableau de bord de démonstration : http://localhost:8000/dashboard

## Architecture

```
api/                 API FastAPI
├── main.py          create_app(), montage des routers sous /api/v1, routes système, /dashboard
├── config.py        Settings (seuils de risque, chemins, clé API) — get_settings() est mis en cache
├── schemas.py       modèles Pydantic partagés (entrées/sorties)
├── store.py         DataStore : stockage EN MÉMOIRE (historique, alertes) — get_store() singleton
├── deps.py          dépendances FastAPI : require_api_key, get_department_or_404
├── routers/         un module par domaine (departments, telemetry, predictions,
│                    anomalies, forecast, alerts, reports, simulation)
└── services/        logique métier : predictor, anomaly, forecaster, simulator
ml/
├── train.py         génération de données synthétiques + entraînement (FEATURES, MODEL_VERSION)
└── models/          artefacts .joblib générés localement — NON versionnés (.gitignore)
data/departments.json  référentiel des 6 départements (baselines + incidents 2025)
tests/test_api.py    tests via TestClient
frontend/            ébauche React (non fonctionnelle) — la démo passe par /dashboard
Dockerfile           image Cloud Run (modèles pré-entraînés dans l'image, écoute sur $PORT)
cloudbuild.yaml      build → push Artifact Registry → deploy Cloud Run
.github/workflows/   ci.yml (tests) + deploy.yml (déploiement Cloud Run sur push main)
```

## Conventions et points d'attention

- **Modèle ML** : `HistGradientBoostingClassifier` (coupure H+1) + `IsolationForest` (anomalies).
  Les modèles s'entraînent automatiquement au premier appel si `ml/models/` est vide.
  Pour brancher les vraies données, remplacer `generate_dataset()` dans `ml/train.py` —
  l'API ne change pas. Un LightGBM/LSTM peut se substituer tant qu'il expose `predict_proba`.
- **Stockage en mémoire** : `store.py` est volontairement minimal (destiné à devenir
  TimescaleDB/Kafka). Il est réinitialisable via `reset_store()` (utilisé par les tests).
- **Explicabilité** : `predictor._feature_contributions()` fait une attribution par occlusion
  (chaque métrique comparée à une valeur « réseau sain »), pas du vrai SHAP.
- **Seuils de risque** dans `config.py` : critique > 0.70, modéré > 0.45.
- **Auth** : si `NETSENTINEL_API_KEY` est défini, l'en-tête `X-API-Key` devient obligatoire
  sur `/api/v1/*`. Les tests d'auth doivent appeler `config.get_settings.cache_clear()`.
- **Simulation** : les routes `/api/v1/simulate/*` (tick, scenario) génèrent la télémétrie
  de démo ; elles disparaîtront quand les sondes réelles alimenteront `POST /telemetry`.
- **Tests** : après modif du code, lancer `python -m pytest tests/ -v`. Certains tests
  utilisent `random.seed()` — garder le déterminisme du simulateur.

## Déploiement (Google Cloud Run)

- **Image** : `Dockerfile` (python:3.11-slim). Les modèles sont **pré-entraînés dans l'image**
  (`RUN python -m ml.train`) pour éviter l'entraînement au premier appel. L'app écoute sur
  la variable `$PORT` fournie par Cloud Run (8080 par défaut).
- **Build/deploy** : `cloudbuild.yaml` (build → push Artifact Registry → deploy Cloud Run).
  Substitutions : `_REGION`, `_SERVICE`, `_REPO`, `_TAG`. ⚠️ `$SHORT_SHA` n'existe que pour
  les builds déclenchés — passer `_TAG` explicitement en CI ou en lancement manuel.
- **CI/CD** : `.github/workflows/deploy.yml` déploie sur push `main` (ou manuellement).
  Requiert la variable `GCP_PROJECT_ID` et le secret `GCP_SA_KEY` (JSON compte de service).
- **max-instances=1** tant que le stockage est en mémoire (`store.py`) : il n'est pas partagé
  entre instances. Brancher un stockage externe avant de scaler horizontalement.

## Git

- Branche de développement : `claude/api-budget-network-prototype-c2rzl6` (ne pas pousser ailleurs).
- Pousser avec `git push -u origin <branche>`.
- Ne pas mentionner l'identifiant de modèle dans les commits/PR.
