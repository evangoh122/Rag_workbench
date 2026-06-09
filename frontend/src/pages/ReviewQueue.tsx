import { useState, useEffect, useCallback } from 'react';
import { CheckCircle, XCircle, AlertTriangle, ClipboardList, RefreshCcw } from 'lucide-react';
import {
  getReviewQueue,
  submitVerdict,
  triggerCalibration,
} from '../api/review';
import type { ReviewDecision } from '../api/review';

type FilterTab = 'all' | 'ESCALATE' | 'SAMPLED_REVIEW';

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error';
}

function SkeletonCard() {
  return (
    <div className="bg-[#131926] border border-[#2a3246] rounded-xl p-5 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="h-6 w-24 bg-[#2a3246] rounded-full" />
        <div className="h-4 w-16 bg-[#2a3246] rounded" />
        <div className="ml-auto h-5 w-12 bg-[#2a3246] rounded" />
      </div>
      <div className="h-3 w-1/2 bg-[#2a3246] rounded mb-3" />
      <div className="flex gap-2 mb-4">
        <div className="h-5 w-20 bg-[#2a3246] rounded-full" />
        <div className="h-5 w-20 bg-[#2a3246] rounded-full" />
      </div>
      <div className="flex gap-3 mt-4">
        <div className="h-9 w-24 bg-[#2a3246] rounded-lg" />
        <div className="h-9 w-24 bg-[#2a3246] rounded-lg" />
      </div>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <div className="flex-1 h-2 bg-[#2a3246] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, #ef4444 0%, #eab308 50%, #22c55e 100%)`,
            backgroundSize: '200% 100%',
            backgroundPosition: `${100 - pct}% 0`,
          }}
        />
      </div>
      <span className="text-xs text-gray-400 flex-shrink-0 w-9 text-right">
        {pct}%
      </span>
    </div>
  );
}

