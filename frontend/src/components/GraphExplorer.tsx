import React, { useEffect, useMemo, useState } from 'react';
import { Share2, ExternalLink, Loader2, X } from 'lucide-react';
import KnowledgeGraph, { type GraphSelection } from './KnowledgeGraph';
import {
  getGraphTriples,
  getGraphAnalytics,
  getGraphEvidence,
  type GraphEvidence,
} from '../api/graph';
import type { Triple } from '../api/chat';

/**
 * Dedicated Knowledge Graph tab. Loads filing-derived triples (optionally
 * filtered to one company), renders the force graph, and shows click-to-source
 * evidence in a side panel so every edge stays auditable back to the filing.
 */
const GraphExplorer: React.FC = () => {
  const [triples, setTriples] = useState<Triple[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [ticker, setTicker] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sel, setSel] = useState<GraphSelection | null>(null);
  const [evidence, setEvidence] = useState<GraphEvidence | null>(null);
  const [evLoading, setEvLoading] = useState(false);

  // Company list for the filter (once).
  useEffect(() => {
    getGraphAnalytics()
      .then((a) => setCompanies(a.per_company.map((c) => c.ticker)))
      .catch(() => setCompanies([]));
  }, []);

  // (Re)load triples whenever the company filter changes.
  useEffect(() => {
    setLoading(true);
    setError(null);
    getGraphTriples(ticker || undefined, 300)
      .then((t) => setTriples(t))
      .catch(() => setError('Could not load the knowledge graph.'))
      .finally(() => setLoading(false));
  }, [ticker]);

  const handleSelect = (s: GraphSelection) => {
    setSel(s);
    setEvidence(null);
    if (!s.chunk_id) return;
    setEvLoading(true);
    getGraphEvidence(s.chunk_id)
      .then((e) => setEvidence(e))
      .catch(() => setEvidence(null))
      .finally(() => setEvLoading(false));
  };

  const edgeCount = triples.length;
  const nodeCount = useMemo(() => {
    const s = new Set<string>();
    triples.forEach((t) => {
      s.add(t.subject);
      s.add(t.object);
    });
    return s.size;
  }, [triples]);

  return (
    <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
      <header className="px-3 md:px-4 lg:px-8 py-3 md:py-4 glass-header z-10 flex-shrink-0 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-base md:text-lg font-semibold text-primary flex items-center gap-2">
            <Share2 className="text-accent" size={18} />
            Knowledge Graph
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            Filing-derived entities and relationships. Click any edge or node to see its source in the filing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted tabular-nums">
            {nodeCount} nodes · {edgeCount} edges
          </span>
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="glass-sm text-xs text-primary bg-transparent px-2.5 py-1.5 rounded-lg outline-none cursor-pointer"
          >
            <option value="">All companies</option>
            {companies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="flex-1 relative bg-background overflow-hidden">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-secondary gap-2 z-20">
            <Loader2 className="animate-spin" size={18} /> Loading graph…
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center text-secondary z-20">
            {error}
          </div>
        )}
        {!loading && !error && triples.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-secondary z-20">
            No triples for this selection yet.
          </div>
        )}
        {!loading && !error && triples.length > 0 && (
          <KnowledgeGraph triples={triples} onSelect={handleSelect} />
        )}

        {/* Evidence side panel — appears on edge/node click. */}
        {sel && (
          <div className="absolute top-3 right-3 bottom-3 w-[340px] max-w-[85vw] fintech-card p-4 overflow-y-auto z-30 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold text-primary leading-snug">{sel.label}</h3>
              <button
                onClick={() => {
                  setSel(null);
                  setEvidence(null);
                }}
                className="text-muted hover:text-primary border-0 bg-transparent cursor-pointer p-0.5"
                aria-label="Close evidence panel"
              >
                <X size={16} />
              </button>
            </div>

            {evLoading && (
              <div className="text-secondary text-xs flex items-center gap-2">
                <Loader2 className="animate-spin" size={14} /> Fetching source…
              </div>
            )}

            {!evLoading && !evidence && (
              <p className="text-xs text-secondary">
                {sel.chunk_id
                  ? 'No source excerpt found for this element.'
                  : 'This element has no linked filing source.'}
              </p>
            )}

            {evidence && (
              <>
                <div className="flex flex-wrap gap-1.5 text-[10px] uppercase tracking-wide">
                  {evidence.ticker && (
                    <span className="px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/30">
                      {evidence.ticker}
                    </span>
                  )}
                  {evidence.form_type && (
                    <span className="px-2 py-0.5 rounded-full bg-surface/40 text-secondary border border-border/40">
                      {evidence.form_type}
                    </span>
                  )}
                  {evidence.section_id && (
                    <span className="px-2 py-0.5 rounded-full bg-surface/40 text-secondary border border-border/40">
                      {evidence.section_id}
                    </span>
                  )}
                </div>
                <p className="text-[13px] text-secondary leading-relaxed whitespace-pre-wrap">
                  {evidence.excerpt.slice(0, 1200)}
                  {evidence.excerpt.length > 1200 ? '…' : ''}
                </p>
                {evidence.edgar_url && (
                  <a
                    href={evidence.edgar_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-accent inline-flex items-center gap-1 hover:underline mt-auto"
                  >
                    View on EDGAR <ExternalLink size={12} />
                  </a>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default GraphExplorer;
