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

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getDriftStatus();
      setStatus(data);
      setUnavailable(false);
    } catch (err) {
      console.error('Failed to fetch drift status:', err);
      setUnavailable(true);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
    const interval = setInterval(() => void fetchStatus(), 30_000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (unavailable) {
    return (
      <div className="mt-auto px-3 py-3 rounded-lg bg-[#1c2130] border border-[#2a3246]">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Activity size={12} />
          <span>Status unavailable</span>
        </div>
      </div>
    );
  }

  if (status === null) {
    return (
      <div className="mt-auto px-3 py-3 rounded-lg bg-[#1c2130] border border-[#2a3246] animate-pulse">
        <div className="h-3 w-3/4 bg-[#2a3246] rounded mb-2" />
        <div className="h-3 w-2/3 bg-[#2a3246] rounded" />
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
          ? 'bg-red-950 border-red-800'
          : 'bg-[#1c2130] border-[#2a3246]'
      }`}
    >
      <div className="flex items-center gap-1.5 mb-2 font-semibold text-gray-300">
        <Activity size={12} className={hasAlert ? 'text-red-400' : 'text-gray-400'} />
        <span>Pipeline Monitor</span>
      </div>

      {/* Agreement rate row */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-gray-500">Agreement</span>
        <div className="flex items-center gap-1.5">
          <span
            className={
              status.agreement_alert ? 'text-red-400 font-semibold animate-pulse' : 'text-green-400'
            }
          >
            {agreementPct}%
          </span>
          <span className="text-gray-600">/</span>
          <span className="text-gray-500">{floorPct}% floor</span>
          {status.agreement_alert ? (
            <AlertTriangle size={11} className="text-red-400" />
          ) : (
            <CheckCircle size={11} className="text-green-500" />
          )}
        </div>
      </div>

      {/* Concept spike row */}
      <div className="flex items-center justify-between">
        <span className="text-gray-500">Unknown concepts</span>
        <div className="flex items-center gap-1.5">
          <span
            className={
              status.concept_alert ? 'text-amber-400 font-semibold' : 'text-green-400'
            }
          >
            {conceptCount}
          </span>
          <span className="text-gray-600">/</span>
          <span className="text-gray-500">{conceptThreshold} limit</span>
          {status.concept_alert ? (
            <AlertTriangle size={11} className="text-amber-400" />
          ) : (
            <CheckCircle size={11} className="text-green-500" />
          )}
        </div>
      </div>

      {/* Healthy chip */}
      {!hasAlert && (
        <div className="mt-2 flex items-center gap-1 text-green-600">
          <CheckCircle size={10} />
          <span className="text-green-600">Pipeline healthy</span>
        </div>
      )}
    </div>
  );
}
