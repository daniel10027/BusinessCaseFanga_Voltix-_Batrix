/**
 * Enveloppe commune a tous les evenements publies par le relais outbox de
 * fanga-ingest (brief, section 5.7) : {event_id, type, version, occurred_at, payload}.
 */
export interface FangaWebhookEvent<TPayload = unknown> {
  event_id: string;
  type: string;
  version: number;
  occurred_at: string;
  payload: TPayload;
}
