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
  triples?: Record<string, string>[];
  // Standard Response Framework educational layers (sections 3–5)
  what_it_means?: string;
  how_to_interpret?: string;
  follow_ups?: string[];
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
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/auditable-rag', {
    message,
    ticker,
  });
  return response.data;
}
