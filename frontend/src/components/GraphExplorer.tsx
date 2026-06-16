import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Share2, ExternalLink, Loader2, X, Check } from 'lucide-react';
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
 * filtered to selected companies), renders the force graph, and shows
 * click-to-source evidence in a side panel so every edge stays auditable.
 */
const GraphExplorer: React.FC = () => {
  const [triples, setTriples] = useState<Triple[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<string[]>(['MU']);
  const [dropdownOpen, setDropdownOpen] = useState(false);
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

    if (selectedTickers.length === 0) {
      // No selection = all companies
      getGraphTriples(undefined, 300)
        .then((t) => setTriples(t))
        .catch(() => setError('Could not load the knowledge graph.'))
        .finally(() => setLoading(false));
    } else if (selectedTickers.length === 1) {
      // Single company — use the API filter
      getGraphTriples(selectedTickers[0], 300)
        .then((t) => setTriples(t))
        .catch(() => setError('Could not load the knowledge graph.'))
        .finally(() => setLoading(false));
    } else {
      // Multiple companies — fetch all and filter client-side
      getGraphTriples(undefined, 1000)
        .then((all) => {
          const set = new Set(selectedTickers);
          setTriples(all.filter((t) => set.has(t.ticker)));
        })
        .catch(() => setError('Could not load the knowledge graph.'))
        .finally(() => setLoading(false));
    }
  }, [selectedTickers]);

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

  const toggleTicker = useCallback((t: string) => {
    setSelectedTickers((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    );
  }, []);

  const selectAll = useCallback(() => {
    setSelectedTickers([]);
  }, []);

  const edgeCount = triples.length;
  const nodeCount = useMemo(() => {
    const s = new Set<string>();
    triples.forEach((t) => {
      s.add(t.subject);
      s.add(t.object);
    });
    return s.size;
  }, [triples]);

  const filterLabel =
    selectedTickers.length === 0
      ? 'All companies'
      : selectedTickers.length === 1
        ? selectedTickers[0]
        : `${selectedTickers.length} companies`;

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

          {/* Multi-select dropdown */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              onBlur={() => setTimeout(() => setDropdownOpen(false), 200)}
              className="glass-sm text-xs text-primary bg-transparent px-2.5 py-1.5 rounded-lg outline-none cursor-pointer flex items-center gap-1.5"
            >
              {filterLabel}
              <span className="text-[10px] text-muted">{dropdownOpen ? '\u25B2' : '\u25BC'}</span>
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 fintech-card p-1.5 z-50 shadow-lg max-h-64 overflow-y-auto">
                {/* All companies option */}
                <button
                  onClick={selectAll}
                  className={`w-full text-left text-xs px-2 py-1.5 rounded flex items-center gap-2 hover:bg-surface/60 ${
                    selectedTickers.length === 0 ? 'text-accent' : 'text-primary'
                  }`}
                >
                  <span className="w-3.5 h-3.5 flex items-center justify-center">
                    {selectedTickers.length === 0 && <Check size={12} />}
                  </span>
                  All companies
                </button>

                <div className="border-t border-border/30 my-1" />

                {/* Individual tickers */}
                {companies.map((c) => (
                  <button
                    key={c}
                    onClick={() => toggleTicker(c)}
                    className={`w-full text-left text-xs px-2 py-1.5 rounded flex items-center gap-2 hover:bg-surface/60 ${
                      selectedTickers.includes(c) ? 'text-accent' : 'text-primary'
                    }`}
                  >
                    <span className="w-3.5 h-3.5 flex items-center justify-center">
                      {selectedTickers.includes(c) && <Check size={12} />}
                    </span>
                    {c}
                  </button>
                ))}
              </div>
            )}
          </div>
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
