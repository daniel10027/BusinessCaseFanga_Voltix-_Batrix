# Livrable 3 — Manques de la documentation et message au fournisseur Voltix

## Manques et hypothèses retenues dans le code

| # | Manque dans la documentation | Hypothèse retenue dans le code |
|---|---|---|
| 1 | Comportement en cas d'absence d'ACK (délai, nombre d'essais) | Non géré côté serveur : on suppose que le cabinet réémet la trame après un délai interne ; le serveur ne fait que répondre à ce qui arrive. |
| 2 | Stockage des trames pendant une coupure 4G | On suppose que le cabinet mémorise ses trames localement et les rejoue à la reconnexion, dans l'ordre. D'où la déduplication par `dedup_key` et une politique de vérité indépendante de l'ordre d'arrivée (section 5.3). |
| 3 | Absence de numéro de séquence dans les trames | Aucun numéro de séquence n'est utilisé ; la déduplication se fait uniquement par contenu (source + identifiants + horodatage). |
| 4 | Intervalle HEARTBEAT | Supposé fixe à 60 secondes. |
| 5 | Horloge du cabinet, synchronisation NTP | Supposée en secondes Unix UTC, mais non fiable : tolérance de 5 minutes par rapport à l'heure serveur pour l'horodatage du SWAP_EVENT, au-delà on retient l'heure serveur (section 5.3). |
| 6 | Signe de l'octet de température | Lu comme un octet **signé** (complément à deux), pour couvrir les températures négatives. |
| 7 | Convention de numéro de série vide | Considéré vide si tous les octets valent `0x00` **ou** si tous valent l'ASCII `'0'` (0x30). |
| 8 | Numérotation des casiers | Supposée de 1 à 8 (pas de casier 0, sauf valeur spéciale pour un swap partiel). |
| 9 | Encodage d'un swap partiel (dépôt seul ou retrait seul) | Casier à `00` et numéro de série vide côté manquant. |
| 10 | Fréquence et déclenchement de SLOT_STATUS | Non documenté : traité à la fois comme périodique et sur changement d'état ; daté à réception (pas d'horodatage propre à la trame). |
| 11 | Commande inconnue | ACK d'erreur (`01`), sans fermeture de connexion (hypothèse distincte d'un CRC invalide, qui ferme après répétition). |
| 12 | Identifiant LOGIN plus court que 12 octets | Complété par des espaces ou des octets `0x00` ; les deux sont acceptés en fin de chaîne. |
| 13 | Identifiant de session rider dans SWAP_EVENT | Absent du protocole. Rattachement swap ↔ rider fait par corrélation temporelle côté NestJS (fenêtre de session), voir `docs/architecture.md` section 4. |
| 14 | Commande serveur → cabinet (hors ACK) | Aucune n'est documentée ; on suppose qu'il n'en existe pas pour l'instant (pas de verrouillage à distance d'un casier, pas d'ouverture pilotée). |
| 15 | Sécurité du transport (TLS, authentification réseau) | Aucune : liste blanche par identifiant LOGIN uniquement, connexion en clair. |
| 16 | (Batrix) Republication de messages anciens après une coupure | Supposée possible ; gérée par la politique de vérité (clé d'ordre total) plutôt que par rejet des messages tardifs. |
| 17 | (Batrix) Nombre de sondes de température par batterie | Supposé variable d'une batterie à l'autre (la liste `t` peut avoir une longueur différente). |

## Message à l'ingénieur Voltix (anglais)

**Objet : VTX-CAB protocol — a few confirmations ahead of the Cotonou rollout**

Hi,

We're integrating the VTX-CAB cabinet protocol into our platform ahead of
the Cotonou deployment, six weeks from now. Your documentation is clear on
the frame format itself, but leaves a number of operational behaviours
unspecified. Below are the assumptions we've made — could you confirm or
correct each one?

1. **Retransmission without ACK.** We assume the cabinet retries sending a
   frame if it doesn't receive an ACK within some timeout. What is that
   timeout, and how many retries before the cabinet gives up or raises an
   error?
2. **Buffering during a connectivity loss.** We assume the cabinet buffers
   SLOT_STATUS and SWAP_EVENT frames locally during a 4G outage and replays
   them in order once reconnected. Could you confirm, and tell us the
   buffer's capacity and what happens if it overflows?
3. **Sequence numbers.** We don't see one in any frame. Is there really
   none? Without it, we can only deduplicate by content and a server-side
   receipt timestamp, which is weaker against reordering.
4. **HEARTBEAT interval.** We assume 60 seconds, fixed. Is it configurable?
5. **Cabinet clock and NTP.** Is the cabinet clock synchronised via NTP? We
   only trust a SWAP_EVENT timestamp within 5 minutes of our server time —
   is that margin realistic for cabinets in the field?
6. **Signed temperature.** We decode the SLOT_STATUS temperature byte as
   signed (two's complement), to support sub-zero readings. Please confirm.
7. **Empty battery serial.** We treat a serial as "no battery" when all 8
   bytes are `0x00` or all are ASCII `'0'`. Is one of these the actual
   convention, or could either appear depending on firmware version?
8. **Slot numbering.** We assume slots are numbered 1–8. Please confirm,
   and let us know if numbering could have gaps on an 8-slot cabinet.
9. **Partial swap.** For a deposit-only or withdrawal-only event, we assume
   the missing side of SWAP_EVENT is encoded as slot `0x00` with an empty
   serial. Correct?
10. **SLOT_STATUS frequency and timing.** The frame carries no timestamp.
    Is it sent periodically, only on state change, or both? What's the
    typical interval?
11. **Rider session correlation.** SWAP_EVENT carries no rider or session
    identifier. We currently correlate a swap to a rider's app session
    purely by a time window on our side. Is there any plan to add something
    like an `idToken` (OCPP-style) to the frame, so we could associate a
    swap with a specific session at the protocol level instead?
12. **Server-to-cabinet commands.** Is there any command path from our
    server to the cabinet — e.g. to remotely lock a faulty battery's slot,
    or request a specific door to open? The documentation only shows
    cabinet → server frames besides ACK.
13. **Transport security.** The cabinet connects over the public internet
    with no visible authentication beyond the LOGIN frame, and no TLS. Is
    TLS on your roadmap, or a private APN option for larger deployments?
14. **OCPP roadmap.** Do you have plans to support OCPP 2.1's Battery
    Swapping extension on future hardware? That would let us use a single
    integration pattern across vendors.

We'd also appreciate a longer raw capture (ideally a full day, across more
cabinets) and, if possible, a test cabinet we could point at our staging
environment — that would let us validate retry and reconnection behaviour
directly. Given our 6-week deployment window, we'd be grateful for answers
within the next two weeks if at all possible.

Thanks,
Daniel
