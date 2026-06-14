import React, { useState, useRef, useEffect } from 'react';
import { Send, Database, BookOpen, RefreshCcw, Search, Activity, MessageSquare, BarChart3, Network, Server, Cpu, ThumbsUp, ThumbsDown, ShieldCheck, Menu, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendSqlMessage, sendRagMessage, sendAuditableRagMessage, sendGraphRagMessage } from './api/chat';
import type { ChatResponse, Source, XBRLFact } from './api/chat';
import { submitChatFeedback } from './api/review';
import ReviewQueue from './pages/ReviewQueue';
import MetricsDashboard from './pages/MetricsDashboard';
import SystemDashboard from './pages/SystemDashboard';
import ProductAnalytics from './pages/ProductAnalytics';
import Methodology from './pages/Methodology';
import StocksList from './pages/StocksList';
import AuditLog from './pages/AuditLog';
import DriftAlert from './components/DriftAlert';
import AuditTrail from './components/AuditTrail';
import PipelineFlow from './components/PipelineFlow';

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
  triples?: Record<string, string>[];
}

type AppView = 'chat' | 'traceability' | 'results' | 'metrics' | 'system' | 'methodology' | 'stocks' | 'audit' | 'analytics';

type PipelineStatus = {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
};

import { getPosthog } from './utils/posthog'

