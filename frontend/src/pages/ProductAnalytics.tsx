import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { BarChart3, Users, Activity, Database, RefreshCcw } from 'lucide-react';
import {
  getAnalyticsSummary, getPosthogSummary,
  type AnalyticsSummary, type PosthogSummary,
} from '../api/analytics';

const tooltipStyle = {
  backgroundColor: 'var(--color-surface-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: '8px',
  color: 'var(--color-primary)',
  boxShadow: 'none',
} as const;

function Kpi({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="fintech-card p-4 flex items-center gap-4">
      <div className="text-secondary">{icon}</div>
      <div>
        <div className="text-[11px] uppercase tracking-widest text-secondary">{label}</div>
        <div className="text-2xl font-semibold font-mono text-primary tabular-nums">{value}</div>
      </div>
    </div>
  );
}

function ProductAnalytics() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [ph, setPh] = useState<PosthogSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([getAnalyticsSummary(14), getPosthogSummary().catch(() => null)])
      .then(([summary, posthog]) => { setData(summary); setPh(posthog); })
      .catch(() => setError('Failed to load analytics.'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-10 flex items-center justify-between">
        <div>
          <h1 className="text-base md:text-xl font-semibold text-primary flex items-center gap-3">
            <BarChart3 className="text-secondary" size={20} />
            Product Analytics
          </h1>
          <p className="text-xs md:text-sm text-secondary mt-1">
            Self-captured usage events (DuckDB) {ph?.configured ? '+ PostHog' : ''}
          </p>
        </div>
        <button
          onClick={load}
          className="fintech-button flex items-center gap-2 px-3 py-2 text-sm"
        >
          <RefreshCcw size={15} /> Refresh
        </button>
      </header>

      <div className="p-3 md:p-4 lg:p-8 space-y-6 max-w-6xl mx-auto">
        {loading && <div className="text-secondary text-sm">Loading…</div>}
        {error && <div className="text-bearish text-sm">{error}</div>}

        {data && (
          <>
            {/* KPIs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <Kpi icon={<Activity size={20} />} label="Total events" value={data.total_events.toLocaleString()} />
              <Kpi icon={<Users size={20} />} label="Unique visitors" value={data.unique_visitors.toLocaleString()} />
              <Kpi icon={<Database size={20} />} label="Event types" value={data.by_event.length} />
              <Kpi
                icon={<BarChart3 size={20} />}
                label="PostHog 7d"
                value={ph?.configured && ph.events_7d != null ? ph.events_7d.toLocaleString() : '—'}
              />
            </div>

            {/* Daily trend */}
            <div className="fintech-card p-4">
              <div className="text-[11px] uppercase tracking-widest text-secondary mb-4">Events / day (14d)</div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={data.daily} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ev" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4ADE80" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#4ADE80" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} width={32} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: 'var(--color-secondary)' }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Area type="monotone" dataKey="count" stroke="#4ADE80" strokeWidth={2} fill="url(#ev)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Top events + pageviews by view */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="fintech-card p-4">
                <div className="text-[11px] uppercase tracking-widest text-secondary mb-4">Top events</div>
                <ResponsiveContainer width="100%" height={Math.max(180, data.by_event.length * 28)}>
                  <BarChart data={data.by_event} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <XAxis type="number" tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <YAxis type="category" dataKey="event" width={140} tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <Bar dataKey="count" fill="#60a5fa" radius={[0, 4, 4, 0]} barSize={16} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="fintech-card p-4">
                <div className="text-[11px] uppercase tracking-widest text-secondary mb-4">Pageviews by section</div>
                {data.by_view.length === 0 ? (
                  <div className="text-secondary text-sm">No pageviews captured yet.</div>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(180, data.by_view.length * 28)}>
                    <BarChart data={data.by_view} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <XAxis type="number" tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                      <YAxis type="category" dataKey="view" width={100} tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                      <Bar dataKey="count" fill="var(--color-accent)" radius={[0, 4, 4, 0]} barSize={16} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* PostHog section */}
            <div className="fintech-card p-4">
              <div className="text-[11px] uppercase tracking-widest text-secondary mb-4">PostHog (last 7 days)</div>
              {!ph?.configured ? (
                <div className="text-secondary text-sm">
                  PostHog API not configured. Set <code className="text-primary">POSTHOG_API_KEY</code> and{' '}
                  <code className="text-primary">POSTHOG_PROJECT_ID</code> as Space secrets to pull aggregates here.
                </div>
              ) : ph.error ? (
                <div className="text-bearish text-sm">{ph.error}</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(ph.top_events ?? []).map((e) => (
                    <span key={e.event} className="px-3 py-1.5 rounded-lg bg-surface-elevated border border-border text-sm text-primary font-mono">
                      {e.event} <span className="text-secondary">· {e.count.toLocaleString()}</span>
                    </span>
                  ))}
                  {(ph.top_events ?? []).length === 0 && <div className="text-secondary text-sm">No events in the last 7 days.</div>}
                </div>
              )}
            </div>

            {/* Recent events */}
            <div className="fintech-card p-4">
              <div className="text-[11px] uppercase tracking-widest text-secondary mb-3">Recent events</div>
              <div className="divide-y divide-border">
                {data.recent.map((r, i) => (
                  <div key={i} className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs sm:text-sm">
                    <span className="font-mono text-primary break-all max-w-[200px]">{r.event}</span>
                    <span className="text-secondary font-medium">{r.view ?? ''}</span>
                    <span className="text-secondary/60 tabular-nums text-xs whitespace-nowrap">{r.ts.replace('T', ' ').slice(0, 19)}</span>
                  </div>
                ))}
                {data.recent.length === 0 && <div className="text-secondary text-sm py-2">No events captured yet.</div>}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ProductAnalytics;
