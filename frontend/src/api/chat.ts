import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export interface ChatResponse {
  answer?: string;
  detail?: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: Record<string, unknown>[];
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
