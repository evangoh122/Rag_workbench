import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

export interface ReviewDecision {
  id: string;
  cik: string;
  accession: string;
  form_type: string;
  route: 'SAMPLED_REVIEW' | 'ESCALATE';
  confidence: number;
  triggers_fired: string[];
  status: 'pending' | 'reviewed';
  created_at: string;
}

export interface Verdict {
  decision_id: string;
  reviewer_agrees: boolean;
  notes?: string;
}

export interface DriftStatus {
  agreement_rate: number;
  agreement_floor: number;
  agreement_alert: boolean;
  unrecognized_concept_count: number;
  concept_spike_threshold: number;
  concept_alert: boolean;
  window_size: number;
  last_updated: string;
}

export interface CalibrationResult {
  message: string;
  updated_thresholds?: Record<string, number>;
}

export async function getReviewQueue(): Promise<ReviewDecision[]> {
  const response = await axios.get<ReviewDecision[]>(`${API_BASE}/review/queue`);
  return response.data;
}

export async function submitVerdict(verdict: Verdict): Promise<void> {
  await axios.post(`${API_BASE}/review/verdict`, verdict);
}

export async function getDriftStatus(): Promise<DriftStatus> {
  const response = await axios.get<DriftStatus>(`${API_BASE}/review/drift`);
  return response.data;
}

export async function triggerCalibration(): Promise<CalibrationResult> {
  const response = await axios.post<CalibrationResult>(`${API_BASE}/review/calibrate`);
  return response.data;
}
