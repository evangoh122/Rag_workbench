import React, { useState, useRef, useEffect } from 'react';
import { Send, Database, BookOpen, RefreshCcw, Search, Activity, MessageSquare, BarChart3, Network, Server, Cpu, ThumbsUp, ThumbsDown, ShieldCheck, Menu, X, Lightbulb, Info, ChevronDown, ArrowRight, FlaskConical } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendSqlMessage, sendRagMessage, sendAuditableRagMessage, sendGraphRagMessage } from './api/chat';
import type { ChatResponse, Source, XBRLFact, Triple, ChartSpec, ToneAnalysis as ToneAnalysisData } from './api/chat';
import { submitChatFeedback } from './api/review';
import ReviewQueue from './pages/ReviewQueue';
import MetricsDashboard from './pages/MetricsDashboard';
import SystemDashboard from './pages/SystemDashboard';
import ProductAnalytics from './pages/ProductAnalytics';
import ConjointStudy from './pages/ConjointStudy';
import ConjointGate from './components/ConjointGate';
import ConjointSurvey from './components/ConjointSurvey';
import {
  loadConjointPrefs,
  hasCompletedConjoint,
  type ConjointPrefs,
} from './api/conjoint';
import Methodology from './pages/Methodology';
import StocksList from './pages/StocksList';
import AuditLog from './pages/AuditLog';
import DriftAlert from './components/DriftAlert';
import AuditTrail from './components/AuditTrail';
import PipelineFlow from './components/PipelineFlow';
import FinancialChart from './components/FinancialChart';
import ChartErrorBoundary from './components/ChartErrorBoundary';
import ToneAnalysis from './components/ToneAnalysis';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: Record<string, unknown>[];
  sources?: Source[];
  xbrl_facts?: XBRLFact[];
  relevant_xbrl?: XBRLFact[];
  xbrl_badge?: string;
  xbrl_group?: string;
  verification?: {
    status: string;
    reasoning: string;
  };
  math_steps?: string[];
  entities?: string[];
  triples?: Triple[];
  what_it_means?: string;
  how_to_interpret?: string;
  follow_ups?: string[];
  chart?: ChartSpec;
  tone_analysis?: ToneAnalysisData;
}

type AppView = 'chat' | 'graph' | 'traceability' | 'results' | 'metrics' | 'system' | 'methodology' | 'stocks' | 'audit' | 'analytics' | 'conjoint';

type PipelineStatus = {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
};

import { getPosthog } from './utils/posthog'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import PortfolioHome from './pages/PortfolioHome';
import RagOverview from './pages/RagOverview';

import ChartView from './components/ChartView';
import GraphExplorer from './components/GraphExplorer';
import KnowledgeGraph from './components/KnowledgeGraph';
import type { GraphSelection } from './components/KnowledgeGraph';
import { getGraphEvidence, getGraphTriples, type GraphEvidence } from './api/graph';
import { COMPANY_NAMES } from './components/GraphExplorer';

