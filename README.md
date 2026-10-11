# fanga-ingest

Service d'ingestion multi-fournisseurs pour la plateforme FANGA OS. Il
décode les trames binaires des cabinets Voltix (TCP), consomme la télémétrie
des batteries Batrix (MQTT), consolide les deux dans un modèle canonique
unique selon une politique de vérité explicite, et expose l'état résultant
par une API HTTP ainsi que des événements métier signés vers NestJS.

## Prérequis

- Docker et Docker Compose (v2, intégré à Docker Desktop).
- Python 3.12 si vous voulez lancer les tests ou les scripts de démo hors
  conteneur (`make install` crée un environnement virtuel local dans `.venv`).
- Aucun autre logiciel : PostgreSQL et Mosquitto tournent dans des
  conteneurs, il n'y a rien à installer sur l'hôte pour la télémétrie MQTT
  (les scripts de démo utilisent un client Python, pas `mosquitto_pub`).

## Lancement

```bash
cp .env.example .env
docker compose up --build
```

`.env` fixe `REPLAY_START=2026-10-01T07:59:49Z` : l'horloge du service démarre
à cette date au lieu de la date réelle. C'est nécessaire pour que la démo
(ci-dessous) produise exactement l'état attendu — sans ça, l'horloge système
réelle entrerait en conflit avec les horodatages du jeu de données (qui date
du document) et la politique de vérité donnerait un résultat différent.

Au premier démarrage, le service :
1. attend que PostgreSQL soit prêt (healthcheck) ;
2. applique les migrations (service `migrate`, s'exécute une fois puis
   s'arrête — c'est normal de le voir `Exited (0)`) ;
3. démarre l'API HTTP (port 8000) et le serveur TCP Voltix (port 9000), et
   se connecte à Mosquitto (port 1883).

Vérifier que tout est prêt :

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Démo pas à pas

Une fois `docker compose up` lancé et `/health` vert, dans un second
terminal :

```bash
make demo
```

Ce que fait `make demo` (voir `scripts/run_demo.py`) :
1. enregistre l'inventaire connu (`BT001977`, `BT002290`, `BT003105`,
   `BT004817`, `BT000555`) via `POST /internal/inventory/batteries` — sans
   cette étape, ces batteries seraient elles aussi mises en quarantaine
   comme une batterie réellement inconnue, et le document produirait 7
   événements au lieu des 3 attendus ;
2. rejoue les trames Voltix du document sur le port 9000
   (`scripts/fake_cabinet.py`, mêmes découpages que dans l'énoncé) ;
3. publie les 6 messages Batrix sur Mosquitto (`scripts/publish_batrix.py`) ;
4. affiche l'état consolidé de `BT004817`.

Résultat attendu :

```
BT004817 :
  localisation : {'kind': 'out_of_cabinet', 'cabinet_id': 'VTX-CAB-0042', ...}
  SOC          : {'value': 91.8, 'source': 'batrix', 'observed_at': '2026-10-01T08:01:00Z'}
  statut       : {'value': 'discharging', ...}
```

C'est-à-dire : la batterie a été retirée du cabinet (source cabinet, trame
SWAP_EVENT), et son SOC vient du BMS (91,8 %), pas du cabinet (qui avait
annoncé 96 % avant le retrait) — exactement le résultat attendu par la note
d'architecture, section « Consolidation ».

Pour tout explorer à la main :

```bash
curl http://localhost:8000/batteries/BT004817 | python3 -m json.tool
curl http://localhost:8000/batteries/BT009999 | python3 -m json.tool   # batterie inconnue, en quarantaine
curl http://localhost:8000/cabinets/VTX-CAB-0042/slots | python3 -m json.tool
curl http://localhost:8000/metrics
```

Pour repartir d'un état propre : `make down` (équivalent à
`docker compose down -v`, supprime aussi les données PostgreSQL).

## Tests

```bash
make install        # une seule fois : crée .venv et installe les dépendances
make lint            # ruff (lint + format check)
make typecheck        # mypy (strict sur domain/ et application/) + import-linter
make test-unit        # rapide, sans réseau ni base
make test-integration # PostgreSQL et Mosquitto réels (démarrer un Postgres local au préalable, voir ci-dessous)
make test-e2e          # construit et démarre toute la pile docker compose, rejoue le document, démonte
make test              # lint + typecheck + test-unit + test-integration
```

`test-integration` a besoin d'une base PostgreSQL accessible via
`DATABASE_URL` (voir `.env.example`) et migrée (`make migrate`) ; le plus
simple est d'en démarrer une avec Docker :

```bash
docker run -d --name fanga-test-postgres -p 5433:5432 \
  -e POSTGRES_USER=fanga -e POSTGRES_PASSWORD=fanga -e POSTGRES_DB=fanga_ingest \
  postgres:16
export DATABASE_URL=postgresql+asyncpg://fanga:fanga@localhost:5433/fanga_ingest
make migrate
make test-integration
```

`test-e2e` gère lui-même tout le cycle de vie de `docker compose` (il
construit, démarre, attend `/health`, rejoue, vérifie, démonte) : pas besoin
de lancer la pile au préalable pour celui-ci, mais le port 5432/1883/8000/9000
doivent être libres.

## Structure du projet

```
src/fanga_ingest/
  domain/          Python pur : modèle canonique, agrégats, politique de vérité, événements
  application/     ports (Protocol), unité de travail, cas d'usage d'ingestion
  adapters/
    vendors/
      voltix/      protocole binaire, décodage, traduction, session TCP, serveur
      batrix/      schéma Pydantic, traduction, consommateur MQTT
    persistence/   schéma SQL, migrations Alembic, dépôts PostgreSQL, relais outbox
    api/           routes FastAPI, sérialisation, sécurité HMAC, métriques
  clock.py         horloge injectable (REPLAY_START pour la démo)
  config.py        configuration par variables d'environnement
  main.py          point d'assemblage : le seul fichier qui connaît tout
```

