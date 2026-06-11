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
  verification?: {
    status: string;
    reasoning: string;
  };
  math_steps?: string[];
  pipeline_status?: Record<string, 'success' | 'error' | 'pending'>;
  entities?: string[];
  triples?: Record<string, string>[];
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
  ticker: string = 'AAPL',
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/graph-rag', {
    message,
    ticker,
  });
  return response.data;
}

export async function sendAuditableRagMessage(
  message: string,
  ticker: string = 'AAPL',
): Promise<ChatResponse> {
  const response = await client.post<ChatResponse>('/chat/auditable-rag', {
    message,
    ticker,
  });
  return response.data;
}
