# AUDIT — NetSentinel (netsentinel-budget)

Phase 1, lecture seule. Branche `refonte-gcp`. Aucun fichier existant n'a été modifié.

## 1. Stack et architecture

| Élément | État constaté |
|---|---|
| Backend | FastAPI 0.111 + Pydantic 2, un seul fichier `main.py` (126 lignes) |
| Frontend | React 18 annoncé (`index.js`, `App.js`, `index.html`) — **non constructible en l'état** |
| Modèle « IA » | Aucun modèle : score = combinaison linéaire à poids fixes (`main.py:46-65`) |
| Données | `arcep_sample.json` (5 départements synthétiques) |
| CI | `ci.yml.txt` — fichier texte, **jamais exécuté** par GitHub Actions |
| Tests | Aucun |
| Dépôt | 11 fichiers à plat, 4 commits « Add files via upload » |

Le dépôt est une maquette déposée par l'interface web de GitHub : l'arborescence décrite dans le README
(`src/`, `api/`, `data/`, `package.json`) n'existe pas.

## 2. Points d'entrée

- `GET /`, `GET /health`, `POST /predict`, `POST /predict/batch`, `GET /departments` (`main.py:75-123`)
- `index.js` → `App.js` → `./reseau-prediction` (fichier absent)

## 3. Dépendances

`requirements.txt` épingle des versions de mi-2024. `pip-audit` n'a pas abouti dans le temps imparti
(compilation de lightgbm) : **résultat non concluant, à refaire en phase 4**. À vue, `fastapi 0.111.0`
embarque une version de Starlette antérieure aux correctifs de déni de service sur le multipart ; à confirmer.

Dépendances déclarées mais jamais importées : `lightgbm`, `scikit-learn`, `pandas`, `kafka-python`,
`python-dotenv`, `httpx`. `numpy` est importé mais inutilisé (`main.py:10`). Elles alourdiraient l'image
Docker d'environ 400 Mo pour rien.

## 4. Problèmes

### Critique

| # | Fichier:ligne | Problème |
|---|---|---|
| C1 | `App.js:1` | Importe `./reseau-prediction`, **absent du dépôt**. Le tableau de bord — la seule interface — n'existe pas. |
| C2 | (racine) | Pas de `package.json` : `npm install` / `npm start` du README échouent. Le frontend ne peut pas être construit. |
| C3 | `main.py:121` | `open("data/arcep_sample.json")` alors que le fichier est à la racine → `GET /departments` renvoie une erreur 500 à chaque appel. |
| C4 | `README.md:7,68-77` | Annonce « LightGBM + LSTM », précision 91,4 %, SHAP. Aucun modèle n'est entraîné ni chargé ; les « SHAP values » (`main.py:96-102`) sont les poids fixes recopiés. Présenté à un ministère dans un appel d'offres, c'est un risque contractuel et de crédibilité, pas seulement technique. |

### Important

| # | Fichier:ligne | Problème |
|---|---|---|
| I1 | `main.py:20-25` | CORS `allow_origins=["*"]` sur toutes les méthodes. |
| I2 | `main.py:88,113` | Aucune authentification ni limitation de débit ; `/predict/batch` accepte une liste de taille illimitée. |
| I3 | `main.py:28-35` | Aucune borne sur les métriques : latence négative, CPU à 500 %, `NaN`/`inf` sont acceptés et produisent un score faux sans erreur. |
| I4 | `main.py:123` | `"count": 5` codé en dur au lieu de `len(...)`. |
| I5 | `ci.yml.txt` | CI inactive (mauvais emplacement et extension) ; elle masque en plus l'absence de tests par `|| echo`. |
| I6 | `Src` | Fichier vide nommé `Src` : empêche de créer le dossier `src/` sur un système insensible à la casse. |
| I7 | — | Aucun test, aucun Dockerfile, aucune configuration par variable d'environnement. |

### Mineur

| # | Fichier:ligne | Problème |
|---|---|---|
| M1 | `main.py:86,110` | `datetime.utcnow()` déprécié (horodatage sans fuseau). |
| M2 | `main.py:93-102` | Calcul des contributions dupliqué entre `compute_risk_score` et `predict`. |
| M3 | `main.py:42` | `shap_values: dict` non typé. |
| M4 | `index.html:9-10` | Polices chargées depuis Google Fonts : dépendance externe et fuite d'adresse IP, sensible pour un outil ministériel. |
| M5 | `.gitignore` | Modèle Python seul ; rien pour `node_modules/`, `build/`. |
| M6 | `README.md:13` | Montants en euros et références ARCEP/ANSSI (France) : à aligner sur le contexte réel du client. |

## 5. Secrets

Recherche par motifs dans le code et dans tout l'historique git (`git log --all -p`) : **rien trouvé**.
Limite : recherche par expressions régulières, pas un outil spécialisé (gitleaks).

## 6. Plan priorisé proposé

Ce dépôt demande une **décision de ta part avant la phase 2** (voir « Doutes »).

1. Restructurer : `api/main.py`, `data/`, `web/`, activer la CI dans `.github/workflows/`.
2. Corriger l'API : chemin du fichier de données, bornes Pydantic, taille maximale du lot, calcul factorisé,
   CORS par variable d'environnement, logs JSON.
3. Tests `pytest` sur le score, les seuils de risque et chaque route.
4. Frontend : soit tu me fournis `reseau-prediction.jsx`, soit je reconstruis un tableau de bord (Vite + React)
   à partir des quatre onglets décrits dans le README.
5. Rendre le README honnête : « score heuristique » tant qu'aucun modèle n'est entraîné.
6. Supprimer les dépendances inutilisées.

## 7. Doutes

- **Le fichier `reseau-prediction.jsx` existe-t-il chez toi ?** Sans lui, il n'y a pas d'interface à
  « refaire » en phase 3 : il faut la créer, ce qui dépasse « garder les parcours existants ».
- Supprimer le fichier vide `Src` et les dépendances inutilisées : je considère que ce n'est pas « supprimer
  une fonctionnalité », mais je préfère ton accord explicite.
- Veux-tu un vrai modèle (LightGBM entraîné sur données synthétiques) ou garder l'heuristique en
  l'étiquetant correctement ?
