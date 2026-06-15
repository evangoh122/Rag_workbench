import React, { useEffect, useState } from 'react';
import { BarChart3, X } from 'lucide-react';
import { getGraphAnalytics, type GraphAnalytics as Analytics } from '../api/graph';

// Node-type colours mirror KnowledgeGraph's TYPE_COLORS so the legend matches.
const TYPE_COLORS: Record<string, string> = {
  Company: '#1D4ED8',
  Segment: '#0891b2',
  Risk: '#dc2626',
  Executive: '#d97706',
  Metric: '#7c3aed',
  XBRL: '#059669',
  Product: '#db2777',
  Geography: '#4b5563',
};

const Stat: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="flex flex-col">
    <span className="text-lg font-semibold tabular-nums text-primary">
      {value.toLocaleString()}
    </span>
    <span className="text-[10px] uppercase tracking-wide text-secondary">{label}</span>
  </div>
);

const Bar: React.FC<{ label: string; count: number; max: number; color?: string; suffix?: string }> = ({
  label, count, max, color = 'var(--color-accent, #2E8B57)', suffix,
}) => (
  <div className="flex items-center gap-2 text-xs">
    <span className="w-28 shrink-0 truncate text-secondary" title={label}>{label}</span>
    <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
      <div
        className="h-full rounded-full"
        style={{ width: `${Math.max(4, (count / max) * 100)}%`, background: color }}
      />
    </div>
    <span className="w-14 shrink-0 text-right tabular-nums text-primary">
      {count}{suffix ?? ''}
    </span>
  </div>
);

/** Collapsible analytics overlay for the knowledge-graph view. Fetches
 *  graph-wide aggregates (relation/entity types, per-company coverage). */
const GraphAnalytics: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!open || data || loading) return;
    setLoading(true);
    getGraphAnalytics()
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [open, data, loading]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="absolute top-3 right-3 z-10 flex items-center gap-1.5 glass-button px-3 py-1.5 text-xs font-medium text-primary"
      >
        <BarChart3 size={14} className="text-accent" />
        Analytics
      </button>
    );
  }

  const relMax = data ? Math.max(...data.relations.map((r) => r.count), 1) : 1;
  const entMax = data ? Math.max(...data.entity_types.map((e) => e.count), 1) : 1;
  const coMax = data ? Math.max(...data.per_company.map((c) => c.triples), 1) : 1;

  return (
    <div className="absolute top-3 right-3 z-10 w-80 max-h-[calc(100%-1.5rem)] overflow-y-auto glass-modal p-4 text-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <BarChart3 size={16} className="text-accent" />
          <h3 className="font-semibold text-primary">Graph Analytics</h3>
        </div>
        <button onClick={() => setOpen(false)} className="text-secondary hover:text-primary">
          <X size={16} />
        </button>
      </div>

      {loading && <p className="text-secondary text-xs">Loading…</p>}
      {error && <p className="text-bearish text-xs">Couldn’t load analytics.</p>}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Triples" value={data.totals.triples} />
            <Stat label="Companies" value={data.totals.companies} />
            <Stat label="Relations" value={data.totals.relation_types} />
            <Stat label="Entities" value={data.totals.entities} />
            <Stat label="XBRL-linked" value={data.totals.xbrl_linked} />
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wide text-secondary mb-2">Relationship types</h4>
            <div className="space-y-1.5">
              {data.relations.map((r) => (
                <Bar key={r.predicate} label={r.predicate} count={r.count} max={relMax} />
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wide text-secondary mb-2">Entity types</h4>
            <div className="space-y-1.5">
              {data.entity_types.map((e) => (
                <Bar
                  key={e.type}
                  label={e.type}
                  count={e.count}
                  max={entMax}
                  color={TYPE_COLORS[e.type] ?? '#4b5563'}
                />
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wide text-secondary mb-2">Per-company coverage</h4>
            <div className="space-y-1.5">
              {data.per_company.map((c) => (
                <Bar key={c.ticker} label={c.ticker} count={c.triples} max={coMax} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphAnalytics;