function DecisionCard({
  decision,
  onVerdict,
}: {
  decision: ReviewDecision;
  onVerdict: (id: string, agrees: boolean) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);

  const handleVerdict = async (agrees: boolean) => {
    setSubmitting(true);
    try {
      await onVerdict(decision.id, agrees);
    } finally {
      setSubmitting(false);
    }
  };

  const isEscalate = decision.route === 'ESCALATE';

  return (
    <div className="bg-[#131926] border border-[#2a3246] rounded-xl p-5 flex flex-col gap-3 transition-colors duration-200 hover:border-[#3d4f6e]">
      {/* Top row: route badge + confidence bar + form type chip */}
      <div className="flex items-center gap-3 flex-wrap">
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold flex-shrink-0 ${
            isEscalate
              ? 'bg-red-900 text-red-300'
              : 'bg-amber-900 text-amber-300'
          }`}
        >
          {isEscalate ? (
            <AlertTriangle size={12} />
          ) : (
            <ClipboardList size={12} />
          )}
          {decision.route}
        </span>

        <ConfidenceBar value={decision.confidence} />

        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-[#1c222e] text-gray-300 border border-[#2a3246] flex-shrink-0">
          {decision.form_type}
        </span>
      </div>

      {/* Filing info */}
      <div className="flex items-center gap-4 text-sm text-gray-400">
        <span>
          <span className="text-gray-500">CIK: </span>
          <span className="text-gray-200 font-mono">{decision.cik}</span>
        </span>
        <span>
          <span className="text-gray-500">Accession: </span>
          <span className="text-gray-200 font-mono text-xs">{decision.accession}</span>
        </span>
      </div>

      {/* Triggers fired */}
      <div className="flex items-center gap-2 flex-wrap">
        {decision.triggers_fired.length > 0 ? (
          decision.triggers_fired.map((trigger) => (
            <span
              key={trigger}
              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-950 text-red-400 border border-red-900"
            >
              {trigger}
            </span>
          ))
        ) : (
          <span className="text-xs text-gray-500 italic">No triggers fired</span>
        )}
      </div>

      {/* Status / actions */}
      <div className="flex items-center gap-3 pt-1">
        {decision.status === 'reviewed' ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-[#1c222e] text-gray-400 border border-[#2a3246]">
            <CheckCircle size={14} className="text-green-500" />
            Reviewed
          </span>
        ) : (
          <>
            <button
              onClick={() => void handleVerdict(true)}
              disabled={submitting}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-green-700 hover:bg-green-600 text-white border-0 cursor-pointer transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <CheckCircle size={14} />
              Agree
            </button>
            <button
              onClick={() => void handleVerdict(false)}
              disabled={submitting}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-red-700 hover:bg-red-600 text-white border-0 cursor-pointer transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <XCircle size={14} />
              Disagree
            </button>
          </>
        )}
        <span className="ml-auto text-xs text-gray-600">
          {new Date(decision.created_at).toLocaleString()}
        </span>
      </div>
    </div>
  );
}

export default function ReviewQueue() {
  const [decisions, setDecisions] = useState<ReviewDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [calibrating, setCalibrating] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = (message: string, type: 'success' | 'error') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const fetchQueue = useCallback(async () => {
    try {
      setError(null);
      const data = await getReviewQueue();
      setDecisions(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load review queue';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchQueue();
  }, [fetchQueue]);

  const handleVerdict = async (id: string, agrees: boolean) => {
    // Optimistic update
    setDecisions((prev) =>
      prev.map((d) =>
        d.id === id ? { ...d, status: 'reviewed' as const } : d,
      ),
    );
    try {
      await submitVerdict({ decision_id: id, reviewer_agrees: agrees });
    } catch (err: unknown) {
      // Revert on failure
      setDecisions((prev) =>
        prev.map((d) =>
          d.id === id ? { ...d, status: 'pending' as const } : d,
        ),
      );
      const message = err instanceof Error ? err.message : 'Failed to submit verdict';
      addToast(`Error: ${message}`, 'error');
    }
  };

  const handleCalibration = async () => {
    setCalibrating(true);
    try {
      const result = await triggerCalibration();
      addToast(result.message ?? 'Calibration triggered', 'success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Calibration failed';
      addToast(`Error: ${message}`, 'error');
    } finally {
      setCalibrating(false);
    }
  };

  const filtered = decisions.filter((d) => {
    if (activeTab === 'all') return true;
    return d.route === activeTab;
  });

  const pendingCount = decisions.filter((d) => d.status === 'pending').length;

  const tabs: { label: string; value: FilterTab }[] = [
    { label: 'All', value: 'all' },
    { label: 'ESCALATE', value: 'ESCALATE' },
    { label: 'SAMPLED_REVIEW', value: 'SAMPLED_REVIEW' },
  ];

  return (
    <div className="flex flex-col h-full min-w-0 relative">
      {/* Toast container */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-3 rounded-lg text-sm font-medium shadow-lg pointer-events-auto transition-all duration-300 ${
              t.type === 'success'
                ? 'bg-green-800 text-green-100 border border-green-700'
                : 'bg-red-800 text-red-100 border border-red-700'
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>

      {/* Header */}
      <header className="px-6 py-4 border-b border-[#2a3246] flex items-center gap-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <ClipboardList size={22} className="text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Review Queue</h1>
          {pendingCount > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-2 rounded-full text-xs font-bold bg-blue-600 text-white">
              {pendingCount}
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => void fetchQueue()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 bg-transparent border border-[#2a3246] hover:border-[#3d4f6e] cursor-pointer transition-all duration-200 disabled:opacity-50"
          >
            <RefreshCcw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={() => void handleCalibration()}
            disabled={calibrating}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white border-0 cursor-pointer transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {calibrating ? (
              <RefreshCcw size={14} className="animate-spin" />
            ) : null}
            Trigger Calibration
          </button>
        </div>
      </header>

      {/* Filter tabs */}
      <div className="px-6 pt-4 flex items-center gap-1 border-b border-[#2a3246] pb-0 flex-shrink-0">
        {tabs.map((tab) => {
          const count =
            tab.value === 'all'
              ? decisions.length
              : decisions.filter((d) => d.route === tab.value).length;
          return (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors duration-200 cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0 ${
                activeTab === tab.value
                  ? 'border-b-blue-500 text-blue-400'
                  : 'border-b-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className={`ml-2 inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full text-xs font-semibold ${
                    activeTab === tab.value
                      ? 'bg-blue-900 text-blue-300'
                      : 'bg-[#2a3246] text-gray-400'
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {error && (
          <div className="flex items-center gap-3 px-4 py-3 mb-6 rounded-lg bg-red-950 border border-red-800 text-red-300 text-sm">
            <AlertTriangle size={16} className="flex-shrink-0" />
            <span>{error}</span>
            <button
              onClick={() => void fetchQueue()}
              className="ml-auto text-red-400 hover:text-red-200 underline bg-transparent border-0 cursor-pointer text-sm"
            >
              Retry
            </button>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col gap-4">
            {[1, 2, 3].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <ClipboardList size={48} className="text-gray-600 mb-4" />
            <p className="text-lg font-medium text-gray-400">
              No decisions in review queue
            </p>
            <p className="text-sm text-gray-600 mt-1">
              {activeTab !== 'all'
                ? `No ${activeTab} decisions found`
                : 'All caught up — no items need review'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {filtered.map((d) => (
              <DecisionCard key={d.id} decision={d} onVerdict={handleVerdict} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
