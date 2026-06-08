import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

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
  verification?: Verification;
  math_steps?: string[];
}

interface HistoryEntry {
  role: string;
  content: string;
}

export async function sendSqlMessage(
  message: string,
  history: HistoryEntry[],
): Promise<ChatResponse> {
  const response = await axios.post<ChatResponse>(`${API_BASE}/chat/sql`, {
    message,
    history,
  });
  return response.data;
}

export async function sendRagMessage(
  message: string,
  history: HistoryEntry[],
): Promise<ChatResponse> {
  const response = await axios.post<ChatResponse>(`${API_BASE}/chat/rag`, {
    message,
    history,
  });
  return response.data;
}
