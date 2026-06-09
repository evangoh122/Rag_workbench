import React, { useEffect, useState, useCallback } from 'react';
import {
  Database, Cpu, AlertTriangle, CheckCircle, RefreshCcw,
  FileText, GitBranch, Layers, Zap, Server, ArrowRight,
} from 'lucide-react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

interface StatsData {
  data: {
    filing_chunks: number | null;
    companies_with_chunks: number | null;
    xbrl_facts: number | null;
    companies_with_xbrl: number | null;
    graph_triples: number | null;
    ticker_embeddings: number | null;
    tickers_embedded: string[];
    error?: string;
  };
  review: {
    total_decisions: number | null;
    total_verdicts: number | null;
    pending: number | null;
    escalated: number | null;
    error?: string;
  };
  llm: {
    total_calls: number;
    failed_calls: number;
    success_rate: number;
    last_error: string | null;
    last_error_time: string | null;
    recent_errors: string[];
  };
  config: {
    provider: string;
    embedding_model: string;
    embedding_dim: number;
  };
  database: {
    main_connected: boolean;
    review_connected: boolean;
  };
}

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString();
}

function StatCard({
  label, value, sub, icon, accent = 'blue', alert = false,
}: {
  label: string; value: string; sub?: string;
  icon: React.ReactNode; accent?: string; alert?: boolean;
}) {
  const colors: Record<string, string> = {
    blue:   'text-blue-400 bg-blue-500/10 border-blue-500/20',
    emerald:'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
    red:    'text-red-400 bg-red-500/10 border-red-500/20',
    cyan:   'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  };
  const c = alert ? colors.red : (colors[accent] ?? colors.blue);
  return (
    <div className={`bg-[#0f1219] border rounded-2xl p-5 ${alert ? 'border-red-500/30' : 'border-[#202532]'}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
        <span className={`p-1.5 rounded-lg border ${c}`}>{icon}</span>
      </div>
      <p className={`text-2xl font-bold mb-1 ${alert ? 'text-red-400' : 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600">{sub}</p>}
    </div>
  );
}

function PipelineNode({ label, sub, color }: { label: string; sub?: string; color: string }) {
  return (
    <div className={`flex flex-col items-center justify-center px-4 py-3 rounded-xl border text-center min-w-[110px] ${color}`}>
      <span className="text-sm font-semibold">{label}</span>
      {sub && <span className="text-xs opacity-60 mt-0.5">{sub}</span>}
    </div>
  );
}

function Arrow() {
  return <ArrowRight size={16} className="text-gray-600 flex-shrink-0" />;
}

export default function SystemDashboard() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get<StatsData>(`${API_BASE}/stats`);
      setStats(res.data);
      setLastRefresh(new Date());
    } catch {
      // keep stale data on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const t = setInterval(fetchStats, 30_000);
    return () => clearInterval(t);
  }, [fetchStats]);

  const llmFailed = stats?.llm.failed_calls ?? 0;
  const llmTotal  = stats?.llm.total_calls  ?? 0;
  const successPct = stats ? Math.round(stats.llm.success_rate * 100) : 100;
  const mainOk   = stats?.database.main_connected ?? false;
  const reviewOk = stats?.database.review_connected ?? false;

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <header className="px-8 py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm flex-shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-3">
            <Server className="text-orange-400" />
            System Overview
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Live data coverage, LLM health, and pipeline architecture
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-gray-600">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchStats}
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-white border border-[#202532] hover:border-[#2a3040] bg-transparent hover:bg-[#161b24] transition-all cursor-pointer"
          >
            <RefreshCcw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </header>

      <div className="flex-1 p-8 space-y-8">

        {/* ── Status bar ── */}
        <div className="flex items-center gap-3 px-5 py-3.5 rounded-xl border border-[#202532] bg-[#0f1219] text-sm">
          <div className={`w-2 h-2 rounded-full ${mainOk ? 'bg-emerald-500' : 'bg-red-500'}`} />
          <span className={mainOk ? 'text-emerald-400' : 'text-red-400'}>Main DB</span>
          <span className="text-gray-700">·</span>
          <div className={`w-2 h-2 rounded-full ${reviewOk ? 'bg-emerald-500' : 'bg-red-500'}`} />
          <span className={reviewOk ? 'text-emerald-400' : 'text-red-400'}>Review DB</span>
          <span className="text-gray-700">·</span>
          <span className="text-gray-400">Provider:</span>
          <span className="text-white font-medium">{stats?.config.provider ?? '—'}</span>
          <span className="text-gray-700">·</span>
          <span className="text-gray-400">Embeddings:</span>
          <span className="text-white font-medium">
            {stats?.config.embedding_model ?? '—'} ({stats?.config.embedding_dim ?? '—'}d)
          </span>
        </div>

        {/* ── Stat cards ── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Companies Loaded"
            value={fmt(stats?.data.companies_with_chunks)}
            sub={`${fmt(stats?.data.companies_with_xbrl)} with XBRL facts`}
            icon={<Database size={16} />}
            accent="blue"
          />
          <StatCard
            label="Filing Chunks"
            value={fmt(stats?.data.filing_chunks)}
            sub={`${fmt(stats?.data.xbrl_facts)} XBRL facts`}
            icon={<FileText size={16} />}
            accent="emerald"
          />
          <StatCard
            label="Graph Triples"
            value={fmt(stats?.data.graph_triples)}
            sub="Knowledge graph edges"
            icon={<GitBranch size={16} />}
            accent="purple"
          />
          <StatCard
            label="LLM Failures"
            value={fmt(llmFailed)}
            sub={`${successPct}% success · ${fmt(llmTotal)} total calls`}
            icon={<Zap size={16} />}
            accent={llmFailed > 0 ? 'red' : 'orange'}
            alert={llmFailed > 5}
          />
        </div>

        {/* ── Pipeline architecture ── */}
        <div className="bg-[#0f1219] border border-[#202532] rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-6">
            Pipeline Architecture
          </h3>

          {/* Ingestion row */}
          <div className="mb-4">
            <p className="text-xs text-gray-600 uppercase tracking-widest mb-3 px-1">Data Ingestion</p>
            <div className="flex items-center gap-2 flex-wrap">
              <PipelineNode label="SEC EDGAR" sub="10-K filings" color="border-blue-500/30 bg-blue-500/5 text-blue-300" />
              <Arrow />
              <PipelineNode label="Downloader" sub="sec-edgar-dl" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="HTML Parser" sub="BeautifulSoup" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="Text Splitter" sub="LangChain" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="Ollama Embed" sub={stats?.config.embedding_model ?? 'nomic-embed-text'} color="border-purple-500/30 bg-purple-500/5 text-purple-300" />
              <Arrow />
              <PipelineNode label="DuckDB" sub="edgar_chunks" color="border-emerald-500/30 bg-emerald-500/5 text-emerald-300" />
            </div>
          </div>

          <div className="border-t border-[#202532] my-4" />

          {/* Query row */}
          <div className="mb-4">
            <p className="text-xs text-gray-600 uppercase tracking-widest mb-3 px-1">Query Pipeline</p>
            <div className="flex items-center gap-2 flex-wrap">
              <PipelineNode label="User Query" sub="natural language" color="border-blue-500/30 bg-blue-500/5 text-blue-300" />
              <Arrow />
              <PipelineNode label="Embed Query" sub="Ollama" color="border-purple-500/30 bg-purple-500/5 text-purple-300" />
              <Arrow />
              <PipelineNode label="Vector Search" sub="VSS cosine" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="XBRL Lookup" sub="exact match" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="LLM Synthesis" sub={stats?.config.provider ?? 'provider'} color="border-orange-500/30 bg-orange-500/5 text-orange-300" />
              <Arrow />
              <PipelineNode label="Verifier" sub="XBRL cross-check" color="border-emerald-500/30 bg-emerald-500/5 text-emerald-300" />
            </div>
          </div>

          <div className="border-t border-[#202532] my-4" />

          {/* Graph RAG row */}
          <div>
            <p className="text-xs text-gray-600 uppercase tracking-widest mb-3 px-1">Graph RAG (optional)</p>
            <div className="flex items-center gap-2 flex-wrap">
              <PipelineNode label="Entity Extract" sub="from query" color="border-indigo-500/30 bg-indigo-500/5 text-indigo-300" />
              <Arrow />
              <PipelineNode label="Graph Triples" sub="DuckDB" color="border-indigo-500/30 bg-indigo-500/5 text-indigo-300" />
              <Arrow />
              <PipelineNode label="Subgraph" sub="BFS/DFS" color="border-[#202532] bg-[#161b24] text-gray-300" />
              <Arrow />
              <PipelineNode label="LLM Synthesis" sub="with graph ctx" color="border-orange-500/30 bg-orange-500/5 text-orange-300" />
            </div>
          </div>
        </div>

        {/* ── Two-col: review stats + ticker list ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Review queue stats */}
          <div className="bg-[#0f1219] border border-[#202532] rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
              Review Queue
            </h3>
            <div className="space-y-3">
              {[
                { label: 'Total Decisions', value: fmt(stats?.review.total_decisions), color: 'text-white' },
                { label: 'Human Verdicts', value: fmt(stats?.review.total_verdicts), color: 'text-white' },
                { label: 'Pending Review', value: fmt(stats?.review.pending), color: 'text-yellow-400' },
                { label: 'Escalated',       value: fmt(stats?.review.escalated), color: 'text-red-400' },
              ].map(row => (
                <div key={row.label} className="flex justify-between items-center py-2 border-b border-[#202532]/50 last:border-0">
                  <span className="text-sm text-gray-400">{row.label}</span>
                  <span className={`text-sm font-semibold ${row.color}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* LLM health */}
          <div className="bg-[#0f1219] border border-[#202532] rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              LLM Health
              {llmFailed > 0
                ? <AlertTriangle size={14} className="text-red-400" />
                : <CheckCircle size={14} className="text-emerald-400" />}
            </h3>
            {/* Success rate bar */}
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1.5">
                <span className="text-gray-400">Success rate</span>
                <span className={successPct >= 95 ? 'text-emerald-400' : 'text-yellow-400'}>{successPct}%</span>
              </div>
              <div className="h-2 bg-[#161b24] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${successPct >= 95 ? 'bg-emerald-500' : 'bg-yellow-500'}`}
                  style={{ width: `${successPct}%` }}
                />
              </div>
            </div>
            <div className="space-y-2">
              {[
                { label: 'Total Calls',    value: fmt(llmTotal) },
                { label: 'Failed Calls',   value: fmt(llmFailed) },
                { label: 'Last Error',     value: stats?.llm.last_error ?? 'None' },
              ].map(row => (
                <div key={row.label} className="flex justify-between items-start py-1.5 border-b border-[#202532]/50 last:border-0 gap-4">
                  <span className="text-sm text-gray-400 flex-shrink-0">{row.label}</span>
                  <span className="text-sm text-white text-right truncate max-w-[200px]" title={row.value}>{row.value}</span>
                </div>
              ))}
            </div>
            {stats?.llm.recent_errors && stats.llm.recent_errors.length > 0 && (
              <div className="mt-4 p-3 bg-red-500/5 border border-red-500/20 rounded-xl">
                <p className="text-xs font-semibold text-red-400 mb-2">Recent Errors</p>
                {stats.llm.recent_errors.map((e, i) => (
                  <p key={i} className="text-xs text-gray-500 truncate">{e}</p>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Ticker coverage ── */}
        {stats?.data.tickers_embedded && stats.data.tickers_embedded.length > 0 && (
          <div className="bg-[#0f1219] border border-[#202532] rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Layers size={14} />
              Embedded Tickers ({stats.data.tickers_embedded.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {stats.data.tickers_embedded.map(t => (
                <span
                  key={t}
                  className="px-2.5 py-1 text-xs font-mono bg-[#161b24] border border-[#202532] rounded-lg text-gray-300 hover:border-blue-500/30 hover:text-blue-300 transition-colors"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
