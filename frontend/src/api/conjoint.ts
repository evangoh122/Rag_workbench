import client from './client';

// ── Types (mirror api/routes/conjoint.py) ────────────────────────────────────
export interface Level {
  key: string;
  label: string;
}

export interface Attribute {
  key: string;
  label: string;
  levels: Level[];
}

export interface Role {
  key: string;
  name: string;
  persona: string;
  situation: string;
  motivation: string;
  outcome: string;
  emotional_job: string;
  social_job: string;
  answer_guidance: string;
}

/** A bundle of attribute-level choices: { attributeKey: levelKey }. */
export type Profile = Record<string, string>;

export interface Task {
  index: number;
  profile_a: Profile;
  profile_b: Profile;
}

/** Experiment arm: control = standard app, treatment = role-based personalization. */
export type ExperimentArm = 'control' | 'treatment';

export interface SessionStart {
  session_id: string;
  arm: ExperimentArm;
  role: string | null;
  tasks: Task[];
  attributes: Attribute[];
  roles: Role[];
}

/** The winning level per attribute, derived from a respondent's own choices. */
export type AppliedPrefs = Record<string, string>;

export interface ResultLevel {
  key: string;
  label: string;
  utility: number;
  appearances: number;
  wins: number;
}

export interface ResultAttribute {
  key: string;
  label: string;
  levels: ResultLevel[];
  importance: number;
}

export interface ConjointResults {
  n_sessions_completed: number;
  n_choices: number;
  attributes: ResultAttribute[];
  usefulness: {
    average: number | null;
    count: number;
    distribution: { score: number; count: number }[];
  };
  by_arm: { arm: string; avg_usefulness: number | null; n: number }[];
  assignment: string;
}

// ── API calls ─────────────────────────────────────────────────────────────────
export async function getConjointAttributes(): Promise<{ attributes: Attribute[]; roles: Role[] }> {
  const res = await client.get('/conjoint/attributes');
  return res.data;
}

export async function startConjointSession(
  arm: ExperimentArm,
  role?: string | null,
  tasks = 6,
): Promise<SessionStart> {
  const res = await client.post<SessionStart>('/conjoint/session', {
    arm,
    role: role ?? null,
    distinct_id: getDistinctId(),
    tasks,
  });
  return res.data;
}

export async function recordConjointResponse(
  session_id: string,
  task_index: number,
  profile_a: Profile,
  profile_b: Profile,
  chosen: 'A' | 'B',
): Promise<void> {
  await client.post('/conjoint/response', { session_id, task_index, profile_a, profile_b, chosen });
}

export async function completeConjointSession(
  session_id: string,
  usefulness: number,
  comment = '',
): Promise<{ applied_prefs: AppliedPrefs }> {
  const res = await client.post('/conjoint/complete', { session_id, usefulness, comment });
  return res.data;
}

export async function getConjointResults(): Promise<ConjointResults> {
  const res = await client.get<ConjointResults>('/conjoint/results');
  return res.data;
}

// ── Local personalization prefs ───────────────────────────────────────────────
// The survey's winning levels (+ chosen role) are persisted client-side and
// applied to the chat experience. No server round-trip needed to read them.
export interface ConjointPrefs {
  arm?: ExperimentArm;     // control | treatment
  role?: string | null;
  answer_basis?: string;   // role_based | standard
  answer_style?: string;   // direct | explained
  prompts?: string;        // guided | suggested
  evidence?: string;       // text_only | graph_metrics
}

const PREFS_KEY = 'conjoint_prefs';
const DONE_KEY = 'conjoint_completed';
const DID_KEY = 'conjoint_distinct_id';

export function loadConjointPrefs(): ConjointPrefs | null {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? (JSON.parse(raw) as ConjointPrefs) : null;
  } catch {
    return null;
  }
}

export function saveConjointPrefs(prefs: ConjointPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* localStorage unavailable — personalization simply won't persist */
  }
}

export function clearConjointPrefs(): void {
  try {
    localStorage.removeItem(PREFS_KEY);
    localStorage.removeItem(DONE_KEY);
  } catch {
    /* no-op */
  }
}

export function hasCompletedConjoint(): boolean {
  try {
    return localStorage.getItem(DONE_KEY) === '1';
  } catch {
    return false;
  }
}

export function markConjointCompleted(): void {
  try {
    localStorage.setItem(DONE_KEY, '1');
  } catch {
    /* no-op */
  }
}

/** A stable-ish anonymous id so sessions from one browser can be grouped. */
export function getDistinctId(): string {
  try {
    let id = localStorage.getItem(DID_KEY);
    if (!id) {
      id = `cj_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      localStorage.setItem(DID_KEY, id);
    }
    return id;
  } catch {
    return 'cj_anon';
  }
}
