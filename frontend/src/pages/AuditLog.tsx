import { useEffect, useState, useCallback } from 'react';
import { ShieldCheck, RefreshCw, ChevronDown, ChevronRight, AlertTriangle, CheckCircle, Clock } from 'lucide-react';

import { getPosthog } from '../utils/posthog'

interface AuditRun {
  run_id: string;
  timestamp: string;
  ticker: string | null;
  question: string | null;
  answer: string | null;
  query_type: string | null;
  eval_route: string | null;
  confidence: number | null;
  verification_status: string | null;
  model_used: string | null;
  source_docs: string[];
  chunk_ids: string[];
  xbrl_facts_cited: { concept: string; value: number; period_end: string; form_type: string }[];
  math_result: string | null;
  math_steps: string[];
  eval_triggers: string[];
  review_id: string | null;
}

interface AuditStats {
  total_runs: number;
  unique_tickers: number;
  avg_confidence: number | null;
  escalated: number;
  sampled_review: number;
  auto_approved: number;
  first_run: string | null;
  last_run: string | null;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

function routeBadge(route: string | null) {
  if (!route) return null;
  const styles: Record<string, string> = {
    AUTO: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    SAMPLED_REVIEW: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    ESCALATE: 'bg-red-500/10 text-red-400 border-red-500/20',
  };
  return (
    <span className={`px-2 py-0.5 rounded-md text-xs font-semibold border ${styles[route] ?? 'bg-gray-500/10 text-gray-400 border-gray-500/20'}`}>
      {route}
    </span>
  );
}

function verificationIcon(status: string | null) {
  if (status === 'PASS') return <CheckCircle size={14} className="text-emerald-400" />;
  if (status === 'FAIL') return <AlertTriangle size={14} className="text-red-400" />;
  return <Clock size={14} className="text-gray-500" />;
}

function RunTableRow({ run }: { run: AuditRun }) {
  const [expanded, setExpanded] = useState(false);

  const ts = new Date(run.timestamp).toLocaleString();
  const conf = run.confidence != null ? `${(run.confidence * 100).toFixed(1)}%` : '—';

  return (
    <>
      <tr
        className="border-b border-border hover:bg-surface-elevated cursor-pointer transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <td className="px-4 py-3 text-secondary text-xs font-mono tabular-nums">
          {expanded ? <ChevronDown size={14} className="inline mr-1" /> : <ChevronRight size={14} className="inline mr-1" />}
          {run.run_id.slice(0, 8)}…
        </td>
        <td className="px-4 py-3 text-xs text-secondary whitespace-nowrap tabular-nums">{ts}</td>
        <td className="px-4 py-3">
          <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-md text-xs font-mono font-semibold">
            {run.ticker ?? '—'}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-primary max-w-xs truncate">{run.question ?? '—'}</td>
        <td className="px-4 py-3">{routeBadge(run.eval_route)}</td>
        <td className="px-4 py-3 text-xs text-secondary tabular-nums">{conf}</td>
        <td className="px-4 py-3">
          <span className="flex items-center gap-1 text-xs text-secondary">
            {verificationIcon(run.verification_status)}
            {run.verification_status ?? '—'}
          </span>
        </td>
      </tr>

      {expanded && (
        <tr className="bg-background border-b border-border">
          <td colSpan={7} className="px-6 py-5">
            <ExpandedContent run={run} />
          </td>
        </tr>
      )}
    </>
  );
}

function RunCard({ run }: { run: AuditRun }) {
  const [expanded, setExpanded] = useState(false);

  const ts = new Date(run.timestamp).toLocaleString();
  const conf = run.confidence != null ? `${(run.confidence * 100).toFixed(1)}%` : '—';

  return (
    <>
      <div
        className="bg-surface border border-border rounded-xl p-4 cursor-pointer transition-colors hover:bg-surface-elevated"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <span className="text-secondary">
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
            <span className="text-xs font-mono text-secondary tabular-nums">{run.run_id.slice(0, 8)}…</span>
            <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-md text-xs font-mono font-semibold">
              {run.ticker ?? '—'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {routeBadge(run.eval_route)}
          </div>
        </div>
        <p className="text-sm text-primary truncate mb-2">{run.question ?? '—'}</p>
        <div className="flex items-center justify-between text-xs text-secondary">
          <span className="tabular-nums">{ts}</span>
          <div className="flex items-center gap-3">
            <span className="tabular-nums">Conf: {conf}</span>
            <span className="flex items-center gap-1">
              {verificationIcon(run.verification_status)}
              {run.verification_status ?? '—'}
            </span>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="bg-background border border-border rounded-xl p-4 -mt-2 mb-2">
          <ExpandedContent run={run} />
        </div>
      )}
    </>
  );
}

