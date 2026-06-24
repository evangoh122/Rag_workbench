import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, ChevronRight, Star, X, Loader2, BarChart3 } from 'lucide-react';
import {
  startConjointSession,
  recordConjointResponse,
  completeConjointSession,
  saveConjointPrefs,
  markConjointCompleted,
  type Attribute,
  type Task,
  type Profile,
  type ConjointPrefs,
  type ExperimentArm,
} from '../api/conjoint';

type Phase = 'loading' | 'tasks' | 'vote' | 'done' | 'error';

interface Props {
  /** Arm chosen at the entry gate. control = vote only; treatment = tasks + vote. */
  arm: ExperimentArm;
  /** Role chosen at the entry gate (treatment only). */
  role?: string | null;
  /** Called with the (possibly updated) personalization prefs on completion. */
  onComplete?: (prefs: ConjointPrefs) => void;
  /** Optional close handler (shows an X in the header when provided). */
  onClose?: () => void;
  /** Optional "view results" action shown on the done screen. */
  onViewResults?: () => void;
  /** Number of choice tasks to run (treatment only). */
  tasks?: number;
}

const TONE = {
  card: 'glass-sm p-4',
  primaryBtn:
    'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent/15 border border-accent/30 text-accent font-medium text-[13px] hover:bg-accent/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
  ghostBtn:
    'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-surface-elevated border border-border text-muted text-[13px] hover:text-secondary transition-colors disabled:opacity-50',
};

