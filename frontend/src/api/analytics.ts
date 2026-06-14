import client from './client';

export interface AnalyticsSummary {
  total_events: number;
  unique_visitors: number;
  by_event: { event: string; count: number }[];
  by_view: { view: string; count: number }[];
  daily: { date: string; count: number }[];
  recent: { event: string; view: string | null; ts: string }[];
}

export interface PosthogSummary {
  configured: boolean;
  events_7d?: number;
  top_events?: { event: string; count: number }[];
  error?: string;
}

export async function getAnalyticsSummary(days = 14): Promise<AnalyticsSummary> {
  const res = await client.get<AnalyticsSummary>('/analytics/summary', { params: { days } });
  return res.data;
}

export async function getPosthogSummary(): Promise<PosthogSummary> {
  const res = await client.get<PosthogSummary>('/analytics/posthog');
  return res.data;
}
