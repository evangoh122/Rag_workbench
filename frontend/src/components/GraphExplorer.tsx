import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { Share2, ExternalLink, Loader2, X, Check, Search } from 'lucide-react';
import KnowledgeGraph, { type GraphSelection } from './KnowledgeGraph';
import {
  getGraphTriples,
  getGraphAnalytics,
  getGraphEvidence,
  type GraphEvidence,
} from '../api/graph';
import type { Triple } from '../api/chat';

export const COMPANY_NAMES: Record<string, string> = {
  SPCX: 'SpaceX',
  MU: 'Micron Technology',
  NVDA: 'NVIDIA',
  AMD: 'Advanced Micro Devices',
  INTC: 'Intel',
  AVGO: 'Broadcom',
  QCOM: 'Qualcomm',
  TXN: 'Texas Instruments',
  ADI: 'Analog Devices',
  MRVL: 'Marvell Technology',
  ON: 'ON Semiconductor',
  MCHP: 'Microchip Technology',
  STM: 'STMicroelectronics',
  AMAT: 'Applied Materials',
  LRCX: 'Lam Research',
  KLAC: 'KLA Corporation',
};

/**
 * Dedicated Knowledge Graph tab. Loads filing-derived triples (optionally
 * filtered to selected companies), renders the force graph, and shows
 * click-to-source evidence in a side panel (desktop) or bottom sheet (mobile).
 */
const GraphExplorer: React.FC = () => {
  const [triples, setTriples] = useState<Triple[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<string[]>(['MU']);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sel, setSel] = useState<GraphSelection | null>(null);
  const [evidence, setEvidence] = useState<GraphEvidence | null>(null);
  const [evLoading, setEvLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Company list for the filter (once).
  useEffect(() => {
    getGraphAnalytics()
      .then((a) => setCompanies(a.per_company.map((c) => c.ticker)))
      .catch(() => setCompanies([]));
  }, []);

  // Close dropdown on outside click.
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
        setSearchQuery('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [dropdownOpen]);

  // (Re)load triples whenever the company filter changes.
  useEffect(() => {
    setLoading(true);
    setError(null);

    if (selectedTickers.length === 0) {
      getGraphTriples(undefined, 200)
        .then((t) => setTriples(t))
        .catch(() => setError('Could not load the knowledge graph.'))
        .finally(() => setLoading(false));
    } else if (selectedTickers.length === 1) {
      getGraphTriples(selectedTickers[0], 150)
        .then((t) => setTriples(t))
        .catch(() => setError('Could not load the knowledge graph.'))
        .finally(() => setLoading(false));
    } else {
      getGraphTriples(undefined, 500)
        .then((all) => {
          const set = new Set(selectedTickers);
          setTriples(all.filter((t) => t.ticker && set.has(t.ticker)));
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

  const filteredCompanies = useMemo(() => {
    if (!searchQuery.trim()) return companies;
    const q = searchQuery.toLowerCase();
    return companies.filter(
      (c) =>
        c.toLowerCase().includes(q) ||
        (COMPANY_NAMES[c] ?? '').toLowerCase().includes(q)
    );
  }, [companies, searchQuery]);

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

          {/* Multi-select dropdown with search */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => {
                setDropdownOpen(!dropdownOpen);
                setSearchQuery('');
              }}
              className="glass-sm text-xs text-primary bg-transparent px-2.5 py-2 md:py-1.5 rounded-lg outline-none cursor-pointer flex items-center gap-1.5 min-h-[44px] md:min-h-0"
            >
              {filterLabel}
              <span className="text-[10px] text-muted">{dropdownOpen ? '\u25B2' : '\u25BC'}</span>
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-1 w-64 md:w-72 fintech-card p-2 z-50 shadow-lg max-h-80 flex flex-col">
                {/* Search input */}
                <div className="relative mb-2">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
                  <input
                    type="text"
                    autoFocus
                    placeholder="Search companies..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-surface-elevated border border-border rounded-md pl-8 pr-3 py-2 text-xs text-primary placeholder-secondary outline-none focus:border-accent/40"
                  />
                </div>

                {/* All companies option */}
                <button
                  onClick={selectAll}
                  className={`w-full text-left text-xs px-2.5 py-2 md:py-1.5 rounded flex items-center gap-2 hover:bg-surface/60 min-h-[40px] md:min-h-0 ${
                    selectedTickers.length === 0 ? 'text-accent' : 'text-primary'
                  }`}
                >
                  <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                    {selectedTickers.length === 0 && <Check size={12} />}
                  </span>
                  All companies
                </button>

                <div className="border-t border-border/30 my-1" />

                {/* Individual tickers with names */}
                <div className="overflow-y-auto max-h-52 flex-1">
                  {filteredCompanies.length === 0 && (
                    <p className="text-xs text-muted px-2.5 py-3 text-center">No matches</p>
                  )}
                  {filteredCompanies.map((c) => (
                    <button
                      key={c}
                      onClick={() => toggleTicker(c)}
                      className={`w-full text-left text-xs px-2.5 py-2 md:py-1.5 rounded flex items-center gap-2 hover:bg-surface/60 min-h-[40px] md:min-h-0 ${
                        selectedTickers.includes(c) ? 'text-accent' : 'text-primary'
                      }`}
                    >
                      <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                        {selectedTickers.includes(c) && <Check size={12} />}
                      </span>
                      <span className="font-mono font-semibold w-12 flex-shrink-0">{c}</span>
                      <span className="text-secondary truncate">{COMPANY_NAMES[c] ?? c}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex-1 relative bg-background overflow-hidden" style={{ minHeight: 0 }}>
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

        {/* Evidence panel — side panel on md+, bottom sheet on mobile */}
        {sel && (
          <>
            {/* Desktop side panel (md+) */}
            <div className="hidden md:flex absolute top-3 right-3 bottom-3 w-[340px] fintech-card p-4 overflow-y-auto z-30 flex-col gap-3">
              <EvidenceContent
                sel={sel}
                evidence={evidence}
                evLoading={evLoading}
                onClose={() => { setSel(null); setEvidence(null); }}
              />
            </div>

            {/* Mobile bottom sheet */}
            <div className="md:hidden fixed inset-x-0 bottom-0 z-50 fintech-card p-4 pb-6 max-h-[60vh] overflow-y-auto rounded-t-2xl border-t border-accent/20 shadow-2xl">
              {/* Drag handle */}
              <div className="flex justify-center mb-3">
                <div className="w-10 h-1 rounded-full bg-border" />
              </div>
              <EvidenceContent
                sel={sel}
                evidence={evidence}
                evLoading={evLoading}
                onClose={() => { setSel(null); setEvidence(null); }}
              />
            </div>
            {/* Backdrop for mobile bottom sheet */}
            <div
              className="md:hidden fixed inset-0 bg-black/50 z-40"
              onClick={() => { setSel(null); setEvidence(null); }}
            />
          </>
        )}
      </div>
    </div>
  );
};

/** Shared evidence content used by both desktop panel and mobile bottom sheet. */
function EvidenceContent({
  sel,
  evidence,
  evLoading,
  onClose,
}: {
  sel: GraphSelection;
  evidence: GraphEvidence | null;
  evLoading: boolean;
  onClose: () => void;
}) {
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-primary leading-snug">{sel.label}</h3>
        <button
          onClick={onClose}
          className="text-muted hover:text-primary border-0 bg-transparent cursor-pointer p-1 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:p-0.5 flex items-center justify-center"
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
    </>
  );
}

export default GraphExplorer;
