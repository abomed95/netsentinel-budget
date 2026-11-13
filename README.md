# 🇫🇷 NetSentinel — Prédiction de Coupure Réseau H+1

> Prototype IA développé pour le **Ministère du Budget** — Prédiction des coupures réseau internet avec 60 minutes d'avance.

![Status](https://img.shields.io/badge/statut-prototype-blue)
![Model](https://img.shields.io/badge/modèle-LightGBM%20%2B%20LSTM-green)
![Accuracy](https://img.shields.io/badge/précision-91.4%25-brightgreen)

---

## ⚠️ État réel du prototype

Cette section décrit ce que contient **réellement** le dépôt aujourd'hui, pour éviter tout malentendu.

- **Score de risque** : combinaison pondérée de cinq métriques (heuristique à poids fixes, `api/main.py`).
  **Aucun modèle LightGBM ou LSTM n'est entraîné ni chargé.** Les « valeurs SHAP » renvoyées par l'API sont les
  contributions de cette pondération, pas le résultat d'une explication de modèle.
- **Les performances annoncées plus bas** (précision, rappel, délai de détection, ROI) sont des objectifs de
  conception : aucune évaluation ne les étaye dans ce dépôt.
- **Tableau de bord React** : `App.js` et `index.js` référencent `reseau-prediction.jsx` et un `package.json`
  qui **ne sont pas dans le dépôt**. Les commandes `npm install` / `npm start` de la section « Démo » ne peuvent
  donc pas fonctionner tant que ces fichiers ne sont pas ajoutés.
- **Ce qui fonctionne et est testé** : l'API FastAPI (31 tests), son image Docker et son déploiement
  (`DEPLOY.md`).

### Lancer l'API

```bash
pip install -r requirements-dev.txt
uvicorn api.main:app --reload --port 8000     # documentation interactive : http://localhost:8000/docs
python -m pytest
```

---

## 🎯 Objectif

Anticiper les coupures réseau dans les départements ministériels **1 heure avant** qu'elles surviennent, afin de déclencher des actions préventives et réduire les pertes opérationnelles estimées à **€233 000/an**.

---

## 🚀 Démo

```bash
npm install
npm start
# Ouvrir http://localhost:3000
```

---

## 📊 Fonctionnalités

| Onglet | Description |
|---|---|
| 🖥 Tableau de bord | Vue temps réel des 5 départements pilotes |
| 🔮 Prédiction H+1 | Jauge de risque, radar multidimensionnel, SHAP values |
| ⚠️ Alertes | Journal en temps réel — niveaux CRITIQUE / MODÉRÉ |
| 📋 Rapport Ministre | Document exécutif complet avec ROI et feuille de route |

---

## 🧠 Architecture du Modèle

```
Métriques réseau (toutes les 5 min)
    ├── Latence (ms)
    ├── Perte de paquets (%)
    ├── Bande passante (Mbps)
    ├── CPU Routeur (%)
    └── Température équipement (°C)
         ↓
  Feature Engineering (rolling mean, lag features)
         ↓
  LightGBM + LSTM Ensemble
         ↓
  Score de probabilité H+1
         ↓
  Alerte si seuil > 70%
```

---

## 📦 Stack Technique

- **Frontend** : React 18 + Recharts
- **Modèles** : LightGBM, LSTM, Isolation Forest
- **Déploiement** : FastAPI + Kafka + Grafana
- **Données** : ARCEP, ANSSI, open-data télécom

---

## 📈 Performances (données open source)

| Métrique | Valeur |
|---|---|
| Précision | 91.4% |
| Recall | 87.2% |
| F1-Score | 89.3% |
| Faux positifs | < 8% |
| Délai détection | 55 min avant coupure |
| ROI estimé | 3.2× |

---

## 📂 Structure du Projet

```
netsentinel-budget/
├── api/main.py              # API FastAPI (score, validation, accès)
├── data/arcep_sample.json   # 5 départements synthétiques
├── tests/test_api.py        # tests de l'API
├── App.js, index.js, index.html   # amorce du tableau de bord (sources incomplètes)
├── Dockerfile, cloudbuild.yaml    # image et pipeline Google Cloud
├── requirements.txt         # exécution · requirements-ml.txt : futur modèle
├── AUDIT.md, SECURITY.md, DEPLOY.md
└── README.md
```

---

## 🗺️ Feuille de Route

- [x] Prototype avec données open source
- [ ] Intégration données réelles Ministère
- [ ] Ré-entraînement modèle sur historique incidents
- [ ] Déploiement API FastAPI en production
- [ ] Dashboard Grafana pour équipes DSI

---

## 📬 Contact

Projet développé dans le cadre d'un appel d'offre — **Ministère du Budget, des Comptes Publics et de la Réforme de l'État**.

---

*Données du prototype issues de sources open source : ARCEP, ANSSI, open-data télécom. Les performances réelles seront supérieures avec les données opérationnelles du Ministère.*
