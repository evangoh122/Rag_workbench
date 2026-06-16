import { useState, useEffect, useCallback } from 'react';
import { Activity, AlertTriangle, CheckCircle } from 'lucide-react';
import { getDriftStatus } from '../api/review';
import type { DriftStatus } from '../api/review';

const _parsedFloor = parseFloat(import.meta.env.VITE_DRIFT_AGREEMENT_FLOOR ?? '0.95');
const AGREEMENT_FLOOR = isNaN(_parsedFloor) ? 0.95 : _parsedFloor;
const _parsedThreshold = parseInt(import.meta.env.VITE_DRIFT_CONCEPT_SPIKE_THRESHOLD ?? '50', 10);
const CONCEPT_SPIKE_THRESHOLD = isNaN(_parsedThreshold) ? 50 : _parsedThreshold;

export default function DriftAlert() {
  const [status, setStatus] = useState<DriftStatus | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getDriftStatus();
      setStatus(data);
      setUnavailable(false);
      setConsecutiveFailures(0);
    } catch (err) {
      console.error('Failed to fetch drift status:', err);
      setUnavailable(true);
      setConsecutiveFailures((prev) => prev + 1);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (consecutiveFailures >= 3) return;

    const delay = Math.max(60_000, 60_000 * Math.pow(2, consecutiveFailures));
    const intervalId = setInterval(() => {
      void fetchStatus();
    }, delay);

    return () => clearInterval(intervalId);
  }, [fetchStatus, consecutiveFailures]);

  if (unavailable) {
    return (
      <div className="mt-auto px-3 py-3 rounded-lg bg-surface-elevated border border-border">
        <div className="flex items-center gap-2 text-xs text-secondary/60">
          <Activity size={12} />
          <span>Status unavailable</span>
        </div>
      </div>
    );
  }

  if (status === null) {
    return (
      <div className="mt-auto px-3 py-3 rounded-lg bg-surface-elevated border border-border animate-pulse">
        <div className="h-3 w-3/4 bg-border rounded mb-2" />
        <div className="h-3 w-2/3 bg-border rounded" />
      </div>
    );
  }

  const agreementPct = Math.round(
    (status.agreement_rate ?? AGREEMENT_FLOOR) * 100,
  );
  const floorPct = Math.round(
    (status.agreement_floor ?? AGREEMENT_FLOOR) * 100,
  );
  const conceptCount = status.unrecognized_concept_count ?? 0;
  const conceptThreshold =
    status.concept_spike_threshold ?? CONCEPT_SPIKE_THRESHOLD;

  const hasAlert = status.agreement_alert || status.concept_alert;

  return (
    <div
      className={`mt-auto px-3 py-3 rounded-lg border text-xs transition-colors duration-300 ${
        hasAlert
          ? 'bg-bearish/10 border-bearish/30'
          : 'bg-surface-elevated border-border'
      }`}
    >
      <div className="flex items-center gap-1.5 mb-2 font-semibold text-secondary">
        <Activity size={12} className={hasAlert ? 'text-bearish' : 'text-secondary/60'} />
        <span>Pipeline Monitor</span>
      </div>

      {/* Agreement rate row */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-secondary/60">Agreement</span>
        <div className="flex items-center gap-1.5 tabular-nums">
          <span
            className={
              status.agreement_alert ? 'text-bearish font-semibold animate-pulse' : 'text-bullish'
            }
          >
            {agreementPct}%
          </span>
          <span className="text-secondary/20">/</span>
          <span className="text-secondary/60">{floorPct}% floor</span>
          {status.agreement_alert ? (
            <AlertTriangle size={11} className="text-bearish" />
          ) : (
            <CheckCircle size={11} className="text-bullish" />
          )}
        </div>
      </div>

      {/* Concept spike row */}
      <div className="flex items-center justify-between">
        <span className="text-secondary/60">Unknown concepts</span>
        <div className="flex items-center gap-1.5 tabular-nums">
          <span
            className={
              status.concept_alert ? 'text-amber-400 font-semibold' : 'text-bullish'
            }
          >
            {conceptCount}
          </span>
          <span className="text-secondary/20">/</span>
          <span className="text-secondary/60">{conceptThreshold} limit</span>
          {status.concept_alert ? (
            <AlertTriangle size={11} className="text-amber-400" />
          ) : (
            <CheckCircle size={11} className="text-bullish" />
          )}
        </div>
      </div>

      {/* Healthy chip */}
      {!hasAlert && (
        <div className="mt-2 flex items-center gap-1 text-bullish/60">
          <CheckCircle size={10} />
          <span>Pipeline healthy</span>
        </div>
      )}
    </div>
  );
}
