import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink, CheckCircle, Database } from 'lucide-react';
import type { Source, XBRLFact, PolygonData } from '../api/chat';

interface VerificationResult {
  status: string;
  reasoning: string;
}

interface AuditTrailProps {
  sources?: Source[];
  xbrl_facts?: XBRLFact[];
  relevant_xbrl?: XBRLFact[];
  xbrl_badge?: string;
  xbrl_group?: string;
  polygon_data?: PolygonData[];
  verification?: VerificationResult;
  math_steps?: string[];
}

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  count?: number;
}

function CollapsibleSection({ title, children, defaultOpen = false, count }: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="mt-2 border border-border rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 bg-surface-elevated text-sm font-medium text-secondary hover:bg-surface transition-colors cursor-pointer border-0"
        onClick={() => setOpen(prev => !prev)}
      >
        <span className="flex items-center gap-2">{title}{count != null ? <span className="text-xs text-secondary/40 tabular-nums">({count})</span> : null}</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="px-3 py-3 bg-background">
          {children}
        </div>
      )}
    </div>
  );
}

function VerificationBadge({ verification }: { verification: VerificationResult }) {
  const status = verification.status;
  if (!status || status === 'not_checked') return null;

  if (status === 'verified' || status === 'PASS') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-bullish/10 text-bullish border border-bullish/20">
        &#x2713; Verified ({verification.reasoning})
      </span>
    );
  }

  if (status === 'mismatch' || status === 'FAIL') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-bearish/10 text-bearish border border-bearish/20">
        &#x2717; Verification Failed — {verification.reasoning}
      </span>
    );
  }

  if (status === 'unverifiable' || status === 'ERROR') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-surface-elevated text-secondary border border-border">
        Unverifiable
      </span>
    );
  }

  return null;
}