export default function ConjointSurvey({ arm, role = null, onComplete, onClose, onViewResults, tasks = 6 }: Props) {
  const [phase, setPhase] = useState<Phase>('loading');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [attributes, setAttributes] = useState<Attribute[]>([]);
  const [sessionId, setSessionId] = useState<string>('');
  const [taskList, setTaskList] = useState<Task[]>([]);
  const [taskIdx, setTaskIdx] = useState(0);

  const [usefulness, setUsefulness] = useState(0);
  const [hoverScore, setHoverScore] = useState(0);
  const [comment, setComment] = useState('');
  const [appliedPrefs, setAppliedPrefs] = useState<ConjointPrefs | null>(null);

  // Create the session: treatment gets choice tasks, control goes straight to
  // the usefulness vote. On failure we land on a dedicated error phase with a
  // retry — never the interactive phases with an empty session (review finding).
  const startSession = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPhase('loading');
    startConjointSession(arm, role, tasks)
      .then((s) => {
        if (cancelled) return;
        setSessionId(s.session_id);
        setTaskList(s.tasks);
        setAttributes(s.attributes);
        setPhase(s.tasks.length > 0 ? 'tasks' : 'vote');
      })
      .catch(() => {
        if (cancelled) return;
        setError('Could not start the study. Please try again.');
        setPhase('error');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [arm, role, tasks]);

  useEffect(() => startSession(), [startSession]);

  const levelLabel = useMemo(() => {
    const map: Record<string, Record<string, string>> = {};
    for (const a of attributes) {
      map[a.key] = {};
      for (const lv of a.levels) map[a.key][lv.key] = lv.label;
    }
    return (attrKey: string, levelKey: string) => map[attrKey]?.[levelKey] ?? levelKey;
  }, [attributes]);

  const choose = async (chosen: 'A' | 'B') => {
    if (loading) return;
    const task = taskList[taskIdx];
    if (!task) return;
    setLoading(true);
    setError(null);
    try {
      await recordConjointResponse(sessionId, task.index, task.profile_a, task.profile_b, chosen);
      if (taskIdx + 1 < taskList.length) {
        setTaskIdx(taskIdx + 1);
      } else {
        setPhase('vote');
      }
    } catch {
      setError('Could not save your choice. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const submitVote = async () => {
    if (!usefulness) return;
    setLoading(true);
    setError(null);
    try {
      const { applied_prefs } = await completeConjointSession(sessionId, usefulness, comment);
      // Control keeps standard rendering (no answer_* keys); treatment applies
      // its derived levels on top of the chosen arm + role.
      const prefs: ConjointPrefs = { arm, role, ...applied_prefs };
      saveConjointPrefs(prefs);
      markConjointCompleted();
      setAppliedPrefs(prefs);
      onComplete?.(prefs);
      setPhase('done');
    } catch {
      setError('Could not submit your rating. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Render helpers ────────────────────────────────────────────────────────
  const Header = ({ title, sub }: { title: string; sub?: string }) => (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div>
        <h3 className="text-[15px] font-semibold text-primary m-0">{title}</h3>
        {sub && <p className="text-[12px] text-muted mt-1 mb-0">{sub}</p>}
      </div>
      {onClose && (
        <button onClick={onClose} className="text-muted hover:text-secondary transition-colors" aria-label="Close">
          <X size={18} />
        </button>
      )}
    </div>
  );

  const ProfileCard = ({ title, profile, onPick }: { title: string; profile: Profile; onPick: () => void }) => (
    <button
      onClick={onPick}
      disabled={loading}
      className="flex-1 text-left glass-sm p-4 border border-border hover:border-accent/50 hover:bg-accent/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed rounded-xl group"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</span>
        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-accent text-[11px] font-medium inline-flex items-center gap-1">
          Choose <ChevronRight size={13} />
        </span>
      </div>
      <ul className="space-y-2 m-0 p-0 list-none">
        {attributes.map((a) => (
          <li key={a.key} className="flex items-center justify-between gap-3 text-[13px]">
            <span className="text-muted">{a.label}</span>
            <span className="text-secondary font-medium text-right">{levelLabel(a.key, profile[a.key])}</span>
          </li>
        ))}
      </ul>
    </button>
  );

  // ── Phase: loading ─────────────────────────────────────────────────────────
  if (phase === 'loading') {
    return (
      <div className="flex items-center gap-2 text-muted text-[13px] py-8">
        <Loader2 size={16} className="animate-spin" /> Preparing…
      </div>
    );
  }

  // ── Phase: error (session couldn't start) ───────────────────────────────────
  if (phase === 'error') {
    return (
      <div>
        <Header title="Something went wrong" />
        <p className="text-[13px] text-bearish mb-4">{error ?? 'Could not start the study.'}</p>
        <div className="flex items-center gap-2.5">
          <button onClick={startSession} disabled={loading} className={TONE.primaryBtn}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : null} Retry
          </button>
          {onClose && (
            <button onClick={onClose} className={TONE.ghostBtn}>
              Close
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Phase: choice tasks (treatment only) ────────────────────────────────────
  if (phase === 'tasks') {
    const task = taskList[taskIdx];
    return (
      <div>
        <Header title="Which answer experience would you prefer?" sub={`Task ${taskIdx + 1} of ${taskList.length}`} />
        <div className="h-1 w-full bg-surface-elevated rounded-full overflow-hidden mb-4">
          <div className="h-full bg-accent transition-all duration-300" style={{ width: `${(taskIdx / taskList.length) * 100}%` }} />
        </div>
        {error && <p className="text-[12px] text-bearish mb-3">{error}</p>}
        {task && (
          <div className="flex flex-col sm:flex-row gap-3">
            <ProfileCard title="Profile A" profile={task.profile_a} onPick={() => choose('A')} />
            <div className="flex sm:flex-col items-center justify-center text-muted text-[11px] font-semibold">vs</div>
            <ProfileCard title="Profile B" profile={task.profile_b} onPick={() => choose('B')} />
          </div>
        )}
        <p className="text-[11px] text-muted mt-3 mb-0 italic">
          Pick the bundle you'd rather receive when asking the assistant a question.
        </p>
      </div>
    );
  }

  // ── Phase: usefulness vote (both arms) ──────────────────────────────────────
  if (phase === 'vote') {
    return (
      <div>
        <Header title="One last thing" sub="Overall, how useful is this application to you?" />
        {error && <p className="text-[12px] text-bearish mb-3">{error}</p>}
        <div className="flex items-center gap-1.5 mb-4">
          {[1, 2, 3, 4, 5].map((s) => (
            <button
              key={s}
              onMouseEnter={() => setHoverScore(s)}
              onMouseLeave={() => setHoverScore(0)}
              onClick={() => setUsefulness(s)}
              aria-label={`${s} star${s > 1 ? 's' : ''}`}
              className="p-1 transition-transform hover:scale-110"
            >
              <Star size={28} className={(hoverScore || usefulness) >= s ? 'text-amber-400 fill-amber-400' : 'text-border'} />
            </button>
          ))}
          <span className="ml-2 text-[12px] text-muted">{usefulness ? `${usefulness}/5` : 'Tap to rate'}</span>
        </div>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value.slice(0, 2000))}
          placeholder="Anything else? (optional)"
          rows={3}
          className="w-full bg-surface-elevated border border-border rounded-lg p-3 text-[13px] text-secondary placeholder:text-muted focus:border-accent/50 focus:outline-none resize-none"
        />
        <div className="flex items-center gap-2.5 mt-4">
          <button onClick={submitVote} disabled={!usefulness || loading} className={TONE.primaryBtn}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
            Submit
          </button>
        </div>
      </div>
    );
  }

  // ── Phase: done ─────────────────────────────────────────────────────────────
  const prefLabel = (attrKey: string) => {
    const v = (appliedPrefs as Record<string, string> | null)?.[attrKey];
    return v ? levelLabel(attrKey, v) : '—';
  };
  const isTreatment = arm === 'treatment';

  return (
    <div>
      <Header
        title="Thank you"
        sub={isTreatment ? "We've tuned how answers are shown to match your choices." : 'Thanks for rating the application.'}
      />
      {isTreatment && (
        <div className={TONE.card}>
          <ul className="space-y-2 m-0 p-0 list-none">
            {attributes.map((a) => (
              <li key={a.key} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="text-muted">{a.label}</span>
                <span className="text-accent font-medium">{prefLabel(a.key)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex items-center gap-2.5 mt-4">
        {onClose && (
          <button onClick={onClose} className={TONE.primaryBtn}>
            <Check size={15} /> Done
          </button>
        )}
        {onViewResults && (
          <button onClick={onViewResults} className={TONE.ghostBtn}>
            <BarChart3 size={15} /> View aggregate results
          </button>
        )}
      </div>
    </div>
  );
}
