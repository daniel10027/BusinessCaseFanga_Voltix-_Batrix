"""Schéma SQL : cinq tables, volontairement simples.

`batteries` et `cabinets` stockent l'état consolidé de l'agrégat sous forme de
JSONB (`state`), produit par `Battery.to_state()` / lu par `Battery.from_state()`
(domaine). Les colonnes à côté (`in_inventory`, `faulted`, `online`...) ne sont
que des copies dénormalisées, utiles pour filtrer sans désérialiser tout le
JSON — le contenu de `state` reste la seule source de vérité pour reconstruire
l'agrégat. Alternative rejetée : une colonne par champ (soc_pct, voltage_v...),
qui aurait dupliqué toute la politique de vérité des agrégats dans le schéma
SQL alors qu'elle est déjà encodée dans le domaine.

`observations` ne sert qu'à la déduplication (`dedup_key` unique) : le contenu
de l'observation elle-même n'a pas besoin d'être conservé, seul l'agrégat
consolidé compte.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

cabinets = Table(
    "cabinets",
    metadata,
    Column("cabinet_id", String, primary_key=True),
    Column("online", Boolean, nullable=False, server_default="true"),
    Column("last_seen_at", DateTime(timezone=True), nullable=True),
    Column("state", JSONB, nullable=False),
)

batteries = Table(
    "batteries",
    metadata,
    Column("serial", String, primary_key=True),
    Column("in_inventory", Boolean, nullable=False),
    Column("faulted", Boolean, nullable=False, server_default="false"),
    Column("state", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

observations = Table(
    "observations",
    metadata,
    Column("dedup_key", Text, primary_key=True),
    Column("kind", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

outbox = Table(
    "outbox",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("type", String, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("published_at", DateTime(timezone=True), nullable=True),
)

inventory = Table(
    "inventory",
    metadata,
    Column("serial", String, primary_key=True),
    Column("status", String, nullable=False),  # "registered" | "retired"
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
