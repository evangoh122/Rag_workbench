import client from './client';

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
