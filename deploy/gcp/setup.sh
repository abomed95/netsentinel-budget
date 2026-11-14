#!/usr/bin/env bash
# Mise en place UNIQUE de l'infrastructure Google Cloud de NetSentinel.
#
#   ./deploy/gcp/setup.sh            # dry run : affiche les commandes, ne crée rien
#   ./deploy/gcp/setup.sh --apply    # exécute (crée des ressources)
#
# Idempotent : relancé, il saute ce qui existe déjà. Crée les API, le dépôt
# d'images, le compte de service, la clé d'API (générée, jamais affichée) et les
# droits minimaux. Aucune base de données : l'API est sans état.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh" "$@"
banner

step "1. API nécessaires"
run gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com --project="$PROJECT_ID"

step "2. Dépôt d'images Artifact Registry"
if exists gcloud artifacts repositories describe "$REPOSITORY" --location="$REGION" --project="$PROJECT_ID"; then
  note "déjà présent"
else
  run gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker \
    --location="$REGION" --project="$PROJECT_ID" --description="Images NetSentinel"
fi

step "3. Compte de service de l'application (aucun rôle de projet)"
if exists gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID"; then
  note "déjà présent"
else
  run gcloud iam service-accounts create "$SERVICE_ACCOUNT" --display-name="NetSentinel - Cloud Run" --project="$PROJECT_ID"
fi

step "4. Clé d'API (en-tête X-API-Key)"
if secret_exists netsentinel-api-key; then
  note "netsentinel-api-key déjà présente (renouvellement : ./deploy/gcp/rotate-key.sh)"
else
  note "générée aléatoirement ; pour la lire plus tard : gcloud secrets versions access latest --secret=netsentinel-api-key"
  python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | put_secret netsentinel-api-key
fi

step "5. Droits minimaux"
note "L'application ne lit QUE sa clé d'API."
run gcloud secrets add-iam-policy-binding netsentinel-api-key --project="$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" --role=roles/secretmanager.secretAccessor --condition=None --quiet
grant_cloud_build "$(build_service_account)" "$SA_EMAIL"

step "Terminé"
note "Étape suivante : ./deploy/gcp/first-deploy.sh"
