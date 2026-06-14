import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle, TrendingDown, BarChart3 } from 'lucide-react';
import client from '../api/client';

interface MetricsData {
  agreement_rate: number;
  routing_distribution: { auto: number; sampled_review: number; escalate: number };
  escalation_rate: number;
  total_decisions: number;
}

interface DriftData {
  agreement_rate: number;
  agreement_floor: number;
  agreement_alert: boolean;
  unrecognized_concept_count: number;
  concept_spike_threshold: number;
  concept_alert: boolean;
  window_size: number;
  last_updated: string;
}

export default function MetricsDashboard() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [drift, setDrift] = useState<DriftData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [metricsRes, driftRes] = await Promise.all([
        client.get<MetricsData>('/review/metrics'),
        client.get<DriftData>('/review/drift'),
      ]);
      setMetrics(metricsRes.data);
      setDrift(driftRes.data);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex gap-1.5">
          <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" />
          <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-4">
        <AlertTriangle size={48} className="text-yellow-500" />
        <p className="text-gray-400">Failed to load metrics</p>
        <p className="text-sm text-gray-600">{error}</p>
      </div>
    );
  }

  const total = metrics?.total_decisions ?? 0;
  const autoPct = total > 0 ? ((metrics?.routing_distribution.auto ?? 0) / total * 100) : 0;
  const sampledPct = total > 0 ? ((metrics?.routing_distribution.sampled_review ?? 0) / total * 100) : 0;
  const escalatePct = total > 0 ? ((metrics?.routing_distribution.escalate ?? 0) / total * 100) : 0;
  const agreementPct = (metrics?.agreement_rate ?? 0) * 100;
  const isCertified = agreementPct >= 95;
  const hasDriftAlert = drift?.agreement_alert || drift?.concept_alert;

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <header className="px-4 lg:px-8 py-5 border-b border-[#2A2A2A] bg-[#121212]/50 backdrop-blur-sm z-10 flex-shrink-0">
        <h1 className="text-xl font-semibold text-white flex items-center gap-3">
          <BarChart3 className="text-emerald-400" />
          Metrics Dashboard
        </h1>
        <p className="text-sm text-gray-400 mt-1">
          Pipeline health — agreement rate, routing distribution, and drift signals
        </p>
      </header>

      <div className="flex-1 p-4 lg:p-8">
        {/* Status bar */}
        <div className={`mb-8 px-6 py-4 rounded-xl border flex items-center gap-3 ${
          hasDriftAlert
            ? 'bg-red-500/10 border-red-500/30 text-red-400'
            : isCertified
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
        }`}>
          {hasDriftAlert ? (
            <AlertTriangle size={20} />
          ) : isCertified ? (
            <CheckCircle size={20} />
          ) : (
            <TrendingDown size={20} />
          )}
          <span className="text-sm font-medium">
            {hasDriftAlert
              ? 'DRIFT ALERT — agreement rate below floor'
              : isCertified
              ? 'AUTO tier certified for production use'
              : 'AUTO tier NOT certified — agreement rate below 95% threshold'}
          </span>
          {!isCertified && !hasDriftAlert && (
            <span className="text-xs opacity-70 ml-auto">
              Target: &ge;95% agreement for AUTO tier certification
            </span>
          )}
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard
            label="Agreement Rate"
            value={`${agreementPct.toFixed(1)}%`}
            sub={`Floor: ${((drift?.agreement_floor ?? 0) * 100).toFixed(0)}%`}
            alert={drift?.agreement_alert ?? false}
            icon={<CheckCircle size={20} />}
          />
          <MetricCard
            label="Escalation Rate"
            value={`${((metrics?.escalation_rate ?? 0) * 100).toFixed(1)}%`}
            sub={`${metrics?.routing_distribution.escalate ?? 0} decisions`}
            alert={false}
            icon={<AlertTriangle size={20} />}
          />
          <MetricCard
            label="Total Decisions"
            value={`${total}`}
            sub={`Window: ${drift?.window_size ?? 100}`}
            alert={false}
            icon={<Activity size={20} />}
          />
          <MetricCard
            label="Unrecognized Concepts"
            value={`${drift?.unrecognized_concept_count ?? 0}`}
            sub={`Threshold: ${drift?.concept_spike_threshold ?? 0}`}
            alert={drift?.concept_alert ?? false}
            icon={<TrendingDown size={20} />}
          />
        </div>

        {/* Routing distribution */}
        <div className="bg-[#121212] border border-[#2A2A2A] rounded-2xl p-6 mb-8">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Routing Distribution
          </h3>
          <div className="flex items-center gap-4 mb-4">
            <div className="flex-1">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-emerald-400">AUTO</span>
                <span className="text-gray-400">{autoPct.toFixed(1)}%</span>
              </div>
              <div className="h-2 bg-[#1A1A1A] rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full transition-all duration-500" style={{ width: `${autoPct}%` }} />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 mb-4">
            <div className="flex-1">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-blue-400">SAMPLED REVIEW</span>
                <span className="text-gray-400">{sampledPct.toFixed(1)}%</span>
              </div>
              <div className="h-2 bg-[#1A1A1A] rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full transition-all duration-500" style={{ width: `${sampledPct}%` }} />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-red-400">ESCALATE</span>
                <span className="text-gray-400">{escalatePct.toFixed(1)}%</span>
              </div>
              <div className="h-2 bg-[#1A1A1A] rounded-full overflow-hidden">
                <div className="h-full bg-red-500 rounded-full transition-all duration-500" style={{ width: `${escalatePct}%` }} />
              </div>
            </div>
          </div>
        </div>

        {/* Agreement gauge */}
        <div className="bg-[#121212] border border-[#2A2A2A] rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            AUTO Tier Certification
          </h3>
          <div className="flex items-center gap-6">
            <div className="relative w-32 h-32">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke="#2A2A2A"
                  strokeWidth="8"
                />
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke={isCertified ? '#10b981' : agreementPct >= 80 ? '#f59e0b' : '#ef4444'}
                  strokeWidth="8"
                  strokeDasharray={`${agreementPct * 2.51} 251.2`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${isCertified ? 'text-emerald-400' : 'text-yellow-400'}`}>
                  {agreementPct.toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="flex-1">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">0%</span>
                <span className="text-gray-500 text-xs">{`${80}%`}</span>
                <span className="text-emerald-400 font-semibold">{`${95}%`} <span className="text-xs text-gray-500">CERTIFIED</span></span>
              </div>
              <div className="h-3 bg-[#1A1A1A] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    isCertified ? 'bg-emerald-500' : agreementPct >= 80 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${agreementPct}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  sub,
  alert,
  icon,
}: {
  label: string;
  value: string;
  sub: string;
  alert: boolean;
  icon: React.ReactNode;
}) {
  return (
    <div className={`bg-[#121212] border rounded-2xl p-5 transition-all ${
      alert ? 'border-red-500/30 bg-red-500/5' : 'border-[#2A2A2A]'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
        <span className={alert ? 'text-red-400' : 'text-gray-500'}>{icon}</span>
      </div>
      <p className={`text-2xl font-bold mb-1 ${alert ? 'text-red-400' : 'text-white'}`}>{value}</p>
      <p className="text-xs text-gray-600">{sub}</p>
    </div>
  );
}