import KnowledgeGraph from './components/KnowledgeGraph';

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, _setMode] = useState<'sql' | 'rag' | 'auditable' | 'graph'>('auditable');
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<AppView>('chat');
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({});
  const [ticker, _setTicker] = useState('MU');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<Set<number>>(new Set());
  const [graphModalOpen, setGraphModalOpen] = useState(false);
  const [activeTriples, setActiveTriples] = useState<any[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (import.meta.env.VITE_POSTHOG_KEY) {
      getPosthog().then(p => p.capture('$pageview', { view }))
    }
  }, [view]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    if (mode === 'auditable') {
      setPipelineStatus({ input: 'success', retrieval: 'pending' });
      // If the user submits from the traceability view, we might want to stay there or move them.
      // We'll keep them wherever they are.
    }
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = input;
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
        data = await sendAuditableRagMessage(currentInput, ticker);
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
    <div className="flex h-screen w-screen overflow-hidden bg-background text-primary font-sans selection:bg-blue-500/30">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-72 bg-surface border-r border-border flex flex-col p-5 
        transition-transform duration-300 ease-in-out lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between mb-8 px-1">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl">
              <Search size={22} className="text-white" />
            </div>
            <h2 className="m-0 text-xl font-bold text-primary tracking-tight">RAG Workbench</h2>
          </div>
          <button 
            className="lg:hidden p-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        {/* Main Navigation */}
        <nav className="flex flex-col gap-6 mb-8 overflow-y-auto">
          {/* USER SECTION */}
          <div>
            <div className="text-[11px] font-bold text-secondary uppercase tracking-widest px-2 mb-3">For Users</div>
            <div className="flex flex-col gap-1.5">
              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'stocks'
                    ? 'bg-bullish/10 text-bullish border-bullish/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('stocks'); 
                  setSidebarOpen(false); 
                }}
              >
                <Cpu size={18} className={view === 'stocks' ? 'text-bullish' : 'text-secondary'} />
                Coverage List
              </button>
              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'chat'
                    ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('chat'); 
                  setSidebarOpen(false); 
                }}
              >
                <MessageSquare size={18} className={view === 'chat' ? 'text-blue-400' : 'text-secondary'} />
                Testing Chat
              </button>
              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'traceability'
                    ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('traceability'); 
                  setSidebarOpen(false); 
                }}
              >
                <Activity size={18} className={view === 'traceability' ? 'text-purple-400' : 'text-secondary'} />
                Pipeline Traceability
              </button>
              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'methodology'
                    ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('methodology'); 
                  setSidebarOpen(false); 
                }}
              >
                <BookOpen size={18} className={view === 'methodology' ? 'text-indigo-400' : 'text-secondary'} />
                Methodology
              </button>
            </div>
          </div>

          {/* DIAGNOSTIC SECTION */}
          <div>
            <div className="text-[11px] font-bold text-secondary uppercase tracking-widest px-2 mb-3">Audit & Diagnostics</div>
            <div className="flex flex-col gap-1.5">
              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'results'
                    ? 'bg-bullish/10 text-bullish border-bullish/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('results'); 
                  setSidebarOpen(false); 
                }}
              >
                <BarChart3 size={18} className={view === 'results' ? 'text-bullish' : 'text-secondary'} />
                Results & Testing
              </button>

              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'audit'
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('audit'); 
                  setSidebarOpen(false); 
                }}
              >
                <ShieldCheck size={18} className={view === 'audit' ? 'text-amber-400' : 'text-secondary'} />
                Audit Log
              </button>

              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'metrics'
                    ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('metrics'); 
                  setSidebarOpen(false); 
                }}
              >
                <Activity size={18} className={view === 'metrics' ? 'text-cyan-400' : 'text-secondary'} />
                Metrics Dashboard
              </button>

              <button
                className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                  view === 'system'
                    ? 'bg-orange-500/10 text-orange-400 border-orange-500/20'
                    : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
                }`}
                onClick={() => { 
                  setView('system'); 
                  setSidebarOpen(false); 
                }}
              >
                <Server size={18} className={view === 'system' ? 'text-orange-400' : 'text-secondary'} />
                System Overview
              </button>
            </div>
          </div>
        </nav>

        {/* Clear chat button */}
        {(view === 'chat' || view === 'traceability') && (
          <div className="mt-auto">
            <button
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-sm font-medium text-gray-400 hover:text-red-400 bg-transparent border border-border hover:border-red-900/50 hover:bg-red-500/5 cursor-pointer transition-all duration-300"
              onClick={() => {
                if (import.meta.env.VITE_POSTHOG_KEY) {
                  getPosthog().then(p => p.capture('session_reset', { message_count: messages.length, view }));
                }
                setMessages([]);
                setPipelineStatus({});
                setFeedbackSent(new Set());
              }}
            >
              <RefreshCcw size={16} />
              Reset Session
            </button>
          </div>
        )}

        {/* Drift alert at bottom of sidebar */}
        <div className={(view === 'results' || view === 'metrics') ? 'mt-auto' : 'mt-4'}>
          <DriftAlert />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full min-w-0 bg-background relative">
        {/* Mobile Header Toggle */}
          <div className="lg:hidden flex items-center px-3 py-3 border-b border-border bg-surface/50 backdrop-blur-md sticky top-0 z-30 flex-shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
          >
            <Menu size={24} />
          </button>
          <div className="ml-4 flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <Search size={16} className="text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight text-primary">RAG Workbench</span>
          </div>
        </div>
        
        {/* VIEW: AUDIT LOG */}
        {view === 'audit' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300 overflow-hidden">
            <AuditLog />
          </div>
        )}

        {/* VIEW: RESULTS */}
        {view === 'results' && (
          <div className="flex-1 overflow-hidden animate-in fade-in duration-300">
            <ReviewQueue />
          </div>
        )}

        {/* VIEW: METRICS */}
        {view === 'metrics' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
            <MetricsDashboard />
          </div>
        )}

        {/* VIEW: PRODUCT ANALYTICS */}
        {view === 'analytics' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
            <ProductAnalytics />
          </div>
        )}

        {/* VIEW: SYSTEM OVERVIEW */}
        {view === 'system' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
            <SystemDashboard />
          </div>
        )}

        {/* VIEW: METHODOLOGY */}
        {view === 'methodology' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
            <Methodology />
          </div>
        )}

        {/* VIEW: STOCKS */}
        {view === 'stocks' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300 overflow-y-auto">
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm z-10 flex-shrink-0">
                <h1 className="text-base md:text-xl font-semibold text-white flex items-center gap-3">
                  <Cpu className="text-emerald-400" />
                  Coverage List
                </h1>
              </header>
            <StocksList />
          </div>
        )}

        {/* VIEW: TRACEABILITY */}
        {view === 'traceability' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm z-10 flex-shrink-0">
                <h1 className="text-base md:text-xl font-semibold text-white flex items-center gap-3">
                  <Activity className="text-purple-400" />
                  Pipeline Traceability
                </h1>
                <p className="text-xs md:text-sm text-gray-400 mt-1">Live visualization of the execution steps for your last query.</p>
              </header>
            <div className="flex-1 relative bg-background">
              <PipelineFlow status={pipelineStatus} />
            </div>
            {/* Input allowed in Traceability view too */}
              <div className="px-3 md:px-4 lg:px-8 py-3 md:py-6 bg-gradient-to-t from-[#0A0A0A] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
                <form
                  onSubmit={handleSubmit}
                  className="max-w-4xl mx-auto flex items-center bg-surface-elevated/90 backdrop-blur-md border border-border rounded-2xl p-1.5 md:p-2 shadow-none transition-all duration-300 focus-within:border-purple-500/50 focus-within:ring-4 focus-within:ring-purple-500/10 pointer-events-auto"
                >
                  <input
                    className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-3 md:px-4 py-3 text-base outline-none w-full min-w-0"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Test a query to trace its execution..."
                    disabled={loading}
                  />
                  <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="flex items-center justify-center px-4 md:px-6 py-3 bg-purple-600 hover:bg-purple-500 text-white rounded-xl border-0 cursor-pointer transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed font-medium gap-1.5 md:gap-2 ml-1.5 md:ml-2 shrink-0"
                  >
                    Trace <Send size={16} />
                  </button>
                </form>
              </div>
          </div>
        )}

        {/* VIEW: CHAT */}
        {view === 'chat' && (
          <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-border bg-surface/50 backdrop-blur-sm z-10 flex-shrink-0 flex items-center justify-between gap-2">
              <div>
                <h1 className="text-base md:text-lg lg:text-xl font-semibold text-white flex items-center gap-2 md:gap-3">
                  <MessageSquare className="text-blue-400" size={18} />
                  Testing Interface
                </h1>
                <div className="text-xs lg:text-sm text-gray-400 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <div className="flex items-center gap-1.5">
                    <span className="hidden sm:inline">Engine:</span> <span className="text-gray-200 font-medium px-2 py-0.5 bg-surface-elevated rounded-md border border-border">{mode === 'sql' ? 'SQL Database' : mode === 'rag' ? 'Basic RAG' : mode === 'graph' ? 'Graph RAG' : 'Auditable Filing QA'}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-blue-400/80 font-medium">
                    <ShieldCheck size={14} />
                    <span>Coverage List Only</span>
                  </div>
                </div>
              </div>
              {/* Mini Pipeline Status Indicator */}
              <div className="flex items-center gap-1 md:gap-1.5 lg:gap-2 bg-surface-elevated px-2 md:px-3 lg:px-4 py-1.5 md:py-2 rounded-xl border border-border shadow-none shrink-0">
                 <div className="text-[9px] md:text-[10px] lg:text-xs font-semibold text-gray-400 uppercase mr-0.5 md:mr-1 lg:mr-2 hidden xs:block">Pipeline</div>
                 {['input', 'retrieval', 'extraction', 'math', 'verification', 'output'].map(step => {
                   const s = pipelineStatus[step as keyof PipelineStatus];
                   return (
                     <div key={step} className="group relative">
                       <div className={`w-3 h-3 rounded-full border-2 border-surface-elevated shadow-none transition-colors duration-500 ${
                         s === 'success' ? 'bg-emerald-500' : s === 'error' ? 'bg-red-500' : s === 'pending' ? 'bg-blue-500 animate-pulse' : 'bg-gray-600'
                       }`} />
                     </div>
                   );
                 })}
              </div>
            </header>

            {/* Chat area */}
            <div className="flex-1 overflow-y-auto px-3 md:px-4 lg:px-8 py-6 md:py-8 flex flex-col gap-6 md:gap-8 scroll-smooth pb-28 md:pb-32">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center min-h-full text-center max-w-4xl mx-auto py-4">
                  <div className="w-16 h-16 bg-blue-500/10 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_40px_rgba(59,130,246,0.15)] border border-blue-500/20">
                    <MessageSquare size={32} className="text-blue-400" />
                  </div>
                  <h3 className="text-2xl font-semibold text-white mb-3">
                    Financial research with an audit trail
                  </h3>
                  <p className="text-gray-400 text-base leading-relaxed max-w-2xl mb-6">
                    {mode === 'auditable' 
                      ? 'RAG Workbench helps analysts question SEC filings in plain English. Each answer connects filing excerpts, structured XBRL facts, deterministic calculations, and verification results so you can inspect the evidence instead of trusting a black-box response.'
                      : mode === 'graph'
                      ? 'Explore company relationships through a knowledge graph built from financial filing data. The system identifies relevant entities and shows the graph evidence used to synthesize each answer.'
                      : 'Test the basic retrieval or SQL capabilities of the platform.'}
                  </p>

                  {mode === 'auditable' && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full mb-6 text-left">
                      <div className="rounded-xl border border-border bg-surface p-4">
                        <div className="flex items-center gap-2 text-blue-300 font-semibold text-sm mb-2">
                          <Search size={16} />
                          Retrieve evidence
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500">
                          Finds relevant passages using hybrid semantic and keyword search across supported SEC filings.
                        </p>
                      </div>
                      <div className="rounded-xl border border-border bg-surface p-4">
                        <div className="flex items-center gap-2 text-purple-300 font-semibold text-sm mb-2">
                          <Database size={16} />
                          Ground the numbers
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500">
                          Uses structured XBRL facts and deterministic math for financial metrics and period comparisons.
                        </p>
                      </div>
                      <div className="rounded-xl border border-border bg-surface p-4">
                        <div className="flex items-center gap-2 text-emerald-300 font-semibold text-sm mb-2">
                          <ShieldCheck size={16} />
                          Verify the answer
                        </div>
                        <p className="text-xs leading-relaxed text-gray-500">
                          Returns sources, calculations, confidence signals, and verification status for review.
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-center gap-3 mb-6 text-xs text-gray-500">
                    <span>Designed for research and testing, not investment advice.</span>
                    <button
                      type="button"
                      onClick={() => setView('methodology')}
                      className="inline-flex items-center gap-1.5 text-indigo-300 hover:text-indigo-200 bg-transparent border-0 p-0 cursor-pointer font-medium"
                    >
                      <BookOpen size={14} />
                      Read the methodology
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
                     {mode === 'graph' ? (
                       <>
                         <button onClick={() => {
                           setInput(`What are the key relationships for Micron (MU) in the knowledge graph?`);
                           if (import.meta.env.VITE_POSTHOG_KEY) {
                             getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'micron_relationships', mode }));
                           }
                         }} className="text-left px-4 py-3 bg-surface-elevated border-border rounded-xl transition-all text-sm text-secondary">
                           "What are Micron's key relationships?"
                         </button>
                         <button onClick={() => {
                           setInput(`Show me the suppliers and partners of NVIDIA (NVDA)`);
                           if (import.meta.env.VITE_POSTHOG_KEY) {
                             getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'nvidia_suppliers', mode }));
                           }
                         }} className="text-left px-4 py-3 bg-surface-elevated border-border rounded-xl transition-all text-sm text-secondary">
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
                     }} className="text-left px-4 py-3 bg-surface-elevated border-border rounded-xl transition-all text-sm text-secondary">
                        "What was NVIDIA's total revenue?"
                     </button>
                     <button onClick={() => {
                       setInput(`Did Micron (MU)'s gross margin improve year-over-year?`);
                       if (import.meta.env.VITE_POSTHOG_KEY) {
                         getPosthog().then(p => p.capture('suggestion_click', { suggestion: 'micron_margin', mode }));
                       }
                     }} className="text-left px-4 py-3 bg-surface-elevated border-border rounded-xl transition-all text-sm text-secondary">
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
                  className={`flex gap-3 md:gap-5 max-w-full md:max-w-[90%] ${
                    msg.role === 'user' ? 'self-end flex-row-reverse' : 'self-start'
                  }`}
                >
                  {/* Avatar */}
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-none border ${
                     msg.role === 'user' ? 'bg-blue-600 border-blue-500 text-white' : 'bg-surface-elevated border-border text-blue-400'
                  }`}>
                    {msg.role === 'user' ? <Database size={18} /> : <Search size={18} />}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`px-5 py-4 rounded-2xl leading-relaxed text-[15px] shadow-none ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-sm'
                        : 'bg-surface-elevated text-primary border border-border rounded-tl-sm'
                    }`}
                  >
                    <div className="prose prose-invert prose-p:leading-relaxed prose-pre:bg-background prose-pre:border prose-pre:border-border max-w-none">
                      <ReactMarkdown
                        allowedElements={['p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'a', 'br', 'hr']}
                        skipHtml
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>

                    {msg.role === 'assistant' && (msg.sources || msg.verification || msg.xbrl_facts?.length || msg.relevant_xbrl?.length || msg.xbrl_badge || msg.math_steps?.length) && (
                      <div className="mt-4 pt-4 border-t border-border/50">
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

                    {msg.role === 'assistant' && msg.entities && msg.entities.length > 0 && (
                      <div className="mt-4 pt-4 border-t border-border/50">
                        <div className="flex items-center gap-2 mb-3">
                          <Network size={14} className="text-indigo-400" />
                          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Search Entities</span>
                        </div>
                        <div className="flex flex-wrap gap-2 mb-4">
                          {msg.entities.map((entity, i) => (
                            <span key={i} className="px-3 py-1 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-sm text-indigo-300 font-mono">
                              {entity}
                            </span>
                          ))}
                        </div>
                        {msg.triples && msg.triples.length > 0 && (
                          <>
                            <div className="flex items-center gap-2 mb-3 mt-4">
                              <Search size={14} className="text-blue-400" />
                              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Knowledge Graph Triples ({msg.triples.length})</span>
                            </div>
                            <div className="bg-background border border-border rounded-xl overflow-hidden shadow-none">
                              {msg.triples.map((triple, i) => (
                                <div 
                                  key={i} 
                                  className={`flex items-center gap-2 px-4 py-2.5 text-sm font-mono cursor-pointer transition-colors hover:bg-indigo-500/10 ${i % 2 === 0 ? 'bg-surface/30' : ''} ${i > 0 ? 'border-t border-border/50' : ''}`}
                                  onClick={() => {
                                    setActiveTriples(msg.triples!);
                                    setGraphModalOpen(true);
                                    if (import.meta.env.VITE_POSTHOG_KEY) {
                                      getPosthog().then(p => p.capture('graph_modal_open', { triple_count: msg.triples?.length }));
                                    }
                                  }}
                                  title="Click to visualize this relationship"
                                >
                                  <span className="text-blue-300">{triple.subject}</span>
                                  <span className="text-gray-500">&rarr;</span>
                                  <span className="text-emerald-400 text-xs px-1.5 py-0.5 bg-emerald-500/10 rounded border border-emerald-500/20">{triple.predicate}</span>
                                  <span className="text-gray-500">&rarr;</span>
                                  <span className="text-purple-300">{triple.object}</span>
                                </div>
                              ))}
                            </div>

                          </>
                        )}
                      </div>
                    )}

                    {msg.sql && (
                      <pre className="mt-4 bg-background border border-border text-gray-300 rounded-xl p-4 text-sm font-mono whitespace-pre-wrap overflow-x-auto shadow-none">
                        <code>{msg.sql}</code>
                      </pre>
                    )}

                    {msg.data && msg.data.length > 0 && (
                      <div className="mt-4 bg-background border border-border rounded-xl overflow-hidden shadow-none">
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-sm">
                            <thead>
                              <tr>
                                {Object.keys(msg.data[0]).map(key => (
                                  <th
                                    key={key}
                                    className="text-left px-4 py-3 bg-surface border-b border-border text-secondary font-semibold"
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
                                  className={`transition-colors hover:bg-surface-elevated ${i % 2 === 0 ? '' : 'bg-surface/30'}`}
                                >
                                  {Object.values(row).map((val, j) => (
                                    <td
                                      key={j}
                                      className="px-4 py-3 border-b border-border/50 text-gray-300"
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
                          <div className="px-4 py-2.5 bg-surface border-t border-border text-xs text-secondary font-medium text-center uppercase tracking-wider">
                            Showing 10 of {msg.data.length} rows
                          </div>
                        )}
                      </div>
                    )}

                    {msg.role === 'assistant' && idx > 0 && (
                      <div className="mt-4 pt-3 border-t border-border/50 flex items-center gap-3">
                        <span className="text-xs text-gray-500">Was this correct?</span>
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
                          className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border-0 cursor-pointer transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                            feedbackSent.has(idx)
                              ? 'bg-emerald-500/10 text-emerald-400'
                              : 'bg-surface-elevated text-secondary border border-border shadow-none transition-colors duration-500'
                          }`}
                        >
                          <ThumbsUp size={12} />
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
                          className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border-0 cursor-pointer transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                            feedbackSent.has(idx)
                              ? 'bg-red-500/10 text-red-400'
                              : 'bg-surface-elevated text-secondary border border-border shadow-none transition-colors duration-500'
                          }`}
                        >
                          <ThumbsDown size={12} />
                          {feedbackSent.has(idx) ? 'Disagreed' : 'Disagree'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex gap-5 max-w-[90%] self-start animate-in slide-in-from-bottom-2 duration-300">
                  <div className="w-10 h-10 rounded-xl bg-surface-elevated border border-border text-blue-400 flex items-center justify-center shadow-none">
                    <Search size={18} className="animate-pulse" />
                  </div>
                  <div className="px-6 py-4 rounded-2xl rounded-tl-sm bg-surface-elevated text-gray-400 border border-border flex items-center gap-3">
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 rounded-full bg-blue-500/50 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    Thinking...
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input bar */}
            <div className="px-3 md:px-4 lg:px-8 py-3 md:py-6 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
              <form
                onSubmit={handleSubmit}
                className="max-w-4xl mx-auto flex items-center bg-surface-elevated border-border rounded-xl transition-all duration-300 focus-within:border-blue-500/50 focus-within:ring-4 focus-within:ring-blue-500/10 pointer-events-auto"
              >
                <input
                  className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-3 md:px-4 py-3 text-base outline-none w-full min-w-0"
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
                  className="flex items-center justify-center px-4 md:px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl border-0 cursor-pointer transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed font-medium gap-1.5 md:gap-2 ml-1.5 md:ml-2 shrink-0"
                >
                  Send <Send size={16} />
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
            onClick={() => setGraphModalOpen(false)}
          />
          <div className="relative w-full max-w-6xl h-full max-h-[800px] bg-background border border-border rounded-3xl overflow-hidden flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
            <header className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface/50 backdrop-blur-sm">
              <div>
                <h3 className="text-xl font-bold text-primary flex items-center gap-3">
                  <Network className="text-indigo-400" />
                  Knowledge Graph Visualization
                </h3>
                <p className="text-sm text-secondary mt-1">Relationships extracted from financial filings</p>
              </div>
              <button 
                onClick={() => setGraphModalOpen(false)}
                className="p-2 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer transition-colors"
              >
                <X size={24} />
              </button>
            </header>
            <div className="flex-1 min-h-0">
              <KnowledgeGraph triples={activeTriples} />
            </div>
            <footer className="px-6 py-4 border-t border-border bg-surface/30 text-xs text-secondary/60">
              Interactive node-edge graph. Drag nodes to rearrange. Use scroll to zoom.
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

