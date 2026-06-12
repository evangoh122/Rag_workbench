import React, { useState, useRef, useEffect } from 'react';
import { Send, Database, BookOpen, RefreshCcw, Search, Activity, MessageSquare, BarChart3, Network, Server, Cpu, ThumbsUp, ThumbsDown, ShieldCheck, Menu, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendSqlMessage, sendRagMessage, sendAuditableRagMessage, sendGraphRagMessage } from './api/chat';
import type { ChatResponse, Source, XBRLFact } from './api/chat';
import { submitChatFeedback } from './api/review';
import ReviewQueue from './pages/ReviewQueue';
import MetricsDashboard from './pages/MetricsDashboard';
import SystemDashboard from './pages/SystemDashboard';
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

type AppView = 'chat' | 'traceability' | 'results' | 'metrics' | 'system' | 'methodology' | 'stocks' | 'audit';

type PipelineStatus = {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
};

let _posthog: Promise<typeof import('posthog-js').default> | null = null
function getPosthog() {
  if (!_posthog) _posthog = import('posthog-js').then(m => m.default)
  return _posthog
}

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
      getPosthog().then(p => p.capture('chat_send', { mode, query_length: currentInput.length }))
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
    <div className="flex h-screen w-screen overflow-hidden bg-[#0a0c10] text-gray-200 font-sans selection:bg-blue-500/30">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-72 bg-[#0f1219] border-r border-[#202532] flex flex-col p-5 shadow-[4px_0_24px_rgba(0,0,0,0.2)] 
        transition-transform duration-300 ease-in-out lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo */}
        <div className="flex items-center justify-between mb-8 px-1">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl shadow-lg shadow-blue-500/20">
              <Search size={22} className="text-white" />
            </div>
            <h2 className="m-0 text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-gray-100 to-gray-400 tracking-tight">RAG Workbench</h2>
          </div>
          <button 
            className="lg:hidden p-2 text-gray-500 hover:text-white bg-transparent border-0 cursor-pointer"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        {/* Main Navigation */}
        <nav className="flex flex-col gap-2 mb-8">
          <div className="text-[11px] font-bold text-gray-500 uppercase tracking-widest px-2 mb-2">Sections</div>
          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'stocks'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('stocks'); setSidebarOpen(false); }}
          >
            <Cpu size={18} className={view === 'stocks' ? 'text-emerald-400' : 'text-gray-500'} />
            Coverage List
          </button>
          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'chat'
                ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('chat'); setSidebarOpen(false); }}
          >
            <MessageSquare size={18} className={view === 'chat' ? 'text-blue-400' : 'text-gray-500'} />
            Testing Chat
          </button>
          
          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'traceability'
                ? 'bg-purple-500/10 text-purple-400 border-purple-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('traceability'); setSidebarOpen(false); }}
          >
            <Activity size={18} className={view === 'traceability' ? 'text-purple-400' : 'text-gray-500'} />
            Pipeline Traceability
          </button>

          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'results'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('results'); setSidebarOpen(false); }}
          >
            <BarChart3 size={18} className={view === 'results' ? 'text-emerald-400' : 'text-gray-500'} />
            Results & Testing
          </button>

          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'audit'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('audit'); setSidebarOpen(false); }}
          >
            <ShieldCheck size={18} className={view === 'audit' ? 'text-amber-400' : 'text-gray-500'} />
            Audit Log
          </button>

          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'metrics'
                ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('metrics'); setSidebarOpen(false); }}
          >
            <Activity size={18} className={view === 'metrics' ? 'text-cyan-400' : 'text-gray-500'} />
            Metrics Dashboard
          </button>

          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'system'
                ? 'bg-orange-500/10 text-orange-400 border-orange-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('system'); setSidebarOpen(false); }}
          >
            <Server size={18} className={view === 'system' ? 'text-orange-400' : 'text-gray-500'} />
            System Overview
          </button>

          <button
            className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
              view === 'methodology'
                ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#161b24]'
            }`}
            onClick={() => { setView('methodology'); setSidebarOpen(false); }}
          >
            <BookOpen size={18} className={view === 'methodology' ? 'text-indigo-400' : 'text-gray-500'} />
            Methodology
          </button>
        </nav>

        {/* Clear chat button */}
        {(view === 'chat' || view === 'traceability') && (
          <div className="mt-auto">
            <button
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-sm font-medium text-gray-400 hover:text-red-400 bg-transparent border border-[#202532] hover:border-red-900/50 hover:bg-red-500/5 cursor-pointer transition-all duration-300"
              onClick={() => {
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
      <main className="flex-1 flex flex-col h-full min-w-0 bg-[#0a0c10] relative">
        {/* Mobile Header Toggle */}
          <div className="lg:hidden flex items-center px-3 py-3 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-md sticky top-0 z-30 flex-shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 text-gray-400 hover:text-white bg-transparent border-0 cursor-pointer"
          >
            <Menu size={24} />
          </button>
          <div className="ml-4 flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg shadow-lg">
              <Search size={16} className="text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">RAG Workbench</span>
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
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm z-10 flex-shrink-0">
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
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm z-10 flex-shrink-0">
                <h1 className="text-base md:text-xl font-semibold text-white flex items-center gap-3">
                  <Activity className="text-purple-400" />
                  Pipeline Traceability
                </h1>
                <p className="text-xs md:text-sm text-gray-400 mt-1">Live visualization of the execution steps for your last query.</p>
              </header>
            <div className="flex-1 relative bg-[#0a0c10]">
              <PipelineFlow status={pipelineStatus} />
            </div>
            {/* Input allowed in Traceability view too */}
              <div className="px-3 md:px-4 lg:px-8 py-3 md:py-6 bg-gradient-to-t from-[#0a0c10] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
                <form
                  onSubmit={handleSubmit}
                  className="max-w-4xl mx-auto flex items-center bg-[#161b24]/90 backdrop-blur-md border border-[#202532] rounded-2xl p-1.5 md:p-2 shadow-2xl transition-all duration-300 focus-within:border-purple-500/50 focus-within:ring-4 focus-within:ring-purple-500/10 pointer-events-auto"
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
              <header className="px-3 md:px-4 lg:px-8 py-3 md:py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm z-10 flex-shrink-0 flex items-center justify-between gap-2">
              <div>
                <h1 className="text-base md:text-lg lg:text-xl font-semibold text-white flex items-center gap-2 md:gap-3">
                  <MessageSquare className="text-blue-400" size={18} />
                  Testing Interface
                </h1>
                <div className="text-xs lg:text-sm text-gray-400 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <div className="flex items-center gap-1.5">
                    <span className="hidden sm:inline">Engine:</span> <span className="text-gray-200 font-medium px-2 py-0.5 bg-[#161b24] rounded-md border border-[#202532]">{mode === 'sql' ? 'SQL Database' : mode === 'rag' ? 'Basic RAG' : mode === 'graph' ? 'Graph RAG' : 'Auditable Filing QA'}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-blue-400/80 font-medium">
                    <ShieldCheck size={14} />
                    <span>Coverage List Only</span>
                  </div>
                </div>
              </div>
              {/* Mini Pipeline Status Indicator */}
              <div className="flex items-center gap-1 md:gap-1.5 lg:gap-2 bg-[#161b24] px-2 md:px-3 lg:px-4 py-1.5 md:py-2 rounded-xl border border-[#202532] shadow-sm shrink-0">
                 <div className="text-[9px] md:text-[10px] lg:text-xs font-semibold text-gray-400 uppercase mr-0.5 md:mr-1 lg:mr-2 hidden xs:block">Pipeline</div>
                 {['input', 'retrieval', 'extraction', 'math', 'verification', 'output'].map(step => {
                   const s = pipelineStatus[step as keyof PipelineStatus];
                   return (
                     <div key={step} className="group relative">
                       <div className={`w-3 h-3 rounded-full border-2 border-[#161b24] shadow-sm transition-colors duration-500 ${
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
                <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto">
                  <div className="w-16 h-16 bg-blue-500/10 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_40px_rgba(59,130,246,0.15)] border border-blue-500/20">
                    <MessageSquare size={32} className="text-blue-400" />
                  </div>
                  <h3 className="text-2xl font-semibold text-white mb-3">
                    Start a Testing Session
                  </h3>
                  <p className="text-gray-400 text-base leading-relaxed mb-8">
                    {mode === 'auditable' 
                      ? `Ask questions about SEC filings. The system currently only supports stocks listed in the **Coverage List**. It will retrieve relevant excerpts, extract XBRL facts, and verify the math.`
                      : mode === 'graph'
                      ? `Ask about the knowledge graph for companies in our **Coverage List**. The system will identify entities, query the knowledge graph, and synthesize insights.`
                      : 'Test the basic retrieval or SQL capabilities of the platform.'}
                  </p>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
                     {mode === 'graph' ? (
                       <>
                         <button onClick={() => setInput(`What are the key relationships for Micron (MU) in the knowledge graph?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                           "What are Micron's key relationships?"
                         </button>
                         <button onClick={() => setInput(`Show me the suppliers and partners of NVIDIA (NVDA)`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                           "Show me NVIDIA's suppliers and partners"
                         </button>
                       </>
                     ) : (
                       <>
                     <button onClick={() => setInput(`What was NVIDIA (NVDA)'s total revenue in the last fiscal year?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                        "What was NVIDIA's total revenue?"
                     </button>
                     <button onClick={() => setInput(`Did Micron (MU)'s gross margin improve year-over-year?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
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
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm border ${
                     msg.role === 'user' ? 'bg-blue-600 border-blue-500 text-white' : 'bg-[#161b24] border-[#202532] text-blue-400'
                  }`}>
                    {msg.role === 'user' ? <Database size={18} /> : <Search size={18} />}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`px-5 py-4 rounded-2xl leading-relaxed text-[15px] shadow-sm ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-sm'
                        : 'bg-[#161b24] text-gray-200 border border-[#202532] rounded-tl-sm'
                    }`}
                  >
                    <div className="prose prose-invert prose-p:leading-relaxed prose-pre:bg-[#0a0c10] prose-pre:border prose-pre:border-[#202532] max-w-none">
                      <ReactMarkdown
                        allowedElements={['p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'a', 'br', 'hr']}
                        skipHtml
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>

                    {msg.role === 'assistant' && (msg.sources || msg.verification || msg.xbrl_facts?.length || msg.relevant_xbrl?.length || msg.xbrl_badge || msg.math_steps?.length) && (
                      <div className="mt-4 pt-4 border-t border-[#202532]/50">
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
                      <div className="mt-4 pt-4 border-t border-[#202532]/50">
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
                            <div className="bg-[#0a0c10] border border-[#202532] rounded-xl overflow-hidden shadow-inner">
                              {msg.triples.map((triple, i) => (
                                <div key={i} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-mono ${i % 2 === 0 ? 'bg-[#0c0e14]' : ''} ${i > 0 ? 'border-t border-[#202532]/50' : ''}`}>
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
                      <pre className="mt-4 bg-[#0a0c10] border border-[#202532] text-gray-300 rounded-xl p-4 text-sm font-mono whitespace-pre-wrap overflow-x-auto shadow-inner">
                        <code>{msg.sql}</code>
                      </pre>
                    )}

                    {msg.data && msg.data.length > 0 && (
                      <div className="mt-4 bg-[#0a0c10] border border-[#202532] rounded-xl overflow-hidden shadow-inner">
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-sm">
                            <thead>
                              <tr>
                                {Object.keys(msg.data[0]).map(key => (
                                  <th
                                    key={key}
                                    className="text-left px-4 py-3 bg-[#13171f] border-b border-[#202532] text-gray-400 font-semibold"
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
                                  className={`transition-colors hover:bg-[#161b24] ${i % 2 === 0 ? '' : 'bg-[#0c0e14]'}`}
                                >
                                  {Object.values(row).map((val, j) => (
                                    <td
                                      key={j}
                                      className="px-4 py-3 border-b border-[#202532]/50 text-gray-300"
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
                          <div className="px-4 py-2.5 bg-[#13171f] border-t border-[#202532] text-xs text-gray-500 font-medium text-center uppercase tracking-wider">
                            Showing 10 of {msg.data.length} rows
                          </div>
                        )}
                      </div>
                    )}

                    {msg.role === 'assistant' && idx > 0 && (
                      <div className="mt-4 pt-3 border-t border-[#202532]/50 flex items-center gap-3">
                        <span className="text-xs text-gray-500">Was this correct?</span>
                        <button
                          disabled={feedbackSent.has(idx)}
                          onClick={async () => {
                            setFeedbackSent(prev => new Set(prev).add(idx));
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
                              : 'bg-[#1c222e] text-gray-400 hover:bg-emerald-500/10 hover:text-emerald-400'
                          }`}
                        >
                          <ThumbsUp size={12} />
                          {feedbackSent.has(idx) ? 'Agreed' : 'Agree'}
                        </button>
                        <button
                          disabled={feedbackSent.has(idx)}
                          onClick={async () => {
                            setFeedbackSent(prev => new Set(prev).add(idx));
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
                              : 'bg-[#1c222e] text-gray-400 hover:bg-red-500/10 hover:text-red-400'
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
                  <div className="w-10 h-10 rounded-xl bg-[#161b24] border border-[#202532] text-blue-400 flex items-center justify-center shadow-sm">
                    <Search size={18} className="animate-pulse" />
                  </div>
                  <div className="px-6 py-4 rounded-2xl rounded-tl-sm bg-[#161b24] text-gray-400 border border-[#202532] flex items-center gap-3">
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
            <div className="px-3 md:px-4 lg:px-8 py-3 md:py-6 bg-gradient-to-t from-[#0a0c10] via-[#0a0c10] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
              <form
                onSubmit={handleSubmit}
                className="max-w-4xl mx-auto flex items-center bg-[#161b24]/90 backdrop-blur-md border border-[#202532] rounded-2xl p-1.5 md:p-2 shadow-2xl transition-all duration-300 focus-within:border-blue-500/50 focus-within:ring-4 focus-within:ring-blue-500/10 pointer-events-auto"
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
    </div>
  );
}

export default App;