Règle de dépendance (vérifiée automatiquement en CI par `import-linter`) :
`domain/` ne dépend de rien d'autre dans le projet ; `application/` ne dépend
que de `domain/` ; `adapters/` peut dépendre des deux. `main.py` est le seul
fichier qui assemble tout.

### Ajouter un fournisseur en 4 étapes

Le cœur du système (domaine, cas d'usage, persistance, API) ne connaît que
trois types d'observation canoniques (`SlotObserved`, `SwapObserved`,
`TelemetryObserved`, dans `domain/observations.py`). Ajouter un fournisseur
fictif « Kinetix » qui parlerait, disons, HTTP+JSON, ne demande que :

1. Un nouveau dossier `adapters/vendors/kinetix/` avec son propre décodage
   (`schema.py` ou équivalent) et sa traduction (`translate.py`) vers les
   observations canoniques — c'est le seul endroit qui connaît le vocabulaire
   Kinetix.
2. Un adaptateur d'entrée (`consumer.py`, `server.py`, ou une route FastAPI
   selon le transport de Kinetix) qui appelle les cas d'usage d'ingestion
   déjà existants (`application/use_cases.py`) avec les observations
   traduites — ces cas d'usage ne changent pas d'une ligne.
3. Son câblage dans `main.py` (composition root).
4. Ses tests (`tests/unit/kinetix/`), sur le même modèle que `voltix/` et
   `batrix/`.

Zéro ligne modifiée dans `domain/`, `application/`, les dépôts PostgreSQL ou
les routes API : c'est la clé de voûte de l'architecture (voir
`docs/architecture.md`, section 1).

## Bonus — module NestJS (`nestjs-swap/`)

Livrable 4 (facultatif) : un module NestJS indépendant qui reçoit les
événements du relais outbox (`POST /webhooks/fanga`, signé HMAC) et
rattache un `battery.swapped` à la session rider ouverte sur le même
cabinet (brief, section 5.8). Projet séparé, son propre `package.json` et
son propre job CI :

```bash
cd nestjs-swap
npm install
npm test
```

## Branches et CI/CD

- `dev` : tout le développement, intégration continue.
- `preprod` : reçoit `dev` une fois la CI verte, promotion manuelle.
- `production` : reçoit `preprod` une fois sa pipeline verte, tag `vX.Y.Z`.

`.github/workflows/ci.yml` tourne sur `dev`/`preprod`/`production` (lint,
types, tests avec couverture, build Docker sans publication).
`.github/workflows/cd.yml` tourne sur push vers `preprod`/`production`
(E2E réel, publication de l'image sur GHCR, puis une étape de déploiement
**simulée** — ce projet n'est pas hébergé, voir la note dans le workflow).

## Hypothèses retenues

La documentation fournisseur comporte des manques (voir
`docs/livrable-3-voltix.md` pour le détail et le message envoyé à Voltix).
Hypothèses posées dans le code :

- Température des batteries lue comme un octet **signé**.
- Un numéro de série est considéré vide si tous ses octets valent `0x00` ou
  l'ASCII `'0'`.
- L'horloge du cabinet est en secondes Unix UTC, mais peut dériver : on ne
  lui fait confiance que si elle reste à moins de 5 minutes de l'heure
  serveur (sinon on retient l'heure serveur et on logue la dérive).
- `SLOT_STATUS` ne porte pas d'horodatage propre : on date à réception.
- Un cabinet renvoie une trame sans ACK et stocke ses événements pendant une
  coupure 4G (d'où la déduplication par `dedup_key` et l'indépendance du
  résultat final à l'ordre d'arrivée).
- HEARTBEAT toutes les 60 secondes ; casiers numérotés de 1 à 8.
- Un swap partiel se traduit par un casier à `00` et une série vide.
- L'identifiant du cabinet dans LOGIN est complété par des espaces ou des
  octets `0x00`.
- Une commande inconnue entraîne un ACK d'erreur, sans fermer la connexion.
- Batrix peut republier un message déjà vu après une coupure (déduplication
  par `dedup_key` sur source + série + `observed_at`) ; le nombre de sondes
  de température peut varier d'une batterie à l'autre.

## Limites connues et ce qui manque

- **Réconciliation d'inventaire** : seul l'enregistrement/retrait ponctuel
  (`POST /internal/inventory/batteries`) est implémenté. La réconciliation
  nocturne complète depuis l'API métier est documentée (`docs/architecture.md`)
  mais pas codée.
- **Identifiant de session rider dans la trame Voltix** : le rattachement
  swap ↔ rider se fait par corrélation temporelle côté NestJS (fenêtre de
  session), faute de mieux — voir `docs/livrable-3-voltix.md`, question
  posée à Voltix à ce sujet.
- **TLS côté Voltix** : le port TCP est exposé sans chiffrement en démo (le
  protocole ne le prévoit pas). Recommandation de durcissement dans
  `docs/architecture.md`.
- **Alerting actif** (PagerDuty, Slack...) sur `cabinet.offline` : seul
  l'événement est émis, rien ne le relaie vers un canal de notification pour
  l'instant.
- **Tableau de bord** : les métriques Prometheus existent (`/metrics`), mais
  aucun Grafana n'est fourni dans ce dépôt.

## Outils utilisés

- **Claude** (claude.ai) : recherches ponctuelles (notamment la vérification
  des informations OCPP 2.1 auprès des sources officielles de l'Open
  Charge Alliance pour `docs/architecture.md`) et travail sur la
  spécification du projet.
- **Claude Code** : implémentation — code, tests, infrastructure Docker,
  CI/CD.