function Workbench() {
  useEffect(() => {
    document.title = "RAG Workbench";
  }, []);

  const navigate = useNavigate();
  const location = useLocation();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, _setMode] = useState<'sql' | 'rag' | 'auditable' | 'graph'>('auditable');
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<AppView>(() => {
    const state = location.state as { initialView?: string } | null;
    if (state && state.initialView) {
      return state.initialView as AppView;
    }
    return 'chat';
  });
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({});
  const [ticker, _setTicker] = useState('MU');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<Set<number>>(new Set());
  // Conjoint personalization. `prefs` (arm/role/answer-experience levels) drives
  // both the chat presentation and whether role-based answers are requested.
  const [prefs, setPrefs] = useState<ConjointPrefs | null>(() => loadConjointPrefs());
  const [gateOpen, setGateOpen] = useState<boolean>(() => loadConjointPrefs() === null);
  const [surveyOpen, setSurveyOpen] = useState(false);
  const [surveyPrompted, setSurveyPrompted] = useState<boolean>(() => hasCompletedConjoint());
  // Personalization toggles derived from prefs (standard/control => all shown).
  const showEvidence = prefs?.evidence !== 'text_only';
  const showExplain = prefs?.answer_style !== 'direct';
  const promptsGuided = prefs?.prompts === 'guided';
  const roleArg =
    prefs?.arm === 'treatment' && prefs?.answer_basis === 'role_based' ? prefs?.role ?? null : null;
  const [graphModalOpen, setGraphModalOpen] = useState(false);
  const [activeTriples, setActiveTriples] = useState<any[]>([]);
  const [originalTriples, setOriginalTriples] = useState<any[]>([]);
  const [modalTicker, setModalTicker] = useState('');
  const [graphCompanies, setGraphCompanies] = useState<string[]>([]);
  const [modalLoading, setModalLoading] = useState(false);
  // Phase C: click an edge/node in the graph → fetch + show its source evidence.
  const [evidence, setEvidence] = useState<GraphEvidence | null>(null);
  const [evidenceSel, setEvidenceSel] = useState<GraphSelection | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const handleGraphSelect = (sel: GraphSelection) => {
    setEvidenceSel(sel);
    setEvidence(null);
    if (!sel.chunk_id) return; // legacy/code-graph triple — no source ref
    setEvidenceLoading(true);
    getGraphEvidence(sel.chunk_id)
      .then((e) => setEvidence(e))
      .catch(() => setEvidence(null))
      .finally(() => setEvidenceLoading(false));
    if (import.meta.env.VITE_POSTHOG_KEY) {
      getPosthog().then((p) => p.capture('graph_evidence_open', { chunk_id: sel.chunk_id }));
    }
  };

  const closeGraphModal = () => {
    setGraphModalOpen(false);
    setEvidence(null);
    setEvidenceSel(null);
  };

  const handleModalTickerChange = (ticker: string) => {
    setModalTicker(ticker);
    setEvidence(null);
    setEvidenceSel(null);
    if (!ticker) {
      setActiveTriples(originalTriples);
    } else {
      setModalLoading(true);
      getGraphTriples(ticker, 150)
        .then((t) => setActiveTriples(t))
        .catch(() => {})
        .finally(() => setModalLoading(false));
    }
  };

  useEffect(() => {
    const allTickers = Object.keys(COMPANY_NAMES).sort();
    setGraphCompanies(allTickers);
  }, []);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Once the user has engaged (≥3 assistant answers), prompt the end-of-session
  // study a single time — unless they've already completed it or the gate is up.
  useEffect(() => {
    if (surveyPrompted || gateOpen || prefs === null) return;
    const answers = messages.filter((m) => m.role === 'assistant').length;
    if (answers >= 3) {
      setSurveyPrompted(true);
      setSurveyOpen(true);
    }
  }, [messages, surveyPrompted, gateOpen, prefs]);

  useEffect(() => {
    if (import.meta.env.VITE_POSTHOG_KEY) {
      getPosthog().then(p => p.capture('$pageview', { view }))
    }
  }, [view]);

  const handleSubmit = async (e?: React.FormEvent, overrideText?: string) => {
    e?.preventDefault();
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    if (mode === 'auditable') {
      setPipelineStatus({ input: 'success', retrieval: 'pending' });
      // If the user submits from the traceability view, we might want to stay there or move them.
      // We'll keep them wherever they are.
    }
    const userMsg: Message = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = text;
    setInput('');
    setLoading(true);

    if (import.meta.env.VITE_POSTHOG_KEY) {
      getPosthog().then(p => p.capture('chat_send', { mode, query_length: currentInput.length, view }))
    }

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));

      let data: ChatResponse;
      if (mode === 'sql') {
        data = await sendSqlMessage(currentInput, history);
      } else if (mode === 'rag') {
        data = await sendRagMessage(currentInput, history);
      } else if (mode === 'graph') {
        data = await sendGraphRagMessage(currentInput, ticker);
      } else {
        data = await sendAuditableRagMessage(currentInput, ticker, history, roleArg);
      }

      // Persist the company the backend resolved to, so a follow-up that names
      // no company stays grounded on it instead of falling back to the default.
      if (data.ticker) {
        _setTicker(data.ticker);
      }

      if (data.pipeline_status) {
        setPipelineStatus(data.pipeline_status);
      } else if (mode !== 'auditable') {
        setPipelineStatus({
          input: 'success',
          retrieval: 'success',
          extraction: 'success',
          math: 'success',
          verification: 'success',
          output: 'success',
        });
      }

      const assistantMsg: Message = {
        role: 'assistant',
        content: data.answer ?? data.detail ?? 'No response',
        type: data.type,
        sql: data.sql,
        data: data.data,
        sources: data.sources,
        xbrl_facts: data.xbrl_facts,
        relevant_xbrl: data.relevant_xbrl,
        xbrl_badge: data.xbrl_badge,
        verification: data.verification,
        math_steps: data.math_steps,
        entities: data.entities,
        triples: data.triples,
        what_it_means: data.what_it_means,
        how_to_interpret: data.how_to_interpret,
        follow_ups: data.follow_ups,
        chart: data.chart,
        tone_analysis: data.tone_analysis,
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: unknown) {
      setPipelineStatus({
        input: 'success',
        retrieval: 'error',
      });
      const is400 =
        err != null &&
        typeof err === 'object' &&
        'response' in err &&
        (err as { response?: { status?: number } }).response?.status === 400;
      const message = is400
        ? 'This does not appear to be finance related, do you want to rephrase that question?'
        : err instanceof Error
          ? err.message
          : 'An unexpected error occurred';
      if (import.meta.env.VITE_POSTHOG_KEY) {
        getPosthog().then(p => p.capture('chat_error', { mode, error: message }))
      }
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: is400 ? message : `Error: ${message}`,
          type: 'error',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-primary font-sans">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-72 glass-sidebar flex flex-col px-4 py-5
        transition-transform duration-300 ease-out lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo (returns to the portfolio home) */}
        <div className="flex items-center justify-between mb-7 px-1">
          <button
            type="button"
            onClick={() => navigate('/')}
            title="Back to home"
            aria-label="Back to home"
            className="flex items-center gap-3 bg-transparent border-0 p-0 cursor-pointer text-left"
          >
            <div className="bg-gradient-to-br from-emerald-500 to-green-600 p-2 rounded-lg shadow-[0_0_12px_rgba(46,139,87,0.25)]">
              <Search size={20} className="text-white" />
            </div>
            <h2 className="m-0 text-lg font-semibold text-primary tracking-tight hover:text-emerald-300 transition-colors">RAG Workbench</h2>
          </button>
          <button
            className="lg:hidden p-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        {/* Main Navigation */}
        <nav className="flex flex-col gap-5 mb-8 overflow-y-auto">
          {/* USER SECTION */}
          <div>
            <div className="text-[10px] font-semibold text-muted uppercase tracking-[0.12em] px-2 mb-2.5">For Users</div>
            <div className="flex flex-col gap-1">
              <button
                className={`nav-item ${
                  view === 'stocks'
                    ? 'active !text-bullish [&>svg]:text-bullish'
                    : ''
                }`}
                onClick={() => {
                  setView('stocks');
                  setSidebarOpen(false);
                }}
              >
                <Cpu size={16} className={view === 'stocks' ? 'text-bullish' : 'text-secondary'} />
                Coverage List
              </button>
              <button
                className={`nav-item ${
                  view === 'chat'
                    ? 'active !text-accent [&>svg]:text-accent'
                    : ''
                }`}
                onClick={() => {
                  setView('chat');
                  setSidebarOpen(false);
                }}
              >
                <MessageSquare size={16} className={view === 'chat' ? 'text-accent' : 'text-secondary'} />
                Testing Chat
              </button>
              <button
                className={`nav-item ${
                  view === 'traceability'
                    ? 'active !text-purple-400 [&>svg]:text-purple-400'
                    : ''
                }`}
                onClick={() => {
                  setView('traceability');
                  setSidebarOpen(false);
                }}
              >
                <Activity size={16} className={view === 'traceability' ? 'text-purple-400' : 'text-secondary'} />
                Pipeline Traceability
              </button>
              <button
                className={`nav-item ${
                  view === 'methodology'
                    ? 'active !text-indigo-400 [&>svg]:text-indigo-400'
                    : ''
                }`}
                onClick={() => {
                  setView('methodology');
                  setSidebarOpen(false);
                }}
              >
                <BookOpen size={16} className={view === 'methodology' ? 'text-indigo-400' : 'text-secondary'} />
                Methodology
              </button>
            </div>
          </div>

          {/* DIAGNOSTIC SECTION */}
          <div>
            <div className="text-[10px] font-semibold text-muted uppercase tracking-[0.12em] px-2 mb-2.5">Audit & Diagnostics</div>
            <div className="flex flex-col gap-1">
              <button
                className={`nav-item ${
                  view === 'graph'
                    ? 'active !text-accent [&>svg]:text-accent'
                    : ''
                }`}
                onClick={() => {
                  setView('graph');
                  setSidebarOpen(false);
                }}
              >
                <Network size={16} className={view === 'graph' ? 'text-accent' : 'text-secondary'} />
                Knowledge Graph
              </button>
              <button
                className={`nav-item ${
                  view === 'results'
                    ? 'active !text-bullish [&>svg]:text-bullish'
                    : ''
                }`}
                onClick={() => {
                  setView('results');
                  setSidebarOpen(false);
                }}
              >
                <BarChart3 size={16} className={view === 'results' ? 'text-bullish' : 'text-secondary'} />
                Results & Testing
              </button>

              <button
                className={`nav-item ${
                  view === 'audit'
                    ? 'active !text-amber-400 [&>svg]:text-amber-400'
                    : ''
                }`}
                onClick={() => {
                  setView('audit');
                  setSidebarOpen(false);
                }}
              >
                <ShieldCheck size={16} className={view === 'audit' ? 'text-amber-400' : 'text-secondary'} />
                Audit Log
              </button>

              <button
                className={`nav-item ${
                  view === 'metrics'
                    ? 'active !text-cyan-400 [&>svg]:text-cyan-400'
                    : ''
                }`}
                onClick={() => {
                  setView('metrics');
                  setSidebarOpen(false);
                }}
              >
                <Activity size={16} className={view === 'metrics' ? 'text-cyan-400' : 'text-secondary'} />
                Metrics Dashboard
              </button>

              <button
                className={`nav-item ${
                  view === 'system'
                    ? 'active !text-orange-400 [&>svg]:text-orange-400'
                    : ''
                }`}
                onClick={() => {
                  setView('system');
                  setSidebarOpen(false);
                }}
              >
                <Server size={16} className={view === 'system' ? 'text-orange-400' : 'text-secondary'} />
                System Overview
              </button>

              <button
                className={`nav-item ${
                  view === 'conjoint'
                    ? 'active !text-pink-400 [&>svg]:text-pink-400'
                    : ''
                }`}
                onClick={() => {
                  setView('conjoint');
                  setSidebarOpen(false);
                }}
              >
                <FlaskConical size={16} className={view === 'conjoint' ? 'text-pink-400' : 'text-secondary'} />
                Answer Study
              </button>
            </div>
          </div>
        </nav>

        {/* Clear chat button */}
        {(view === 'chat' || view === 'traceability') && (
          <div className="mt-auto">
            <button
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg text-sm font-medium text-gray-400 hover:text-red-400 glass-button hover:border-red-900/50 hover:bg-red-500/5"
              onClick={() => {
                if (import.meta.env.VITE_POSTHOG_KEY) {
                  getPosthog().then(p => p.capture('session_reset', { message_count: messages.length, view }));
                }
                setMessages([]);
                setPipelineStatus({});
                setFeedbackSent(new Set());
              }}
            >
              <RefreshCcw size={14} />
              Reset Session
            </button>
          </div>
        )}

        {/* Drift alert at bottom of sidebar */}
        <div className={(view === 'results' || view === 'metrics') ? 'mt-auto' : 'mt-3'}>
          <DriftAlert />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-background relative">
        {/* Mobile Header Toggle */}
          <div className="lg:hidden flex items-center px-3 py-2.5 glass-header sticky top-0 z-30 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
          >
            <Menu size={22} />
          </button>
          <div className="ml-3 flex items-center gap-2">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-1.5 rounded-lg">
              <Search size={14} className="text-white" />
            </div>
            <span className="font-semibold text-base tracking-tight text-primary">RAG Workbench</span>
          </div>
        </div>
        
        {/* VIEW: AUDIT LOG */}
        {view === 'audit' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200 overflow-hidden">
            <AuditLog />
          </div>
        )}

        {/* VIEW: RESULTS */}
        {view === 'results' && (
          <div className="flex-1 overflow-hidden animate-in fade-in duration-200">
            <ReviewQueue />
          </div>
        )}

        {/* VIEW: METRICS */}
        {view === 'metrics' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
            <MetricsDashboard />
          </div>
        )}

        {/* VIEW: PRODUCT ANALYTICS */}
        {view === 'analytics' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
            <ProductAnalytics />
          </div>
        )}

        {/* VIEW: CONJOINT / ANSWER EXPERIENCE STUDY */}
        {view === 'conjoint' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
            <ConjointStudy />
          </div>
        )}

        {/* VIEW: SYSTEM OVERVIEW */}
        {view === 'system' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
            <SystemDashboard />
          </div>
        )}

        {/* VIEW: METHODOLOGY */}
        {view === 'methodology' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
            <Methodology />
          </div>
        )}

        {/* VIEW: STOCKS */}
        {view === 'stocks' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200 overflow-y-auto">
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-4 glass-header z-10 flex-shrink-0">
                <h1 className="text-base md:text-lg font-semibold text-primary flex items-center gap-2">
                  <Cpu className="text-emerald-400" size={18} />
                  Coverage List
                </h1>
              </header>
            <StocksList />
          </div>
        )}

        {/* VIEW: TRACEABILITY */}
        {view === 'traceability' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-4 glass-header z-10 flex-shrink-0">
                <h1 className="text-base md:text-lg font-semibold text-primary flex items-center gap-2">
                  <Activity className="text-purple-400" size={18} />
                  Pipeline Traceability
                </h1>
                <p className="text-xs text-secondary mt-0.5">Live visualization of the execution steps for your last query.</p>
              </header>
            <div className="flex-1 relative bg-background">
              <PipelineFlow status={pipelineStatus} />
            </div>
            {/* Input allowed in Traceability view too */}
              <div className="px-2 sm:px-3 md:px-4 lg:px-8 py-2 sm:py-3 md:py-5 bg-gradient-to-t from-[#0A0A0A] to-transparent flex-shrink-0 sticky bottom-0 z-20 pointer-events-none">
                <form
                  onSubmit={handleSubmit}
                  className="max-w-4xl mx-auto flex items-center glass-input p-1 sm:p-1.5 md:p-2 pointer-events-auto"
                >
                  <input
                    className="flex-1 bg-transparent border-0 text-primary placeholder-muted px-2.5 sm:px-3 md:px-4 py-2 sm:py-2.5 text-[13px] sm:text-sm outline-none w-full min-w-0"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Test a query to trace its execution..."
                    disabled={loading}
                  />
                  <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="flex items-center justify-center px-3 sm:px-4 md:px-5 py-2 sm:py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg border-0 cursor-pointer transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[13px] sm:text-sm gap-1 sm:gap-1.5 ml-1 sm:ml-1.5 md:ml-2 shrink-0 active:scale-[0.97]"
                  >
                    <span className="hidden sm:inline">Trace</span> <Send size={14} />
                  </button>
                </form>
              </div>
          </div>
        )}

        {/* VIEW: KNOWLEDGE GRAPH */}
        {view === 'graph' && <GraphExplorer />}

        {/* VIEW: CHAT */}
        {view === 'chat' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-200">
              <header className="px-2 sm:px-3 md:px-4 lg:px-8 py-2 sm:py-3 md:py-4 glass-header z-10 flex-shrink-0 flex items-center justify-between gap-2">
              <div>
                <h1 className="text-sm sm:text-base md:text-lg font-semibold text-primary flex items-center gap-1.5 sm:gap-2">
                  <MessageSquare className="text-accent" size={16} />
                  Testing Interface
                </h1>
                <div className="text-[10px] sm:text-xs text-secondary mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <div className="flex items-center gap-1 sm:gap-1.5">
                    <span className="hidden sm:inline">Engine:</span> <span className="text-gray-200 font-medium px-1.5 sm:px-2 py-0.5 glass-sm text-[10px] sm:text-[11px]">{mode === 'sql' ? 'SQL Database' : mode === 'rag' ? 'Basic RAG' : mode === 'graph' ? 'Graph RAG' : 'Auditable Filing QA'}</span>
                  </div>
                  <div className="hidden sm:flex items-center gap-1 text-accent/70 font-medium text-[11px]">
                    <ShieldCheck size={12} />
                    <span>Coverage List Only</span>
                  </div>
                  <div className="flex items-center gap-1 font-medium text-[10px] sm:text-[11px] px-1.5 sm:px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 status-pulse" />
                    <span>UAT</span>
                  </div>
                </div>
              </div>
              {/* Mini Pipeline Status Indicator */}
              <div className="flex items-center gap-1.5 md:gap-2 glass-sm px-2.5 md:px-3 py-1.5 shrink-0">
                 <div className="text-[9px] md:text-[10px] font-semibold text-secondary uppercase tracking-wider mr-1 hidden xs:block">Pipeline</div>
                 {['input', 'retrieval', 'extraction', 'math', 'verification', 'output'].map(step => {
                   const s = pipelineStatus[step as keyof PipelineStatus];
                   return (
                     <div key={step} className="group relative">
                       <div className={`w-2.5 h-2.5 rounded-full transition-colors duration-500 ${
                         s === 'success' ? 'bg-emerald-500' : s === 'error' ? 'bg-red-500' : s === 'pending' ? 'bg-blue-500 status-pulse' : 'bg-gray-600'
                       }`} />
                     </div>
                   );
                 })}
              </div>
            </header>

            {/* Chat area */}
            <div className="flex-1 overflow-y-auto px-2 sm:px-3 md:px-4 lg:px-8 py-4 sm:py-6 md:py-8 flex flex-col gap-4 sm:gap-6 scroll-smooth pb-12 sm:pb-16">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center min-h-full text-center max-w-4xl mx-auto py-4">
                  <div className="w-14 h-14 bg-accent/8 rounded-xl flex items-center justify-center mb-5 border border-accent/15">
                    <MessageSquare size={28} className="text-accent" />
                  </div>
                  <h3 className="text-xl font-semibold text-primary mb-2.5 tracking-tight">
                    Financial research with an audit trail
                  </h3>
                  <p className="text-secondary text-sm leading-relaxed max-w-2xl mb-6">
                    {mode === 'auditable'
                      ? 'RAG Workbench helps analysts question SEC filings in plain English. Each answer connects filing excerpts, structured XBRL facts, deterministic calculations, and verification results so you can inspect the evidence instead of trusting a black-box response.'
                      : mode === 'graph'
                      ? 'Explore company relationships through a knowledge graph built from financial filing data. The system identifies relevant entities and shows the graph evidence used to synthesize each answer.'
                      : 'Test the basic retrieval or SQL capabilities of the platform.'}
                  </p>

                   {/* Front-and-center query composer */}
                  <form
                    onSubmit={handleSubmit}
                    className="w-full max-w-2xl mx-auto flex items-center glass-input mb-5 sm:mb-7"
                  >
                    <input
                      autoFocus
                      className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-3 sm:px-4 py-3 sm:py-3.5 text-[14px] sm:text-[15px] outline-none w-full min-w-0"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder={
                        mode === 'sql'
                          ? 'Ask a SQL question...'
                          : mode === 'rag'
                          ? 'Ask a Knowledge Base question...'
                          : mode === 'graph'
                          ? 'Ask about the knowledge graph...'
                          : "Ask about an SEC filing..."
                      }
                      disabled={loading}
                    />
                    <button
                      type="submit"
                      disabled={loading || !input.trim()}
                      className="flex items-center justify-center px-3 sm:px-5 py-3 sm:py-3.5 bg-bullish hover:bg-emerald-500 text-white rounded-lg border-0 cursor-pointer transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed font-semibold text-[13px] sm:text-sm gap-1 sm:gap-1.5 ml-1.5 sm:ml-2 shrink-0 active:scale-[0.97]"
                    >
                      <span className="hidden sm:inline">Try a query</span> <Send size={14} />
                    </button>
                  </form>

                  <div className="w-full max-w-2xl mx-auto p-3.5 mb-6 bg-amber-500/10 border border-amber-500/20 rounded-2xl flex gap-3 text-xs text-amber-200 leading-relaxed shadow-sm text-left animate-in fade-in duration-300">
                    <div className="mt-0.5 shrink-0 w-2 h-2 rounded-full bg-amber-500 status-pulse" />
                    <div>
                      <strong className="font-semibold text-amber-300 block mb-0.5">Filing Range Notice</strong>
                      Qualitative search is limited to the <strong>latest 10-K and 20-F</strong> filings by default (plus the latest 1 year of 10-Q filings for MU). Older or historical filings are not loaded by default.
                    </div>
                  </div>

                  {mode === 'auditable' && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 w-full mb-6 text-left">
                      <div className="glass p-3.5">
                        <div className="flex items-center gap-2 text-emerald-300 font-medium text-sm mb-1.5">
                          <Search size={14} />
                          Retrieve evidence
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500 m-0">
                          Finds relevant passages using hybrid semantic and keyword search across supported SEC filings.
                        </p>
                      </div>
                      <div className="glass p-3.5">
                        <div className="flex items-center gap-2 text-emerald-300 font-medium text-sm mb-1.5">
                          <Database size={14} />
                          Ground the numbers
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500 m-0">
                          Uses structured XBRL facts and deterministic math for financial metrics and period comparisons.
                        </p>
                      </div>
                      <div className="glass p-3.5">
                        <div className="flex items-center gap-2 text-emerald-300 font-medium text-sm mb-1.5">
                          <ShieldCheck size={14} />
                          Verify the answer
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500 m-0">
                          Returns sources, calculations, confidence signals, and verification status for review.
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-center gap-3 mb-6 text-xs text-muted">
                    <span>Designed for research and testing, not investment advice.</span>
                    <button
                      type="button"
                      onClick={() => setView('methodology')}
                      className="inline-flex items-center gap-1.5 text-accent hover:text-emerald-300 bg-transparent border-0 p-0 cursor-pointer font-medium"
                    >
                      <BookOpen size={14} />
                      Read the methodology
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 w-full">
                     {mode === 'graph' ? (
                       <>
                         <button onClick={() => {
                           setInput(`What are the key relationships for Micron (MU) in the knowledge graph?`);
                           if (import.meta.env.VITE_POSTHOG_KEY) {
                             getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'micron_relationships', mode }));
                           }
                         }} className="text-left px-3 sm:px-4 py-2.5 sm:py-3 glass-button text-[13px] sm:text-sm text-secondary hover:text-primary">
                           "What are Micron's key relationships?"
                         </button>
                         <button onClick={() => {
                           setInput(`Show me the suppliers and partners of NVIDIA (NVDA)`);
                           if (import.meta.env.VITE_POSTHOG_KEY) {
                             getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'nvidia_suppliers', mode }));
                           }
                         }} className="text-left px-3 sm:px-4 py-2.5 sm:py-3 glass-button text-[13px] sm:text-sm text-secondary hover:text-primary">
                           "Show me NVIDIA's suppliers and partners"
                         </button>
                       </>
                     ) : (
                       <>
                      <button onClick={() => {
                        setInput(`What was NVIDIA (NVDA)'s total revenue in the last fiscal year?`);
                        if (import.meta.env.VITE_POSTHOG_KEY) {
                          getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'nvidia_revenue', mode }));
                        }
                      }} className="text-left px-3 sm:px-4 py-2.5 sm:py-3 glass-button text-[13px] sm:text-sm text-secondary hover:text-primary">
                         "What was NVIDIA's total revenue?"
                      </button>
                      <button onClick={() => {
                        setInput(`Did Micron (MU)'s gross margin improve year-over-year?`);
                        if (import.meta.env.VITE_POSTHOG_KEY) {
                          getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'micron_margin', mode }));
                        }
                      }} className="text-left px-3 sm:px-4 py-2.5 sm:py-3 glass-button text-[13px] sm:text-sm text-secondary hover:text-primary">
                         "Did Micron's gross margin improve?"
                      </button>
                       </>
                     )}
                  </div>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex gap-2 sm:gap-3 md:gap-4 max-w-[95%] sm:max-w-[90%] md:max-w-[88%] ${
                    msg.role === 'user' ? 'self-end flex-row-reverse' : 'self-start'
                  }`}
                >
                  {/* Avatar */}
                  <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                     msg.role === 'user' ? 'bg-bullish border-emerald-500/50 text-white' : 'glass-sm text-accent'
                  }`}>
                    {msg.role === 'user' ? <Database size={13} /> : <Search size={13} />}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`px-3 sm:px-4 py-2.5 sm:py-3.5 rounded-xl leading-relaxed text-[13px] sm:text-[14.5px] min-w-0 ${
                      msg.role === 'user'
                        ? 'msg-user text-white rounded-tr-sm'
                        : 'msg-assistant text-primary rounded-tl-sm'
                    }`}
                  >
                    <div className="prose prose-invert prose-refined prose-pre:bg-background prose-pre:border prose-pre:border-border max-w-none">
                      <ReactMarkdown
                        allowedElements={['p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'a', 'br', 'hr']}
                        skipHtml
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>

                    <ChartErrorBoundary>
                      {showEvidence && msg.role === 'assistant' && msg.chart && msg.chart.data?.length > 0 && (
                        <ChartView chart={msg.chart} />
                      )}

                      {/* Only show raw XBRL chart when no backend chart is present */}
                      {showEvidence && msg.role === 'assistant' && !msg.chart && ((msg.relevant_xbrl?.length ?? 0) > 0 || (msg.xbrl_facts?.length ?? 0) > 0) && (
                        <FinancialChart facts={(msg.relevant_xbrl?.length ?? 0) > 0 ? msg.relevant_xbrl : msg.xbrl_facts} />
                      )}
                    </ChartErrorBoundary>

                    {showEvidence && msg.role === 'assistant' && (msg.sources || msg.verification || msg.xbrl_facts?.length || msg.relevant_xbrl?.length || msg.xbrl_badge || msg.math_steps?.length) && (
                      <div className="mt-3 pt-3 border-t border-border/40">
                        <AuditTrail
                          sources={msg.sources}
                          xbrl_facts={msg.xbrl_facts}
                          relevant_xbrl={msg.relevant_xbrl}
                          xbrl_badge={msg.xbrl_badge}
                          xbrl_group={msg.xbrl_group}
                          verification={msg.verification}
                          math_steps={msg.math_steps}
                        />
                      </div>
                    )}

                    {msg.role === 'assistant' && ((showExplain && (msg.what_it_means || msg.how_to_interpret)) || (msg.follow_ups && msg.follow_ups.length > 0)) && (
                      <div className="mt-3 pt-3 border-t border-border/40 space-y-2.5">
                        {/* Section 3 — What This Means */}
                        {showExplain && msg.what_it_means && (
                          <div className="glass-sm p-3.5">
                            <div className="flex items-center gap-2 mb-1.5">
                              <Lightbulb size={13} className="text-amber-400" />
                              <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">What This Means</span>
                            </div>
                            <p className="text-[13px] text-secondary leading-relaxed m-0">{msg.what_it_means}</p>
                          </div>
                        )}

                        {/* Section 4 — How to Interpret This (collapsible) */}
                        {showExplain && msg.how_to_interpret && (
                          <details className="glass-sm p-3.5 group">
                            <summary className="flex items-center gap-2 cursor-pointer list-none select-none">
                              <Info size={13} className="text-accent" />
                              <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">How to Interpret This</span>
                              <ChevronDown size={13} className="text-muted ml-auto transition-transform group-open:rotate-180" />
                            </summary>
                            <p className="text-[13px] text-secondary leading-relaxed mt-2.5 mb-0">{msg.how_to_interpret}</p>
                          </details>
                        )}

                        {/* Section 5 — Suggested Follow-Up Questions */}
                        {msg.follow_ups && msg.follow_ups.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-1.5">
                              <ArrowRight size={13} className="text-bullish" />
                              <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">{promptsGuided ? 'Guided Next Steps' : 'Suggested Follow-Ups'}</span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.follow_ups.map((q, i) => (
                                <button
                                  key={i}
                                  onClick={() => {
                                    handleSubmit(undefined, q);
                                    if (import.meta.env.VITE_POSTHOG_KEY) {
                                      getPosthog().then(p => p.capture('follow_up_click', { question: q }));
                                    }
                                  }}
                                  disabled={loading}
                                  className="text-left text-[13px] px-3 py-1.5 rounded-lg bg-bullish/8 border border-bullish/15 text-emerald-200 hover:bg-bullish/15 transition-colors disabled:opacity-50"
                                >
                                  {q}
                                </button>
                              ))}
                            </div>
                            <p className="text-[11px] text-muted mt-2.5 italic m-0">
                              SEC filings explain business fundamentals, reported financials, and disclosed risks — they don't provide investment advice, valuation, or market sentiment. Combine with other sources before making decisions.
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Management Tone Analysis */}
                    {msg.role === 'assistant' && msg.tone_analysis && Object.keys(msg.tone_analysis).length > 0 && (
                      <div className="mt-3 pt-3 border-t border-border/40">
                        <ToneAnalysis tone={msg.tone_analysis} />
                      </div>
                    )}

                    {msg.role === 'assistant' && msg.entities && msg.entities.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-border/40">
                        <div className="flex items-center gap-2 mb-2.5">
                          <Network size={13} className="text-accent" />
                          <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">Search Entities</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5 mb-3.5">
                          {msg.entities.map((entity, i) => (
                            <span key={i} className="px-2.5 py-0.5 bg-bullish/8 border border-bullish/15 rounded-md text-[13px] text-emerald-300 font-mono">
                              {entity}
                            </span>
                          ))}
                        </div>
                        {msg.triples && msg.triples.length > 0 && (
                          <>
                            <div className="flex items-center gap-2 mb-2 sm:mb-2.5 mt-3">
                              <Search size={12} className="text-accent" />
                              <span className="text-[10px] sm:text-[11px] font-semibold text-muted uppercase tracking-wider">Knowledge Graph Triples ({msg.triples.length})</span>
                            </div>
                            <div className="bg-background border border-border/50 rounded-lg overflow-hidden overflow-x-auto">
                              {msg.triples.map((triple, i) => (
                                <div
                                  key={i}
                                  className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3.5 py-1.5 sm:py-2 text-[11px] sm:text-[13px] font-mono cursor-pointer transition-colors hover:bg-bullish/8 min-w-0 ${i % 2 === 0 ? 'bg-surface/20' : ''} ${i > 0 ? 'border-t border-border/30' : ''}`}
                                  onClick={() => {
                                    setActiveTriples(msg.triples!);
                                    setOriginalTriples(msg.triples!);
                                    setModalTicker('');
                                    setGraphModalOpen(true);
                                    if (import.meta.env.VITE_POSTHOG_KEY) {
                                      getPosthog().then(p => p.capture('graph_modal_open', { triple_count: msg.triples?.length }));
                                    }
                                  }}
                                  title="Click to visualize this relationship"
                                >
                                  <span className="text-emerald-300 truncate flex-shrink min-w-0">{triple.subject}</span>
                                  <span className="text-muted flex-shrink-0">&rarr;</span>
                                  <span className="text-bullish text-[10px] sm:text-[11px] px-1 sm:px-1.5 py-0.5 bg-bullish/8 rounded border border-bullish/15 whitespace-nowrap flex-shrink-0">{triple.predicate}</span>
                                  <span className="text-muted flex-shrink-0">&rarr;</span>
                                  <span className="text-emerald-200 truncate flex-shrink min-w-0">{triple.object}</span>
                                </div>
                              ))}
                            </div>

                          </>
                        )}
                      </div>
                    )}

                    {msg.sql && (
                      <pre className="mt-3 bg-background border border-border/50 text-gray-300 rounded-lg p-2.5 sm:p-3.5 text-[11px] sm:text-[13px] font-mono whitespace-pre-wrap overflow-x-auto max-w-full">
                        <code>{msg.sql}</code>
                      </pre>
                    )}

                    {msg.data && msg.data.length > 0 && (
                      <div className="mt-3 bg-background border border-border/50 rounded-lg overflow-hidden max-w-full">
                        <div className="overflow-x-auto -mx-1 px-1">
                          <table className="w-full border-collapse text-[11px] sm:text-[13px]">
                            <thead>
                              <tr>
                                {Object.keys(msg.data[0]).map(key => (
                                  <th
                                    key={key}
                                    className="text-left px-2 sm:px-3.5 py-2 sm:py-2.5 bg-surface border-b border-border/50 text-muted font-semibold text-[10px] sm:text-[11px] uppercase tracking-wider whitespace-nowrap"
                                  >
                                    {key}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {msg.data.slice(0, 10).map((row, i) => (
                                <tr
                                  key={i}
                                  className={`transition-colors hover:bg-surface-elevated ${i % 2 === 0 ? '' : 'bg-surface/20'}`}
                                >
                                  {Object.values(row).map((val, j) => (
                                    <td
                                      key={j}
                                      className="px-3.5 py-2.5 border-b border-border/30 text-gray-300"
                                    >
                                      {typeof val === 'number'
                                        ? val.toLocaleString()
                                        : String(val ?? '')}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {msg.data.length > 10 && (
                          <div className="px-3.5 py-2 bg-surface border-t border-border/50 text-[11px] text-muted font-medium text-center uppercase tracking-wider">
                            Showing 10 of {msg.data.length} rows
                          </div>
                        )}
                      </div>
                    )}

                    {msg.role === 'assistant' && idx > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-border/30 flex items-center gap-2.5">
                        <span className="text-[11px] text-muted">Was this correct?</span>
                        <button
                          disabled={feedbackSent.has(idx)}
                          onClick={async () => {
                            setFeedbackSent(prev => new Set(prev).add(idx));
                            if (import.meta.env.VITE_POSTHOG_KEY) {
                              getPosthog().then(p => p.capture('chat_feedback', { sentiment: 'positive', message_index: idx, mode }))
                            }
                            try {
                              await submitChatFeedback(
                                messages[idx - 1]?.content ?? '',
                                msg.content,
                                true,
                              );
                            } catch {
                              setFeedbackSent(prev => { const next = new Set(prev); next.delete(idx); return next; });
                            }
                          }}
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium border-0 cursor-pointer transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed ${
                            feedbackSent.has(idx)
                              ? 'bg-bullish/10 text-bullish'
                              : 'bg-surface-elevated text-muted border border-border hover:text-secondary'
                          }`}
                        >
                          <ThumbsUp size={11} />
                          {feedbackSent.has(idx) ? 'Agreed' : 'Agree'}
                        </button>
                        <button
                          disabled={feedbackSent.has(idx)}
                          onClick={async () => {
                            setFeedbackSent(prev => new Set(prev).add(idx));
                            if (import.meta.env.VITE_POSTHOG_KEY) {
                              getPosthog().then(p => p.capture('chat_feedback', { sentiment: 'negative', message_index: idx, mode }))
                            }
                            try {
                              await submitChatFeedback(
                                messages[idx - 1]?.content ?? '',
                                msg.content,
                                false,
                              );
                            } catch {
                              setFeedbackSent(prev => { const next = new Set(prev); next.delete(idx); return next; });
                            }
                          }}
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium border-0 cursor-pointer transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed ${
                            feedbackSent.has(idx)
                              ? 'bg-bearish/10 text-bearish'
                              : 'bg-surface-elevated text-muted border border-border hover:text-secondary'
                          }`}
                        >
                          <ThumbsDown size={11} />
                          {feedbackSent.has(idx) ? 'Disagreed' : 'Disagree'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex gap-4 max-w-[88%] self-start animate-in slide-in-from-bottom-2 duration-300">
                  <div className="w-8 h-8 rounded-lg glass-sm text-accent flex items-center justify-center">
                    <Search size={14} className="animate-pulse" />
                  </div>
                  <div className="px-5 py-3 rounded-xl rounded-tl-sm glass text-gray-400 flex items-center gap-2.5 text-sm">
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent/50 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-1.5 h-1.5 rounded-full bg-accent/50 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-1.5 h-1.5 rounded-full bg-accent/50 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    Thinking...
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input bar (hidden on the empty state, where the front-and-center composer is shown) */}
            <div className={`px-2 sm:px-3 md:px-4 lg:px-8 py-2 sm:py-3 md:py-5 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/95 to-transparent flex-shrink-0 sticky bottom-0 z-20 pointer-events-none${messages.length === 0 ? ' hidden' : ''}`}>
              <form
                onSubmit={handleSubmit}
                className="max-w-4xl mx-auto flex items-center glass-input pointer-events-auto"
              >
                <input
                  className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-2.5 sm:px-3.5 md:px-4 py-2.5 sm:py-3 text-[13px] sm:text-sm outline-none w-full min-w-0"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    mode === 'sql'
                      ? 'Ask a SQL question...'
                      : mode === 'rag'
                      ? 'Ask a Knowledge Base question...'
                      : mode === 'graph'
                      ? 'Ask about the knowledge graph...'
                      : 'Ask about an SEC filing...'
                  }
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="flex items-center justify-center px-3 sm:px-4 md:px-5 py-2.5 sm:py-3 bg-bullish hover:bg-emerald-500 text-white rounded-lg border-0 cursor-pointer transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[13px] sm:text-sm gap-1 sm:gap-1.5 ml-1 sm:ml-1.5 md:ml-2 shrink-0 active:scale-[0.97]"
                >
                  <span className="hidden sm:inline">Send</span> <Send size={14} />
                </button>
              </form>
            </div>
          </div>
        )}

      </main>
      {/* Knowledge Graph Modal */}
      {graphModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-8">
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-md"
            onClick={closeGraphModal}
          />
          <div className="relative w-full max-w-6xl h-full max-h-[800px] glass-modal overflow-hidden flex flex-col animate-in zoom-in-95 duration-300">
            <header className="px-5 py-3.5 glass-header flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h3 className="text-lg font-semibold text-primary flex items-center gap-2">
                  <Network className="text-accent" size={18} />
                  Knowledge Graph Visualization
                </h3>
                <p className="text-xs text-secondary mt-0.5">Click an edge or node to see its source in the filing</p>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-secondary">Company:</span>
                  <select
                    value={modalTicker}
                    onChange={(e) => handleModalTickerChange(e.target.value)}
                    className="glass-sm text-xs text-primary bg-surface border border-border px-2.5 py-1.5 rounded-lg outline-none cursor-pointer focus:border-accent/40"
                  >
                    <option value="">(Current response)</option>
                    {graphCompanies.map((c) => (
                      <option key={c} value={c} className="bg-surface text-primary">
                        {c} — {COMPANY_NAMES[c] ?? c}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={closeGraphModal}
                  className="p-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer transition-colors"
                >
                  <X size={20} />
                </button>
              </div>
            </header>
            <div className="flex-1 min-h-0 flex relative">
              {modalLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-sm text-secondary gap-2 z-20">
                  <RefreshCcw className="animate-spin text-accent" size={18} /> Loading graph…
                </div>
              )}
              <div className="flex-1 min-w-0">
                <KnowledgeGraph triples={activeTriples} onSelect={handleGraphSelect} />
              </div>
              {evidenceSel && (
                <aside className="w-80 shrink-0 border-l border-border glass-sm overflow-y-auto p-4">
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="text-[10px] uppercase tracking-[0.12em] text-muted font-semibold">Source evidence</span>
                    <button
                      onClick={() => { setEvidenceSel(null); setEvidence(null); }}
                      className="text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <div className="text-[13px] font-mono text-primary mb-3 break-words">{evidenceSel.label}</div>
                  {evidenceLoading && <div className="text-muted text-[13px]">Loading source…</div>}
                  {!evidenceLoading && !evidenceSel.chunk_id && (
                    <div className="text-muted text-[13px]">
                      This relationship has no linked source chunk (legacy triple).
                    </div>
                  )}
                  {!evidenceLoading && evidenceSel.chunk_id && !evidence && (
                    <div className="text-muted text-[13px]">Source chunk not found.</div>
                  )}
                  {!evidenceLoading && evidence && (
                    <div className="space-y-2.5">
                      <div className="flex flex-wrap gap-1.5 text-[10px]">
                        {evidence.form_type && (
                          <span className="px-2 py-0.5 rounded bg-surface-elevated border border-border text-muted">{evidence.form_type}</span>
                        )}
                        {evidence.section_id && (
                          <span className="px-2 py-0.5 rounded bg-surface-elevated border border-border text-muted">{evidence.section_id}</span>
                        )}
                        {evidence.period_of_report && (
                          <span className="px-2 py-0.5 rounded bg-surface-elevated border border-border text-muted">{evidence.period_of_report}</span>
                        )}
                      </div>
                      <blockquote className="text-[13px] text-primary/85 leading-relaxed border-l-2 border-accent/40 pl-3 max-h-72 overflow-y-auto">
                        {evidence.excerpt.slice(0, 1200)}{evidence.excerpt.length > 1200 ? '…' : ''}
                      </blockquote>
                      {evidence.edgar_url && (
                        <a
                          href={evidence.edgar_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-block text-[11px] text-accent hover:text-emerald-300 font-medium"
                        >
                          View {evidence.ticker} on EDGAR ↗
                        </a>
                      )}
                    </div>
                  )}
                </aside>
              )}
            </div>
            <footer className="px-5 py-3 border-t border-border bg-surface/20 text-[11px] text-muted">
              Interactive node-edge graph. Drag nodes to rearrange. Click an edge/node for its filing source. Scroll to zoom.
            </footer>
          </div>
        </div>
      )}

      {/* Conjoint entry gate — first visit: standard vs personalized-by-role */}
      {gateOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg glass rounded-2xl p-6 animate-in fade-in zoom-in-95 duration-200">
            <ConjointGate
              onChosen={(p) => {
                setPrefs(p);
                setGateOpen(false);
              }}
            />
          </div>
        </div>
      )}

      {/* End-of-session study (usefulness vote; conjoint tasks for treatment) */}
      {surveyOpen && prefs && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-2xl glass rounded-2xl p-6 animate-in fade-in zoom-in-95 duration-200">
            <ConjointSurvey
              arm={prefs.arm ?? 'treatment'}
              role={prefs.role}
              onComplete={(p) => setPrefs(p)}
              onClose={() => setSurveyOpen(false)}
              onViewResults={() => {
                setSurveyOpen(false);
                setView('conjoint');
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<PortfolioHome />} />
      <Route path="/rag-overview" element={<RagOverview />} />
      <Route path="/rag/*" element={<Workbench />} />
    </Routes>
  );
}

export default App;