function XBRLFactCard({ fact }: { fact: XBRLFact }) {
  const fmt = (v: unknown) => {
    if (v == null || typeof v !== 'number') return '—';
    if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
    if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toFixed(2);
  };

  const hasProvenance = Boolean(fact.accession || fact.raw_fact_url || fact.filing_url);

  return (
    <div className="px-3 py-2 bg-surface border border-border rounded-md">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-primary font-medium truncate">{fact.label || fact.concept}</span>
            {fact.is_verified && (
              <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] text-bullish">
                <CheckCircle size={10} /> SEC XBRL
              </span>
            )}
          </div>
          {fact.period && <div className="text-[10px] text-secondary/60 mt-0.5 tabular-nums">{fact.period}</div>}
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-mono text-bullish tabular-nums">{fmt(fact.value)}</div>
          <div className="text-[10px] text-secondary/40">{fact.unit || ''}</div>
        </div>
      </div>
      {hasProvenance && (
        <details className="mt-2 border-t border-border/60 pt-2">
          <summary className="cursor-pointer text-[11px] text-blue-400 hover:text-blue-300 select-none">Inspect exact raw data point</summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 mt-2 text-[10px]">
            <dt className="text-secondary/50">Tag</dt><dd className="font-mono text-secondary break-all">{fact.taxonomy || 'us-gaap'}:{fact.concept}</dd>
            <dt className="text-secondary/50">Raw value</dt><dd className="font-mono text-primary break-all tabular-nums">{String(fact.value)} {fact.unit}</dd>
            <dt className="text-secondary/50">Period</dt><dd className="font-mono text-secondary tabular-nums">{fact.period_start ? `${fact.period_start} → ` : ''}{fact.period_end || fact.period}</dd>
            {fact.accession && <><dt className="text-secondary/50">Accession</dt><dd className="font-mono text-secondary break-all">{fact.accession}</dd></>}
            {fact.form_type && <><dt className="text-secondary/50">Filed as</dt><dd className="text-secondary">{fact.form_type}{fact.filed ? ` on ${fact.filed}` : ''}</dd></>}
            {fact.frame && <><dt className="text-secondary/50">SEC frame</dt><dd className="font-mono text-secondary">{fact.frame}</dd></>}
          </dl>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
            {fact.raw_fact_url && <a href={fact.raw_fact_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300">SEC concept JSON <ExternalLink size={10} /></a>}
            {fact.raw_frame_url && <a href={fact.raw_frame_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300">SEC frame JSON <ExternalLink size={10} /></a>}
            {fact.filing_url && <a href={fact.filing_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300">Reporting filing <ExternalLink size={10} /></a>}
          </div>
          <p className="mt-1.5 text-[10px] text-secondary/50">In SEC JSON, match this card’s accession, period, unit, and raw value.</p>
        </details>
      )}
    </div>
  );
}

function SourceCard({ src }: { src: Source }) {
  const [expanded, setExpanded] = useState(false);
  const excerptId = React.useId();
  return (
    <div className="border border-border rounded-md p-3 bg-surface">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span className="px-1.5 py-0.5 rounded text-xs font-mono bg-surface-elevated text-blue-300 border border-blue-900/30">{src.section}</span>
        <span className="px-1.5 py-0.5 rounded-full text-xs font-semibold bg-blue-900/30 text-blue-200">{src.ticker}</span>
        <span className="text-xs text-secondary/40 tabular-nums">{src.accession}</span>
        {src.distance != null && <span className="text-xs text-secondary/30 ml-auto tabular-nums">dist: {src.distance.toFixed(4)}</span>}
      </div>
      <div className="text-[10px] text-secondary/50 mb-2 flex flex-wrap gap-x-3 gap-y-0.5">
        {src.form_type && <span>{src.form_type}</span>}
        {src.period_of_report && <span>Period {src.period_of_report}</span>}
        {src.chunk_index != null && <span className="font-mono">Retrieved chunk #{src.chunk_index}</span>}
      </div>
      <p id={excerptId} className={`text-secondary text-xs leading-relaxed whitespace-pre-wrap ${expanded ? '' : 'line-clamp-3'}`}>
        {expanded ? src.text : src.text.slice(0, 200)}{!expanded && src.text.length > 200 ? '…' : ''}
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2">
        {src.text.length > 200 && <button type="button" aria-expanded={expanded} aria-controls={excerptId} onClick={() => setExpanded(value => !value)} className="text-xs text-blue-400 hover:text-blue-300 bg-transparent border-0 p-0 cursor-pointer">{expanded ? 'Collapse raw excerpt' : 'Show full retrieved excerpt'}</button>}
        <a href={src.edgar_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">Open reporting filing <ExternalLink size={10} /></a>
      </div>
    </div>
  );
}

export default function AuditTrail({ sources, xbrl_facts, relevant_xbrl, xbrl_badge, xbrl_group, polygon_data, verification, math_steps }: AuditTrailProps) {
  const hasSources = sources && sources.length > 0;
  const hasRelevant = relevant_xbrl && relevant_xbrl.length > 0;
  const hasXBRL = xbrl_facts && xbrl_facts.length > 0;
  const hasPolygon = polygon_data && polygon_data.length > 0;
  const hasMath = math_steps && math_steps.length > 0;
  const hasVerification = verification && verification.status !== 'not_checked';

  if (!hasSources && !hasXBRL && !hasRelevant && !hasPolygon && !hasMath && !hasVerification) return null;

  return (
    <div className="mt-3 text-sm">
      {/* Verification badge — always visible */}
      {verification && (
        <div className="mb-2">
          <VerificationBadge verification={verification} />
        </div>
      )}

      {/* XBRL Verified Badge */}
      {hasRelevant && xbrl_badge && (
        <div className="mb-2 flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-950 text-green-300 border border-green-800">
            <Database size={12} />
            {xbrl_badge}
          </span>
          {xbrl_group && xbrl_group !== 'none' && (
            <span className="text-[10px] uppercase text-gray-500 tracking-wide">{xbrl_group}</span>
          )}
        </div>
      )}

      {/* Relevant XBRL Facts — compact cards, always visible */}
      {hasRelevant && (
        <div className="mb-3">
          <div className="flex flex-col gap-1.5">
            {relevant_xbrl!.map((fact, idx) => (
              <XBRLFactCard key={idx} fact={fact} />
            ))}
          </div>
        </div>
      )}

      {/* Polygon Market Data section */}
      {hasPolygon && (
        <CollapsibleSection title="Polygon Market Data" defaultOpen={true}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  {['Ticker', 'Name', 'Price', 'Date', 'Volume'].map(col => (
                    <th
                      key={col}
                      className="text-left px-2 py-2 text-secondary font-medium border-b border-border"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {polygon_data!.map((poly, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? '' : 'bg-background'}>
                    <td className="px-2 py-1.5 font-mono text-blue-300 border-b border-border/40 tabular-nums">{poly.ticker}</td>
                    <td className="px-2 py-1.5 text-secondary border-b border-border/40">{poly.name}</td>
                    <td className="px-2 py-1.5 text-bullish border-b border-border/40 tabular-nums">
                      {poly.last_price ? `$${poly.last_price.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-2 py-1.5 text-secondary/60 border-b border-border/40 tabular-nums">{poly.price_date || 'N/A'}</td>
                    <td className="px-2 py-1.5 text-secondary/60 border-b border-border/40 tabular-nums">
                      {poly.volume ? poly.volume.toLocaleString() : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {polygon_data![0].description && (
              <div className="mt-3 p-2 bg-surface-elevated rounded border border-border">
                <p className="text-[10px] uppercase text-secondary/60 font-bold mb-1">Company Description</p>
                <p className="text-secondary text-xs leading-relaxed italic">
                  "{polygon_data![0].description}"
                </p>
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Sources section */}
      {hasSources && (
        <CollapsibleSection title="Sources" count={sources!.length}>
          <div className="flex flex-col gap-3">
            {sources!.map((src, idx) => (
              <SourceCard key={`${src.accession}-${src.chunk_index ?? idx}`} src={src} />
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Full XBRL Facts — collapsed by default */}
      {hasXBRL && (
        <CollapsibleSection title="All XBRL Facts" count={xbrl_facts!.length} defaultOpen={!hasRelevant}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  {['Concept', 'Label', 'Value', 'Unit', 'Period', 'Raw source'].map(col => (
                    <th
                      key={col}
                      className="text-left px-2 py-2 text-secondary font-medium border-b border-border"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {xbrl_facts!.map((fact, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? '' : 'bg-background'}>
                    <td className="px-2 py-1.5 font-mono text-blue-300 border-b border-border/40 tabular-nums">{fact.concept}</td>
                    <td className="px-2 py-1.5 text-secondary border-b border-border/40">{fact.label}</td>
                    <td className="px-2 py-1.5 text-primary border-b border-border/40 tabular-nums">
                      {fact.value != null ? fact.value.toLocaleString() : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-secondary/60 border-b border-border/40">{fact.unit}</td>
                    <td className="px-2 py-1.5 text-secondary/60 border-b border-border/40 tabular-nums">{fact.period}</td>
                    <td className="px-2 py-1.5 border-b border-border/40 whitespace-nowrap">
                      {fact.raw_fact_url ? (
                        <a
                          href={fact.raw_fact_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={fact.accession ? `SEC accession ${fact.accession}` : 'Open raw SEC XBRL fact'}
                          className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300"
                        >
                          SEC JSON <ExternalLink size={9} />
                        </a>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleSection>
      )}

      {/* Math steps section */}
      {hasMath && (
        <CollapsibleSection title="Math Steps">
          <ol className="list-decimal list-inside space-y-1">
            {math_steps!.map((step, idx) => (
              <li key={idx} className="text-secondary font-mono text-xs leading-relaxed tabular-nums">
                {step}
              </li>
            ))}
          </ol>
        </CollapsibleSection>
      )}
    </div>
  );
}
