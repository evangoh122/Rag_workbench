import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import type { ToneAnalysis as ToneAnalysisType } from '../api/chat';

interface ToneAnalysisProps {
  tone: ToneAnalysisType;
}

function DirectionBadge({ direction, label }: { direction: string; label?: string }) {
  if (direction === 'up') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/25">
        <TrendingUp size={12} />
        {label || 'More Cautious'}
      </span>
    );
  }
  if (direction === 'down') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-bullish/15 text-emerald-400 border border-bullish/25">
        <TrendingDown size={12} />
        {label || 'More Optimistic'}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-500/15 text-gray-400 border border-gray-500/25">
      <Minus size={12} />
      {label || 'Consistent'}
    </span>
  );
}

function formatPctChange(pct: number | null | undefined): string {
  if (pct == null) return '';
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(0)}%`;
}

function PctBadge({ pct, type }: { pct: number | null | undefined; type: 'positive' | 'negative' | 'uncertainty' }) {
  if (pct == null) return null;
  const isUp = pct > 0;
  const isDown = pct < 0;

  let colorClass = 'text-muted';
  if (type === 'positive') {
    colorClass = isUp ? 'text-emerald-400' : isDown ? 'text-amber-400' : 'text-muted';
  } else if (type === 'negative') {
    colorClass = isUp ? 'text-amber-400' : isDown ? 'text-emerald-400' : 'text-muted';
  } else {
    colorClass = isUp ? 'text-amber-400' : isDown ? 'text-emerald-400' : 'text-muted';
  }

  return (
    <span className={`text-[11px] font-mono ${colorClass}`}>
      ({formatPctChange(pct)})
    </span>
  );
}

export default function ToneAnalysis({ tone }: ToneAnalysisProps) {
  const {
    tone_label,
    tone_direction,
    tone_summary,
    key_drivers,
    positive_terms,
    negative_terms,
    uncertainty_terms,
    positive_change_pct,
    negative_change_pct,
    uncertainty_change_pct,
    tone_shift_similarity,
    tone_shift_interpretation,
  } = tone;

  return (
    <div className="glass-sm p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <AlertTriangle size={14} className="text-amber-400" />
        <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">
          Management Tone
        </span>
        <DirectionBadge direction={tone_direction} label={tone_label} />
      </div>

      {/* Term counts */}
      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col">
          <span className="text-[10px] text-muted uppercase tracking-wider font-medium">Positive</span>
          <span className="text-sm font-semibold text-emerald-400 tabular-nums">
            {positive_terms ?? '—'}
            <PctBadge pct={positive_change_pct} type="positive" />
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted uppercase tracking-wider font-medium">Negative</span>
          <span className="text-sm font-semibold text-amber-400 tabular-nums">
            {negative_terms ?? '—'}
            <PctBadge pct={negative_change_pct} type="negative" />
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-muted uppercase tracking-wider font-medium">Uncertainty</span>
          <span className="text-sm font-semibold text-gray-400 tabular-nums">
            {uncertainty_terms ?? '—'}
            <PctBadge pct={uncertainty_change_pct} type="uncertainty" />
          </span>
        </div>
      </div>

      {/* Summary */}
      {tone_summary && (
        <p className="text-[13px] text-secondary leading-relaxed m-0">
          {tone_summary}
        </p>
      )}

      {/* Key Drivers */}
      {key_drivers && key_drivers.length > 0 && (
        <div>
          <span className="text-[10px] font-semibold text-muted uppercase tracking-wider">
            Key Drivers
          </span>
          <ul className="mt-1 space-y-1 pl-0 list-none">
            {key_drivers.map((driver, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-secondary leading-relaxed">
                <span className="text-accent mt-0.5 flex-shrink-0">&#8226;</span>
                {driver}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Tone Shift (Phase D — embedding-based) */}
      {tone_shift_similarity != null && (
        <div className="flex items-center gap-2 text-[12px] text-secondary pt-1 border-t border-border/30">
          <span className="text-muted">Tone shift score:</span>
          <span className={`font-mono font-semibold ${
            tone_shift_similarity > 0.95 ? 'text-emerald-400' :
            tone_shift_similarity > 0.85 ? 'text-amber-400' :
            'text-red-400'
          }`}>
            {tone_shift_similarity.toFixed(2)}
          </span>
          {tone_shift_interpretation && (
            <span className="text-muted italic">({tone_shift_interpretation})</span>
          )}
        </div>
      )}
    </div>
  );
}
