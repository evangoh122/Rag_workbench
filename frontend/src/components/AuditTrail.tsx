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
    <div className="mt-2 border border-[#2a3246] rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 bg-[#161b22] text-sm font-medium text-gray-300 hover:bg-[#1c2130] transition-colors cursor-pointer border-0"
        onClick={() => setOpen(prev => !prev)}
      >
        <span className="flex items-center gap-2">{title}{count != null ? <span className="text-xs text-gray-500">({count})</span> : null}</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="px-3 py-3 bg-[#0d1117]">
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
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-900 text-green-300 border border-green-700">
        &#x2713; Verified ({verification.reasoning})
      </span>
    );
  }

  if (status === 'mismatch' || status === 'FAIL') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-900 text-red-300 border border-red-700">
        &#x2717; Verification Failed — {verification.reasoning}
      </span>
    );
  }

  if (status === 'unverifiable' || status === 'ERROR') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-800 text-gray-400 border border-gray-600">
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

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-[#131926] border border-[#2a3246] rounded-md">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-300 font-medium truncate">{fact.label || fact.concept}</span>
          {fact.is_verified && (
            <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] text-green-400">
              <CheckCircle size={10} /> verified
            </span>
          )}
        </div>
        {fact.period && (
          <div className="text-[10px] text-gray-500 mt-0.5">{fact.period}</div>
        )}
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm font-mono text-green-400 tabular-nums">{fmt(fact.value)}</div>
        <div className="text-[10px] text-gray-500">{fact.unit || ''}</div>
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
                      className="text-left px-2 py-2 text-gray-400 font-medium border-b border-[#2a3246]"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {polygon_data!.map((poly, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? '' : 'bg-[#0a0c10]'}>
                    <td className="px-2 py-1.5 font-mono text-blue-300 border-b border-[#1a1f2e]">{poly.ticker}</td>
                    <td className="px-2 py-1.5 text-gray-300 border-b border-[#1a1f2e]">{poly.name}</td>
                    <td className="px-2 py-1.5 text-green-400 border-b border-[#1a1f2e]">
                      {poly.last_price ? `$${poly.last_price.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-2 py-1.5 text-gray-400 border-b border-[#1a1f2e]">{poly.price_date || 'N/A'}</td>
                    <td className="px-2 py-1.5 text-gray-400 border-b border-[#1a1f2e]">
                      {poly.volume ? poly.volume.toLocaleString() : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {polygon_data![0].description && (
              <div className="mt-3 p-2 bg-[#161b22] rounded border border-[#2a3246]">
                <p className="text-[10px] uppercase text-gray-500 font-bold mb-1">Company Description</p>
                <p className="text-gray-400 text-xs leading-relaxed italic">
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
              <div key={idx} className="border border-[#2a3246] rounded-md p-3 bg-[#131926]">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="px-1.5 py-0.5 rounded text-xs font-mono bg-[#1c2130] text-blue-300 border border-blue-900">
                    {src.section}
                  </span>
                  <span className="px-1.5 py-0.5 rounded-full text-xs font-semibold bg-blue-900 text-blue-200">
                    {src.ticker}
                  </span>
                  <span className="text-xs text-gray-500">{src.accession}</span>
                  {src.distance != null && (
                    <span className="text-xs text-gray-600 ml-auto">dist: {src.distance.toFixed(4)}</span>
                  )}
                </div>
                <p className="text-gray-400 text-xs leading-relaxed mb-2 line-clamp-3">
                  {src.text.slice(0, 200)}{src.text.length > 200 ? '…' : ''}
                </p>
                <a
                  href={src.edgar_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  View on EDGAR <ExternalLink size={10} />
                </a>
              </div>
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
                  {['Concept', 'Label', 'Value', 'Unit', 'Period'].map(col => (
                    <th
                      key={col}
                      className="text-left px-2 py-2 text-gray-400 font-medium border-b border-[#2a3246]"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {xbrl_facts!.map((fact, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? '' : 'bg-[#0a0c10]'}>
                    <td className="px-2 py-1.5 font-mono text-blue-300 border-b border-[#1a1f2e]">{fact.concept}</td>
                    <td className="px-2 py-1.5 text-gray-300 border-b border-[#1a1f2e]">{fact.label}</td>
                    <td className="px-2 py-1.5 text-gray-100 border-b border-[#1a1f2e]">
                      {fact.value != null ? fact.value.toLocaleString() : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-gray-400 border-b border-[#1a1f2e]">{fact.unit}</td>
                    <td className="px-2 py-1.5 text-gray-400 border-b border-[#1a1f2e]">{fact.period}</td>
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
              <li key={idx} className="text-gray-300 font-mono text-xs leading-relaxed">
                {step}
              </li>
            ))}
          </ol>
        </CollapsibleSection>
      )}
    </div>
  );
}
