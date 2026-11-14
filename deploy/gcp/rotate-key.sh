#!/usr/bin/env bash
# Renouvelle la clé d'API (fuite, départ d'un prestataire) et la fait prendre en compte.
#
#   ./deploy/gcp/rotate-key.sh            # dry run
#   ./deploy/gcp/rotate-key.sh --apply
#
# L'ancienne clé cesse de fonctionner dès que la nouvelle révision sert le trafic
# (quelques secondes) : préviens d'abord les clients de l'API. Les anciennes
# versions du secret sont désactivées : réactivables en cas d'erreur, mais encore
# facturées (0,06 $/mois chacune au-delà de 6) tant qu'elles ne sont pas détruites
# (gcloud secrets versions destroy N --secret=netsentinel-api-key).

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh" "$@"
banner

step "1. Nouvelle version du secret"
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | put_secret netsentinel-api-key

step "2. Nouvelle révision qui lit la nouvelle clé"
# « latest » n'est résolu qu'à la création d'une révision ; la configuration du
# secret ne change pas, donc on change une variable pour forcer cette création.
run gcloud run services update "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --update-secrets="NETSENTINEL_API_KEY=netsentinel-api-key:latest" \
  --update-env-vars="NETSENTINEL_KEY_ROTATED_AT=$(date -u +%Y%m%dT%H%M%SZ)"

step "3. Désactivation des anciennes versions"
if (( APPLY )); then
  latest="$(gcloud secrets versions list netsentinel-api-key --project="$PROJECT_ID" \
    --filter='state=ENABLED' --sort-by='~createTime' --format='value(name.basename())' | head -1)"
  gcloud secrets versions list netsentinel-api-key --project="$PROJECT_ID" --filter='state=ENABLED' \
    --format='value(name.basename())' | while read -r version; do
      [[ "$version" == "$latest" ]] && continue
      gcloud secrets versions disable "$version" --secret=netsentinel-api-key --project="$PROJECT_ID" --quiet
    done
  note "Nouvelle clé : gcloud secrets versions access latest --secret=netsentinel-api-key"
else
  note "+ gcloud secrets versions disable <anciennes versions> --secret=netsentinel-api-key"
fi
