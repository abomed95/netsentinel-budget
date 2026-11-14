#!/usr/bin/env bash
# PREMIER déploiement de NetSentinel sur Cloud Run (les suivants passent par cloudbuild.yaml).
#
#   ./deploy/gcp/first-deploy.sh            # dry run
#   ./deploy/gcp/first-deploy.sh --apply    # construit l'image et crée le service
#
# Prérequis : setup.sh --apply terminé. Relancé, il redéploie la même étiquette
# d'image « initial » : sans danger, mais préfère cloudbuild.yaml ensuite.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh" "$@"
banner
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/api:initial"

step "1. Construction de l'image sur Cloud Build (3 à 5 minutes)"
note "Tableau de bord React compilé puis API Python, dans une seule image (environ 210 Mo)."
run gcloud builds submit "$REPO_ROOT" --project="$PROJECT_ID" --tag="$IMAGE" --timeout=900s

step "2. Création du service Cloud Run"
if [[ "$PUBLIC_ACCESS" == "true" ]]; then
  ACCESS="--allow-unauthenticated"
  note "Accès public : la clé X-API-Key protège /predict et /departments."
else
  ACCESS="--no-allow-unauthenticated"
  note "Accès réservé : accorde roles/run.invoker aux comptes autorisés (voir DEPLOY.md)."
fi
run gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$SA_EMAIL" \
  "$ACCESS" \
  --port=8080 --cpu=1 --memory=256Mi \
  --min-instances="$MIN_INSTANCES" --max-instances="$MAX_INSTANCES" \
  --concurrency=80 --timeout=30 \
  --set-env-vars="NETSENTINEL_ENV=production,NETSENTINEL_RATE_LIMIT=$RATE_LIMIT,NETSENTINEL_TRUSTED_PROXY_HOPS=1" \
  --set-secrets="NETSENTINEL_API_KEY=netsentinel-api-key:latest" \
  --startup-probe="httpGet.path=/health,initialDelaySeconds=0,periodSeconds=2,timeoutSeconds=2,failureThreshold=10" \
  --liveness-probe="httpGet.path=/health,periodSeconds=30,timeoutSeconds=5,failureThreshold=3"

step "3. Vérification"
if (( APPLY )); then
  URL="$(service_url)"
  note "URL : $URL"
  if [[ "$PUBLIC_ACCESS" != "true" ]]; then
    note "Service privé : vérifie avec  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" $URL/health"
  else
    curl --fail --silent --show-error --max-time 30 "$URL/health"; echo
    # Appel authentifié : la clé passe par un tube vers curl (--config -), jamais en argument.
    code="$({ printf 'header = "X-API-Key: '; secret_value netsentinel-api-key; printf '"\n'; } \
      | curl --config - --silent --output /dev/null --write-out '%{http_code}' --max-time 30 \
          -X POST "$URL/predict" -H 'Content-Type: application/json' \
          -d '{"department_id":"A","latency_ms":95,"packet_loss_pct":4.2,"bandwidth_mbps":45,"cpu_pct":78,"temperature_celsius":68}')"
    [[ "$code" == "200" ]] || { echo "   ATTENTION : /predict avec la clé a répondu $code (200 attendu)" >&2; exit 1; }
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 30 -X POST "$URL/predict" \
      -H 'Content-Type: application/json' -d '{}')"
    [[ "$code" == "401" ]] || { echo "   ATTENTION : /predict SANS clé a répondu $code (401 attendu)" >&2; exit 1; }
    note "/predict : 200 avec la clé, 401 sans. Tableau de bord : $URL/dashboard/"
  fi
else
  note "+ curl <URL>/health ; POST <URL>/predict avec la clé (200 attendu) puis sans (401 attendu)"
fi

step "Ensuite"
note "Déploiements suivants : gcloud builds submit --config cloudbuild.yaml --project=$PROJECT_ID \\"
note "  --substitutions=_REGION=$REGION,_REPOSITORY=$REPOSITORY,_SERVICE=$SERVICE,_SERVICE_ACCOUNT=$SERVICE_ACCOUNT"
note "Retour arrière : ./deploy/gcp/rollback.sh   ·   Nouvelle clé : ./deploy/gcp/rotate-key.sh"
