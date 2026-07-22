# 🇫🇷 NetSentinel — Prédiction de Coupure Réseau H+1

> Prototype IA développé pour le **Ministère du Budget** — supervision du réseau des **6 départements** et prédiction des coupures avec 60 minutes d'avance.

![Status](https://img.shields.io/badge/statut-prototype-blue)
![API](https://img.shields.io/badge/API-FastAPI-009688)
![Tests](https://img.shields.io/badge/tests-15%20passants-brightgreen)

---

## 🎯 Objectif

Anticiper les coupures réseau dans les départements ministériels **1 heure avant** qu'elles surviennent, détecter les comportements anormaux (dérives, attaques) et chiffrer l'enjeu financier, afin de déclencher des actions préventives et réduire les pertes opérationnelles.

⚠️ **Prototype** : toutes les données sont synthétiques (générées à partir de baselines réalistes). Le branchement des données réelles du Ministère est prévu — voir [Passage aux données réelles](#-passage-aux-données-réelles).

---

## 🚀 Démarrage rapide

```bash
pip install -r requirements.txt
python -m ml.train                       # entraîne les modèles (sinon fait automatiquement au 1er appel)
uvicorn api.main:app --reload --port 8000
```

- **Documentation interactive (Swagger)** : http://localhost:8000/docs
- **Tableau de bord de démonstration** : http://localhost:8000/dashboard
- **Tests** : `python -m pytest tests/ -v`

### Démo en 3 requêtes

```bash
# 1. Générer de la télémétrie simulée pour les 6 départements
curl -X POST "http://localhost:8000/api/v1/simulate/tick?n=12"

# 2. Prédire le risque de coupure H+1 partout
curl "http://localhost:8000/api/v1/predict/all"

# 3. Déclencher une dégradation sur le département A et voir le risque monter
curl -X POST http://localhost:8000/api/v1/simulate/scenario \
  -H "Content-Type: application/json" \
  -d '{"department_id": "A", "scenario": "degradation", "intensity": 1.5}'
curl -X POST "http://localhost:8000/api/v1/simulate/tick?n=3"
curl "http://localhost:8000/api/v1/predict/A"
```

---

## 📡 API v1 — points d'entrée

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/v1/departments` | Référentiel des 6 départements |
| GET | `/api/v1/departments/{id}` | Fiche : baseline, dernière télémétrie, prédiction |
| POST | `/api/v1/telemetry` | Ingestion d'un lot de mesures (sondes) |
| GET | `/api/v1/telemetry/{id}/latest` · `/history` | Consultation de la télémétrie |
| POST | `/api/v1/predict` · `/predict/batch` | Prédiction à partir de mesures fournies |
| GET | `/api/v1/predict/all` · `/predict/{id}` | Prédiction depuis la dernière télémétrie |
| POST | `/api/v1/anomalies/detect` | Détection d'anomalie (Isolation Forest) |
| GET | `/api/v1/anomalies/{id}` | Anomalie sur la dernière télémétrie |
| GET | `/api/v1/forecast/{id}?metric=&horizon_minutes=` | Prévision d'une métrique + intervalle de confiance |
| GET | `/api/v1/alerts` · POST `/alerts/{id}/acknowledge` | Journal et acquittement des alertes |
| GET | `/api/v1/reports/overview` | Santé globale, risques, enjeux financiers |
| GET | `/api/v1/reports/incidents` | Historique incidents 2025 + coûts |
| POST | `/api/v1/simulate/tick` · `/simulate/scenario` | Simulation (démo uniquement) |

Chaque prédiction retourne : probabilité de coupure H+1, niveau de risque (NORMAL / MODÉRÉ / CRITIQUE), recommandation, **perte financière attendue** et **contribution de chaque métrique** au score (explicabilité).

🔐 **Authentification** : définir `NETSENTINEL_API_KEY` rend l'en-tête `X-API-Key` obligatoire sur `/api/v1/*`. (Production : SSO Agent Connect / OAuth2.)

---

## 🧠 Modèles

| Tâche | Modèle | Détail |
|---|---|---|
| Coupure H+1 | Gradient Boosting (`HistGradientBoostingClassifier`) | Entraîné sur données synthétiques dérivées des baselines ; AUC ≈ 0.81 sur le jeu de test synthétique |
| Anomalies | Isolation Forest | Entraîné sur le trafic « normal » uniquement |
| Prévision métriques | Tendance linéaire pondérée | Intervalle de confiance 95 % s'élargissant avec l'horizon |
| Explicabilité | Attribution par occlusion | Contribution locale de chaque métrique vs référence « réseau sain » |

Entraînement automatique au premier démarrage si `ml/models/` est vide, ou manuel : `python -m ml.train`.

---

## 📂 Structure du projet

```
netsentinel-budget/
├── api/                    # API FastAPI
│   ├── main.py             # Création de l'app, routes système, /dashboard
│   ├── config.py           # Configuration (seuils, chemins, clé API)
│   ├── schemas.py          # Modèles Pydantic
│   ├── store.py            # Stockage en mémoire (→ TimescaleDB en prod)
│   ├── deps.py             # Dépendances (auth, 404)
│   ├── routers/            # Un module par domaine fonctionnel
│   ├── services/           # Prédiction, anomalies, prévision, simulateur
│   └── static/dashboard.html  # Tableau de bord de démonstration
├── ml/
│   ├── train.py            # Génération données synthétiques + entraînement
│   └── models/             # Artefacts entraînés (non versionnés)
├── data/departments.json   # Référentiel 6 départements + incidents 2025
├── tests/test_api.py       # 15 tests de bout en bout
├── frontend/               # Ébauche React (voir frontend/README.md)
└── .github/workflows/ci.yml
```

---

## 🔄 Passage aux données réelles

Le prototype est conçu pour que le branchement des données du Ministère soit localisé :

1. **Télémétrie** : remplacer `api/services/simulator.py` par les sondes réelles poussant sur `POST /api/v1/telemetry` (ou un consommateur Kafka), et supprimer les routes `/simulate/*`.
2. **Entraînement** : remplacer `generate_dataset()` dans `ml/train.py` par un chargeur de l'historique télémétrie + incidents réels. L'API ne change pas.
3. **Stockage** : remplacer `api/store.py` (en mémoire) par TimescaleDB/PostgreSQL — l'interface `DataStore` est volontairement minimale.
4. **Modèles** : LightGBM / LSTM peuvent se substituer au Gradient Boosting sans toucher aux routes (même interface `predict_proba`).

---

## 🗺️ Feuille de route

- [x] Réorganisation du dépôt et API modulaire versionnée
- [x] Prototype fonctionnel : prédiction, anomalies, prévision, alertes, rapports
- [x] Tableau de bord de démonstration + tests automatisés + CI
- [ ] Intégration données réelles Ministère (télémétrie + historique incidents)
- [ ] Ré-entraînement LightGBM/LSTM sur historique réel + calibration des seuils
- [ ] Stockage TimescaleDB + ingestion Kafka
- [ ] Authentification SSO + déploiement production

---

## 📬 Contact

Projet développé dans le cadre d'un appel d'offre — **Ministère du Budget, des Comptes Publics et de la Réforme de l'État**.

*Données du prototype 100 % synthétiques, inspirées de sources open source (ARCEP, ANSSI). Les performances réelles seront mesurées après entraînement sur les données opérationnelles du Ministère.*
