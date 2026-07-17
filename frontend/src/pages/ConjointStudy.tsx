import { useEffect, useState } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from 'recharts';
import { BarChart3, RefreshCcw, FlaskConical } from 'lucide-react';
import ConjointGate from '../components/ConjointGate';
import ConjointSurvey from '../components/ConjointSurvey';
import {
  getConjointResults,
  loadConjointPrefs,
  type ConjointResults,
  type ConjointPrefs,
  type ExperimentArm,
} from '../api/conjoint';

const tooltipStyle = {
  backgroundColor: 'var(--color-surface-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: '8px',
  color: 'var(--color-primary)',
  boxShadow: 'none',
} as const;

const BARS = ['#34d399', '#60a5fa', '#fbbf24', '#f472b6'];

export default function ConjointStudy() {
  const [results, setResults] = useState<ConjointResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Local study runner: gate → survey. Pre-fill from any saved arm/role.
  // Lazy initializers so localStorage is read once on mount, not every render.
  const [stage, setStage] = useState<'gate' | 'survey' | 'thanks'>('gate');
  const [arm, setArm] = useState<ExperimentArm>(() => loadConjointPrefs()?.arm ?? 'treatment');
  const [role, setRole] = useState<string | null>(() => loadConjointPrefs()?.role ?? null);

  const load = () => {
    setLoading(true);
    setError(null);
    getConjointResults()
      .then(setResults)
      .catch(() => setError('Failed to load study results.'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const onGateChosen = (prefs: ConjointPrefs) => {
    setArm(prefs.arm ?? 'treatment');
    setRole(prefs.role ?? null);
    setStage('survey');
  };

  const importanceData = (results?.attributes ?? []).map((a) => ({
    name: a.label,
    importance: a.importance,
  }));

  return (
    <div className="flex-1 overflow-y-auto">
      <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-10 flex items-center justify-between">
        <div>
          <h1 className="text-base md:text-xl font-semibold text-primary flex items-center gap-3">
            <FlaskConical className="text-secondary" size={20} />
            Answer Experience Study
          </h1>
          <p className="text-xs md:text-sm text-secondary mt-1">
            Choice-based conjoint on how answers are presented, plus a standard-vs-personalized usefulness test.
          </p>
        </div>
        <button
          onClick={load}
          className="fintech-button flex items-center gap-2 px-3 py-2 text-sm"
        >
          <RefreshCcw size={15} /> Refresh
        </button>
      </header>

      <div className="p-3 md:p-4 lg:p-8 space-y-6 max-w-5xl mx-auto">
        {/* ── Run the study ─────────────────────────────────────────────── */}
        <section className="fintech-card p-5">
          {stage === 'gate' && <ConjointGate onChosen={onGateChosen} />}
          {stage === 'survey' && (
            <ConjointSurvey
              arm={arm}
              role={role}
              onComplete={() => { setStage('thanks'); load(); }}
            />
          )}
          {stage === 'thanks' && (
            <div className="text-center py-4">
              <p className="text-[14px] text-secondary m-0">Thanks for participating.</p>
              <button
                onClick={() => setStage('gate')}
                className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-elevated border border-border text-muted text-[13px] hover:text-secondary transition-colors"
              >
                Run again
              </button>
            </div>
          )}
        </section>

        {loading && <div className="text-secondary text-sm">Loading results…</div>}
        {error && <div className="text-bearish text-sm">{error}</div>}

        {results && (
          <>
            {/* ── Test vs control ─────────────────────────────────────────── */}
            <section className="fintech-card p-5">
              <h2 className="text-[14px] font-semibold text-primary flex items-center gap-2 mb-1">
                <BarChart3 size={16} className="text-secondary" /> Usefulness: standard vs personalized
              </h2>
              <p className="text-[11px] text-muted mb-4">
                Mean usefulness (1–5) by arm. Assignment is self-selected, so read this as observational, not a randomized test.
              </p>
              {results.by_arm.length === 0 ? (
                <p className="text-[13px] text-muted m-0">No ratings yet.</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {results.by_arm.map((a) => (
                    <div key={a.arm} className="glass-sm p-3.5">
                      <div className="text-[11px] uppercase tracking-wider text-muted">
                        {a.arm === 'treatment' ? 'Personalized' : a.arm === 'control' ? 'Standard' : a.arm}
                      </div>
                      <div className="text-2xl font-semibold font-mono text-primary tabular-nums">
                        {a.avg_usefulness ?? '—'}
                      </div>
                      <div className="text-[11px] text-muted">n = {a.n}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* ── Attribute importance ────────────────────────────────────── */}
            <section className="fintech-card p-5">
              <h2 className="text-[14px] font-semibold text-primary mb-1">Attribute importance</h2>
              <p className="text-[11px] text-muted mb-4">
                Relative importance (%) of each answer attribute, from {results.n_choices} choice
                {results.n_choices === 1 ? '' : 's'} across {results.n_sessions_completed} completed session
                {results.n_sessions_completed === 1 ? '' : 's'}.
              </p>
              {importanceData.length === 0 || results.n_choices === 0 ? (
                <p className="text-[13px] text-muted m-0">No choice data yet — run the study above.</p>
              ) : (
                <div style={{ width: '100%', height: 240 }}>
                  <ResponsiveContainer>
                    <BarChart data={importanceData} layout="vertical" margin={{ left: 20, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
                      <XAxis type="number" stroke="var(--color-secondary)" fontSize={11} unit="%" />
                      <YAxis type="category" dataKey="name" stroke="var(--color-secondary)" fontSize={11} width={90} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${value}%`, 'Importance']} />
                      <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                        {importanceData.map((_, i) => (
                          <Cell key={i} fill={BARS[i % BARS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>

            {/* ── Part-worth utilities per attribute ──────────────────────── */}
            {results.n_choices > 0 && (
              <section className="fintech-card p-5">
                <h2 className="text-[14px] font-semibold text-primary mb-1">Level preferences (part-worths)</h2>
                <p className="text-[11px] text-muted mb-4">
                  Win-rate of each level when it appeared. Higher = more preferred.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {results.attributes.map((a) => (
                    <div key={a.key} className="glass-sm p-3.5">
                      <div className="text-[12px] font-semibold text-secondary mb-2">{a.label}</div>
                      {a.levels.map((lv) => (
                        <div key={lv.key} className="mb-2 last:mb-0">
                          <div className="flex items-center justify-between text-[12px] mb-1">
                            <span className="text-muted">{lv.label}</span>
                            <span className="text-secondary font-mono tabular-nums">{(lv.utility * 100).toFixed(0)}%</span>
                          </div>
                          <div className="h-1.5 w-full bg-surface-elevated rounded-full overflow-hidden">
                            <div className="h-full bg-accent" style={{ width: `${Math.round(lv.utility * 100)}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
