import client from './client';
import type { Triple } from './chat';

// One node/edge's source evidence — returned by GET /api/graph/evidence.
export interface GraphEvidence {
  chunk_id: string;
  ticker: string;
  accession: string;
  section_id: string;
  form_type: string;
  period_of_report: string;
  excerpt: string;
  edgar_url: string;
}

export async function getGraphEvidence(chunkId: string): Promise<GraphEvidence> {
  const res = await client.get<GraphEvidence>('/graph/evidence', {
    params: { chunk_id: chunkId },
  });
  return res.data;
}

// Aggregate knowledge-graph stats — returned by GET /api/graph/analytics.
export interface GraphAnalytics {
  totals: {
    triples: number;
    companies: number;
    relation_types: number;
    entities: number;
    xbrl_linked: number;
  };
  relations: { predicate: string; count: number; avg_confidence: number }[];
  entity_types: { type: string; count: number }[];
  per_company: { ticker: string; triples: number; relation_types: number }[];
}

export async function getGraphAnalytics(): Promise<GraphAnalytics> {
  const res = await client.get<GraphAnalytics>('/graph/analytics');
  return res.data;
}

// Knowledge-graph triples for the dedicated Graph tab. Optionally per-company.
export async function getGraphTriples(
  ticker?: string,
  limit = 300,
): Promise<Triple[]> {
  const res = await client.get<{ triples: Triple[]; count: number }>(
    '/graph/triples',
    { params: { ...(ticker ? { ticker } : {}), limit } },
  );
  return res.data.triples;
}
