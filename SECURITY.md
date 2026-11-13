# SECURITY — NetSentinel

État après la phase 4. Le périmètre est réduit : une API sans état, sans base de données, sans compte
utilisateur et sans téléversement de fichier.

## Signaler une faille

Écris au mainteneur du dépôt en privé (pas d'issue publique), avec les étapes de reproduction.

## Corrigé

| Sujet | Avant | Après |
|---|---|---|
| Accès | Aucune authentification | Clé d'API (`X-API-Key`) sur `/predict`, `/predict/batch`, `/departments`, comparée à durée constante ; **obligatoire en production** (l'image refuse de démarrer sans elle) |
| CORS | Toutes les origines, toutes les méthodes | Aucune origine par défaut ; liste explicite par `NETSENTINEL_CORS_ORIGINS` |
| Limitation de débit | Aucune | 120 requêtes par minute et par adresse, IP lue du côté fiable de `X-Forwarded-For` |
| Taille du lot | Illimitée | 1 à 100 éléments |
| Validation | Aucune borne : latence négative, CPU à 500 %, `NaN` acceptés et score faux | Bornes physiques sur chaque métrique, valeurs non finies et champs inconnus refusés, identifiant de département restreint |
| Plantage sur `NaN` | La réponse d'erreur recopiait la valeur et n'était plus du JSON valide (erreur 500) | Les erreurs de validation ne recopient plus l'entrée |
| `/departments` | Erreur 500 à chaque appel (mauvais chemin de fichier) | Corrigé ; une panne du référentiel renvoie un 503 sans chemin de fichier |
| En-têtes | Aucun | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS, `Cache-Control: no-store` |
| Dépendances | Versions de mi-2024, dont six paquets jamais importés | Trois paquets, versions figées, `pip-audit` : aucun avis connu |
| Journaux | Aucun | Une ligne JSON par événement ; les risques critiques sont journalisés |
| Conteneur | Aucun | Image multi-étapes, utilisateur non privilégié |

Sans objet ici : injection SQL (pas de base), XSS côté API (réponses JSON uniquement), CSRF (pas de cookie),
téléversement de fichiers, modèle de langage (le projet n'en appelle aucun).

## Risques résiduels

- **Une seule clé partagée.** Tous les appelants utilisent la même clé : pas de traçabilité par client, et la
  renouveler coupe tout le monde en même temps. Pour un usage ministériel, préfère l'authentification IAM de
  Cloud Run (un compte de service par appelant) — voir `DEPLOY.md`.
- **Limitation de débit en mémoire**, par instance et remise à zéro à chaque redémarrage.
- **`/`, `/health` et `/docs`** restent accessibles sans clé. La documentation interactive révèle le schéma de
  l'API ; désactive-la au besoin (`FastAPI(docs_url=None, redoc_url=None)`).
- **Polices Google** dans `index.html` : le navigateur de chaque utilisateur contacte Google. À héberger
  localement pour un outil d'administration publique.
- **Tableau de bord** : non audité, ses sources n'étant pas dans le dépôt.
- **Fiabilité du score.** Ce n'est pas une faille au sens strict, mais c'est le principal risque du projet : le
  score est une heuristique, pas un modèle évalué. Des décisions d'intervention ne devraient pas reposer dessus
  sans validation sur des données réelles.

## Secrets

Recherche par motifs dans le code et tout l'historique git : aucun secret trouvé. Limite : ce n'est pas un
outil spécialisé ; active le *secret scanning* de GitHub.

## Non vérifié

Aucun test d'intrusion. Aucune ressource Google Cloud n'a été créée.
