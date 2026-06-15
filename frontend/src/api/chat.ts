import client from './client';

export interface Source {
  ticker: string;
  accession: string;
  section: string;
  text: string;
  edgar_url: string;
  distance?: number;
}

export interface XBRLFact {
  concept: string;
  label: string;
  value: number;
  unit: string;
  period: string;
  ticker: string;
  is_verified?: boolean;
}

export interface PolygonData {
  ticker: string;
  name: string;
  description?: string;
  last_price?: number;
  price_date?: string;
  volume?: number;
}

export interface Verification {
  status: 'verified' | 'mismatch' | 'unverifiable' | 'not_checked';
  claimed_value?: number;
  xbrl_value?: number;
  note?: string;
}

export interface ChatResponse {
  answer?: string;
  detail?: string;
  // Company the query resolved to; the UI persists this so follow-ups that
  // name no company stay grounded on the same ticker.
  ticker?: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: Record<string, unknown>[];
  sources?: Source[];
  xbrl_facts?: XBRLFact[];
  relevant_xbrl?: XBRLFact[];
  xbrl_badge?: string;
  xbrl_group?: string;
  polygon_data?: PolygonData[];
  verification?: {
    status: string;
    reasoning: string;
  };
  math_steps?: string[];
  pipeline_status?: Record<string, 'success' | 'error' | 'pending'>;
  entities?: string[];
  triples?: Triple[];
  // Standard Response Framework educational layers (sections 3–5)
  what_it_means?: string;
  how_to_interpret?: string;
  follow_ups?: string[];
  // Optional chart spec (recharts), built from XBRL when the LLM uses the
  // charting tool.
  chart?: ChartSpec;
}

// A chart the backend built from filed XBRL facts (recharts-ready).
export interface ChartSpec {
  type: 'line' | 'bar';
  title: string;
  metric: string;
  label: string;
  unit: 'USD' | '%' | string;
  ticker: string;
  data: { period: string; value: number }[];
}

// A knowledge-graph triple. Phase C adds source refs + node types (optional so
// legacy/code-graph triples without them still render).
export interface Triple {
  subject: string;
  predicate: string;
  object: string;
  subject_type?: string;
  object_type?: string;
  chunk_id?: string;
  source_file?: string;
  source_loc?: string;
  confidence?: number;
}

interface HistoryEntry {
  role: string;
  content: string;
}

export async function sendSqlMessage(
  message: string,
  history: HistoryEntry[],
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/sql', {
    message,
    history,
  });
  return response.data;
}

export async function sendRagMessage(
  message: string,
  history: HistoryEntry[],
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/rag', {
    message,
    history,
  });
  return response.data;
}

export async function sendGraphRagMessage(
  message: string,
  ticker: string = 'MU',
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/graph-rag', {
    message,
    ticker,
  });
  return response.data;
}

export async function sendAuditableRagMessage(
  message: string,
  ticker: string = 'MU',
  history: HistoryEntry[] = [],
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/auditable-rag', {
    message,
    ticker,
    history,
  });
  return response.data;
}
