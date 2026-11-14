# DEPLOY — NetSentinel sur Google Cloud

Rien n'a été exécuté sur Google Cloud : aucune ressource n'a été créée ni facturée. Les scripts de
`deploy/gcp/` sont à lancer par toi.

**Testé en local** : build de l'image, exécution en utilisateur non privilégié, refus de démarrer sans clé d'API,
`/health`, `/predict` avec et sans clé, `/departments`. Scripts : dry run relu, et mode `--apply` exécuté contre une
doublure de `gcloud`, la vérification finale interrogeant la vraie API lancée en local (200 avec la clé, 401 sans ;
la clé n'apparaît dans aucun argument de commande).

## 1. Ce qui est déployé — et ce qui ne l'est pas

| Composant | État |
|---|---|
| **API FastAPI** | Déployable sur **Cloud Run** (ce document) |
| **Tableau de bord React** | Compilé dans la même image et servi par l'API sous **`/dashboard/`**. Il calcule ses scores dans le navigateur à partir de mesures simulées : il n'appelle pas l'API et n'a pas besoin de la clé. |

**Base de données et stockage : aucun.** L'API est sans état ; le référentiel des départements est un fichier
JSON embarqué dans l'image. Si un historique des prédictions ou des métriques devient nécessaire, la suite
logique est BigQuery (séries temporelles, analyses) plutôt qu'une base relationnelle.

## 2. Les scripts (`deploy/gcp/`)

Toute la procédure est scriptée. Chaque script **affiche** ce qu'il ferait (dry run) ; il n'agit qu'avec `--apply`.
Lance-les depuis **Cloud Shell** (console Google Cloud, bouton `>_`) : `gcloud` y est déjà installé et connecté.

| Script | Rôle | Quand |
|---|---|---|
| `setup.sh` | API, dépôt d'images, compte de service, clé d'API générée, droits minimaux (application et Cloud Build) | une fois ; relançable sans risque |
| `first-deploy.sh` | construit l'image, crée le service, vérifie `/health` et `/predict` (200 avec la clé, 401 sans) | une fois |
| `rotate-key.sh` | nouvelle clé d'API, nouvelle révision, anciennes versions désactivées | en cas de fuite ou de départ d'un prestataire |
| `rollback.sh` | liste les révisions, ou renvoie le trafic vers l'une d'elles | en cas de problème |

```bash
git clone <ce dépôt> && cd netsentinel-budget
cp deploy/gcp/config.env.example deploy/gcp/config.env    # renseigner PROJECT_ID (aucun secret dans ce fichier)
./deploy/gcp/setup.sh                 # relire les commandes affichées
./deploy/gcp/setup.sh --apply
./deploy/gcp/first-deploy.sh --apply
```

Paramètres (`config.env`) : projet, région, noms des ressources, `PUBLIC_ACCESS`, nombre d'instances, limite de
débit. Un seul secret, `netsentinel-api-key`, généré par `setup.sh` et jamais affiché ; pour le lire :
`gcloud secrets versions access latest --secret=netsentinel-api-key`.

**Accès.** Avec `PUBLIC_ACCESS="true"`, Cloud Run accepte toutes les requêtes et c'est l'en-tête `X-API-Key` qui
protège les routes de prédiction. Pour un usage strictement interne à un ministère, mets `"false"` : seuls les
comptes autorisés pourront appeler le service, en plus de la clé.

```bash
gcloud run services add-iam-policy-binding netsentinel-api --region=europe-west1 \
  --member="serviceAccount:client@projet-du-client.iam.gserviceaccount.com" --role=roles/run.invoker
```

**Compte Cloud Build.** `setup.sh` demande à Google lequel est utilisé (compte Compute par défaut ou ancien compte
Cloud Build, selon l'âge du projet) et lui donne `run.developer` plutôt que `run.admin` : il peut déployer, pas
modifier qui a le droit d'appeler le service.

## 3. Déploiements suivants

```bash
gcloud builds submit --config cloudbuild.yaml
```

Tests → image → Artifact Registry → révision sans trafic → `/health` → bascule. Si tu as changé un nom dans
`config.env`, `first-deploy.sh` affiche la commande avec les `--substitutions` correspondantes.

## 4. Retour arrière

```bash
./deploy/gcp/rollback.sh                                   # liste les révisions
./deploy/gcp/rollback.sh netsentinel-api-00012-abc --apply # 100 % du trafic sur cette révision
```

Aucune donnée persistante : le retour arrière est complet et immédiat.

## 5. Estimation de coût mensuel

Ordres de grandeur, à **vérifier avec le simulateur Google Cloud** : je n'ai pas interrogé la grille tarifaire en vigueur.

| Poste | Hypothèse | Estimation |
|---|---|---|
| Cloud Run | 5 départements, une mesure toutes les 5 minutes ≈ 45 000 requêtes/mois de quelques millisecondes | 0 $ (dans le volume gratuit) |
| Artifact Registry | image de 210 Mo | < 0,10 $ |
| Secret Manager, Cloud Build, Logging | usage courant | < 1 $ |
| **Total** | | **≈ 0 à 1 $** |

## 6. Points d'attention

- **Hébergement de données d'un ministère.** `europe-west1` est en Belgique. Vérifie les exigences de
  localisation et de souveraineté du client avant tout déploiement réel : c'est une question contractuelle, pas
  technique.
- **Limitation de débit en mémoire**, donc par instance : avec `--max-instances=2`, la limite réelle est doublée.
- **Le score n'est pas un modèle entraîné** (voir `README.md`, « État réel du prototype »).
