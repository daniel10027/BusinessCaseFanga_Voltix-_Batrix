"""Métriques Prometheus (brief, 5.10), exposées par `GET /metrics`.

Les compteurs sont incrémentés directement dans `VoltixSession` et
`BatrixConsumer` (ce sont des objets de process, c'est l'usage normal de
`prometheus_client`). Les jauges liées à l'état courant (cabinets connectés,
outbox en attente) sont calculées à la volée par la route `/metrics`, en
interrogeant la base — pas besoin de les tenir à jour partout ailleurs.
"""

from prometheus_client import Counter, Gauge

VOLTIX_FRAMES_TOTAL = Counter(
    "voltix_frames_total", "Trames Voltix traitées, par résultat", ["result"]
)
VOLTIX_CRC_ERRORS_TOTAL = Counter("voltix_crc_errors_total", "Trames Voltix au CRC invalide")
BATRIX_MESSAGES_TOTAL = Counter(
    "batrix_messages_total", "Messages MQTT Batrix traités, par résultat", ["result"]
)
BATTERIES_UNKNOWN = Gauge("batteries_unknown", "Batteries en quarantaine (hors inventaire)")
CABINETS_CONNECTED = Gauge("cabinets_connected", "Cabinets actuellement en ligne")
OUTBOX_PENDING = Gauge("outbox_pending", "Événements de l'outbox en attente de publication")
