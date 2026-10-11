"""Vérification de signature HMAC pour les appels internes (NestJS → nous).

Même convention que le relais outbox (nous → NestJS) : un en-tête
`X-Fanga-Signature` portant le HMAC-SHA256 hexadécimal du corps brut de la
requête, calculé avec un secret partagé.
"""

import hmac

SIGNATURE_HEADER = "X-Fanga-Signature"


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature)