function ExpandedContent({ run }: { run: AuditRun }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-5 text-sm">
      {/* Answer */}
      <div className="md:col-span-2">
        <div className="text-xs font-semibold text-secondary uppercase tracking-widest mb-2">Answer</div>
        <div className="bg-surface border border-border rounded-xl p-3 md:p-4 text-primary leading-relaxed text-sm">
          {run.answer || '—'}
        </div>
      </div>

      {/* XBRL Facts */}
      {run.xbrl_facts_cited.length > 0 && (
        <div className="md:col-span-2">
          <div className="text-xs font-semibold text-secondary uppercase tracking-widest mb-2">XBRL Facts Cited</div>
          <div className="bg-background border border-border rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface border-b border-border">
                    <th className="text-left px-3 md:px-4 py-2 text-secondary font-semibold">Concept</th>
                    <th className="text-left px-3 md:px-4 py-2 text-secondary font-semibold">Value</th>
                    <th className="text-left px-3 md:px-4 py-2 text-secondary font-semibold">Period End</th>
                    <th className="text-left px-3 md:px-4 py-2 text-secondary font-semibold">Form</th>
                  </tr>
                </thead>
                <tbody>
                  {run.xbrl_facts_cited.map((f, i) => (
                    <tr key={i} className={i % 2 === 0 ? '' : 'bg-surface/30'}>
                      <td className="px-3 md:px-4 py-2 font-mono text-blue-300 break-all">{f.concept}</td>
                      <td className="px-3 md:px-4 py-2 text-bullish font-mono tabular-nums">
                        {typeof f.value === 'number' ? f.value.toLocaleString() : f.value}
                      </td>
                      <td className="px-3 md:px-4 py-2 text-secondary tabular-nums">{f.period_end}</td>
                      <td className="px-3 md:px-4 py-2 text-secondary">{f.form_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Math Steps */}
      {run.math_steps.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Calculation Steps</div>
          <ol className="space-y-1">
            {run.math_steps.map((s, i) => (
              <li key={i} className="text-xs text-gray-400 flex gap-2">
                <span className="text-gray-600 font-mono w-5 flex-shrink-0">{i + 1}.</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
          {run.math_result && (
            <div className="mt-2 text-xs text-emerald-400 font-mono">= {run.math_result}</div>
          )}
        </div>
      )}

      {/* Source Docs */}
      {run.source_docs.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-secondary uppercase tracking-widest mb-2">Source Documents</div>
          <div className="flex flex-col gap-1">
            {run.source_docs.map((d, i) => (
              <span key={i} className="text-xs font-mono text-secondary bg-surface-elevated border border-border px-3 py-1.5 rounded-lg break-all">{d}</span>
            ))}
          </div>
        </div>
      )}

      {/* Meta */}
      <div className="md:col-span-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-secondary pt-2 border-t border-border/50">
        <span>Model: <span className="text-primary font-mono">{run.model_used ?? '—'}</span></span>
        <span>Query type: <span className="text-primary">{run.query_type ?? '—'}</span></span>
        {run.review_id && <span>Review ID: <span className="text-primary font-mono">{run.review_id}</span></span>}
        {run.eval_triggers.length > 0 && (
          <span>Triggers: <span className="text-bearish">{run.eval_triggers.join(', ')}</span></span>
        )}
      </div>
    </div>
  );
}

export default function AuditLog() {
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [tickerFilter, setTickerFilter] = useState('');
  const [routeFilter, setRouteFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (tickerFilter) params.set('ticker', tickerFilter.toUpperCase());
      if (routeFilter) params.set('eval_route', routeFilter);

      const [runsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/audit?${params}`),
        fetch(`${API_BASE}/audit/summary/stats`),
      ]);

      if (!runsRes.ok) throw new Error(`HTTP ${runsRes.status}`);
      setRuns(await runsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tickerFilter, routeFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (import.meta.env.VITE_POSTHOG_KEY) {
      getPosthog().then(p => p.capture('$pageview', { view: 'audit_log' }))
    }
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm flex-shrink-0 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-base md:text-xl font-semibold text-primary flex items-center gap-2 md:gap-3">
            <ShieldCheck className="text-amber-400" size={18} />
            Audit Log
          </h1>
          <p className="text-xs md:text-sm text-secondary mt-0.5">Complete record of every RAG pipeline run — queryable by regulators.</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-3 py-2 bg-surface-elevated border border-border rounded-xl text-sm text-secondary hover:text-primary transition-all cursor-pointer min-h-[44px]"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-3 md:px-4 lg:px-8 py-3 md:py-6">

        {/* Stats bar */}
        {stats && (
          <div className="grid grid-cols-2 gap-3 md:gap-4 mb-4 md:mb-6">
            {[
              { label: 'Total Runs', value: stats.total_runs, color: 'text-primary' },
              { label: 'Auto Approved', value: stats.auto_approved, color: 'text-bullish' },
              { label: 'Sampled Review', value: stats.sampled_review, color: 'text-yellow-400' },
              { label: 'Escalated', value: stats.escalated, color: 'text-bearish' },
            ].map(s => (
              <div key={s.label} className="bg-surface border border-border rounded-xl px-4 md:px-5 py-3 md:py-4">
                <div className={`text-xl md:text-2xl font-bold ${s.color} tabular-nums`}>{s.value}</div>
                <div className="text-[10px] md:text-xs text-secondary mt-1 uppercase tracking-widest">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters — stacked on mobile, row on desktop */}
        <div className="flex flex-col md:flex-row gap-2 md:gap-3 mb-4 md:mb-5">
          <input
            type="text"
            placeholder="Filter by ticker (e.g. NVDA)"
            value={tickerFilter}
            onChange={e => setTickerFilter(e.target.value)}
            className="bg-surface-elevated border border-border rounded-xl px-4 py-2.5 md:py-2 text-sm text-primary placeholder-secondary focus:outline-none focus:border-amber-500/40 w-full md:w-52 transition-all tabular-nums"
          />
          <select
            value={routeFilter}
            onChange={e => setRouteFilter(e.target.value)}
            className="bg-surface-elevated border border-border rounded-xl px-4 py-2.5 md:py-2 text-sm text-primary focus:outline-none focus:border-amber-500/40 cursor-pointer transition-all appearance-none"
          >
            <option value="">All routes</option>
            <option value="AUTO">AUTO</option>
            <option value="SAMPLED_REVIEW">SAMPLED_REVIEW</option>
            <option value="ESCALATE">ESCALATE</option>
          </select>
        </div>

        {/* Content */}
        {error ? (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-5 py-4 text-red-400 text-sm">
            <AlertTriangle size={16} />
            {error}
          </div>
        ) : loading ? (
          <div className="text-gray-500 text-sm py-12 text-center">Loading audit records…</div>
        ) : runs.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <ShieldCheck size={40} className="mx-auto mb-4 text-gray-700" />
            <p className="text-base font-medium text-gray-400">No audit records yet</p>
            <p className="text-sm mt-1">Records appear here after each RAG pipeline query.</p>
          </div>
        ) : (
          <>
            {/* Desktop: table */}
            <div className="hidden md:block bg-surface border border-border rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface-elevated border-b border-border">
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Run ID</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Timestamp</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Ticker</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Question</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Route</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Confidence</th>
                      <th className="text-left px-4 py-3 text-secondary font-semibold text-xs uppercase tracking-wider">Verification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => <RunTableRow key={run.run_id} run={run} />)}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Mobile: card list */}
            <div className="md:hidden flex flex-col gap-2">
              {runs.map(run => (
                <RunCard key={run.run_id} run={run} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
