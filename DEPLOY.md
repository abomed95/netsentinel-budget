# DEPLOY — NetSentinel sur Google Cloud

Rien de ce document n'a été exécuté : aucune ressource n'a été créée ni facturée. Les commandes sont à lancer
par toi.

**Testé en local** : build de l'image, exécution en utilisateur non privilégié, refus de démarrer sans clé d'API,
`/health`, `/predict` avec et sans clé, `/departments`.

## 1. Ce qui est déployé — et ce qui ne l'est pas

| Composant | État |
|---|---|
| **API FastAPI** | Déployable sur **Cloud Run** (ce document) |
| **Tableau de bord React** | **Non déployable** : `reseau-prediction.jsx` et `package.json` manquent dans le dépôt. Quand ils y seront, le plus simple est un second service Cloud Run (nginx servant le build) ou Firebase Hosting, avec `NETSENTINEL_CORS_ORIGINS` réglé sur son adresse. |

**Base de données et stockage : aucun.** L'API est sans état ; le référentiel des départements est un fichier
JSON embarqué dans l'image. Si un historique des prédictions ou des métriques devient nécessaire, la suite
logique est BigQuery (séries temporelles, analyses) plutôt qu'une base relationnelle.

## 2. Variables à renseigner

```bash
export PROJECT_ID="ton-projet-gcp"
export REGION="europe-west1"
export SERVICE="netsentinel-api"
export SA="netsentinel-run"
export REPO="netsentinel"
```

Un seul secret : `netsentinel-api-key`, la clé exigée dans l'en-tête `X-API-Key`.

## 3. Mise en place (une seule fois)

```bash
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
gcloud iam service-accounts create "$SA" --display-name="NetSentinel — Cloud Run"

# Clé d'API générée et stockée sans jamais s'afficher
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" \
  | gcloud secrets create netsentinel-api-key --replication-policy=automatic --data-file=-

# Privilège minimal : le service ne lit que ce secret
gcloud secrets add-iam-policy-binding netsentinel-api-key \
  --member="serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$CB" --role=roles/run.admin
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$CB" --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding "$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --member="$CB" --role=roles/iam.serviceAccountUser
```

> Vérifie dans **Cloud Build → Paramètres** quel compte de service est utilisé et adapte `CB`.

## 4. Premier déploiement

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/api:initial"
gcloud builds submit --tag "$IMAGE"

gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --allow-unauthenticated --port=8080 --cpu=1 --memory=256Mi \
  --min-instances=0 --max-instances=2 --concurrency=80 --timeout=30 \
  --set-env-vars="NETSENTINEL_ENV=production,NETSENTINEL_RATE_LIMIT=120,NETSENTINEL_TRUSTED_PROXY_HOPS=1" \
  --set-secrets="NETSENTINEL_API_KEY=netsentinel-api-key:latest"

gcloud run services update "$SERVICE" --region="$REGION" \
  --startup-probe=httpGet.path=/health,periodSeconds=2,failureThreshold=10 \
  --liveness-probe=httpGet.path=/health,periodSeconds=30

URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
curl "$URL/health"

# Appel authentifié
KEY=$(gcloud secrets versions access latest --secret=netsentinel-api-key)
curl -X POST "$URL/predict" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"department_id":"A","latency_ms":95,"packet_loss_pct":4.2,"bandwidth_mbps":45,"cpu_pct":78,"temperature_celsius":68}'
```

`--allow-unauthenticated` laisse Cloud Run accepter les requêtes ; c'est l'en-tête `X-API-Key` qui protège les
routes de prédiction. Pour un usage strictement interne à un ministère, préfère retirer ce drapeau et
n'autoriser que des comptes de service nommés (`roles/run.invoker`) : l'authentification est alors assurée par
Google, en plus de la clé.

## 5. Déploiements suivants

```bash
gcloud builds submit --config cloudbuild.yaml
```

Tests → image → Artifact Registry → révision sans trafic → `/health` → bascule.

## 6. Retour arrière

```bash
gcloud run revisions list --service="$SERVICE" --region="$REGION"
gcloud run services update-traffic "$SERVICE" --region="$REGION" --to-revisions=NOM-DE-LA-REVISION=100
```

Aucune donnée persistante : le retour arrière est complet et immédiat.

Renouveler la clé d'API (fuite, départ d'un prestataire) :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" \
  | gcloud secrets versions add netsentinel-api-key --data-file=-
gcloud run services update "$SERVICE" --region="$REGION" \
  --update-secrets="NETSENTINEL_API_KEY=netsentinel-api-key:latest"
```

## 7. Estimation de coût mensuel

Ordres de grandeur, à **vérifier avec le simulateur Google Cloud** : je n'ai pas interrogé la grille tarifaire en vigueur.

| Poste | Hypothèse | Estimation |
|---|---|---|
| Cloud Run | 5 départements, une mesure toutes les 5 minutes ≈ 45 000 requêtes/mois de quelques millisecondes | 0 $ (dans le volume gratuit) |
| Artifact Registry | image de 210 Mo | < 0,10 $ |
| Secret Manager, Cloud Build, Logging | usage courant | < 1 $ |
| **Total** | | **≈ 0 à 1 $** |

## 8. Points d'attention

- **Hébergement de données d'un ministère.** `europe-west1` est en Belgique. Vérifie les exigences de
  localisation et de souveraineté du client avant tout déploiement réel : c'est une question contractuelle, pas
  technique.
- **Limitation de débit en mémoire**, donc par instance : avec `--max-instances=2`, la limite réelle est doublée.
- **Le score n'est pas un modèle entraîné** (voir `README.md`, « État réel du prototype »).
