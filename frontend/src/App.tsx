import React, { useState, useRef, useEffect } from 'react';
import { Send, Database, BookOpen, RefreshCcw, Search, ClipboardList, ShieldCheck } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendSqlMessage, sendRagMessage, sendAuditableRagMessage } from './api/chat';
import type { ChatResponse } from './api/chat';
import ReviewQueue from './pages/ReviewQueue';
import DriftAlert from './components/DriftAlert';
import AuditTrail from './components/AuditTrail';
import PipelineFlow from './components/PipelineFlow';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: Record<string, unknown>[];
  sources?: any[];
  xbrl_facts?: any[];
  verification?: {
    status: string;
    reasoning: string;
  };
  math_steps?: string[];
}

type AppView = 'chat' | 'review';

type PipelineStatus = {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
};

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<'sql' | 'rag' | 'auditable'>('auditable');
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<AppView>('chat');
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({});
  const [ticker, setTicker] = useState('AAPL');
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    if (mode === 'auditable') {
      setPipelineStatus({ input: 'success', retrieval: 'pending' });
    }
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = input;
    setInput('');
    setLoading(true);

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));

      let data: ChatResponse;
      if (mode === 'sql') {
        data = await sendSqlMessage(currentInput, history);
      } else if (mode === 'rag') {
        data = await sendRagMessage(currentInput, history);
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
        verification: data.verification,
        math_steps: data.math_steps,
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: unknown) {
      setPipelineStatus({
        input: 'success',
        retrieval: 'error',
      });
      const message =
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred';
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${message}`,
          type: 'error',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0e1117] text-white font-sans">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-[#131926] border-r border-[#2a3246] flex flex-col p-5">
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-8">
          <Search size={24} className="text-blue-500" />
          <h2 className="m-0 text-lg font-semibold">RAG Workbench</h2>
        </div>

        {/* Mode toggle (only visible in chat view) */}
        {view === 'chat' && (
          <div className="flex flex-col gap-2 mb-6">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-1">Engine Mode</div>
            <div className="grid grid-cols-1 gap-1">
              <button
                className={`flex items-center gap-2.5 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                  mode === 'auditable'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#1c2130]'
                }`}
                onClick={() => setMode('auditable')}
              >
                <ShieldCheck size={16} />
                Auditable RAG
              </button>
              <button
                className={`flex items-center gap-2.5 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                  mode === 'sql'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#1c2130]'
                }`}
                onClick={() => setMode('sql')}
              >
                <Database size={16} />
                SQL
              </button>
              <button
                className={`flex items-center gap-2.5 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                  mode === 'rag'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-[#1c2130]'
                }`}
                onClick={() => setMode('rag')}
              >
                <BookOpen size={16} />
                Basic RAG
              </button>
            </div>
          </div>
        )}

        {/* Ticker Selector */}
        {view === 'chat' && mode === 'auditable' && (
          <div className="mb-6 px-1">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Company Ticker</label>
            <input 
              type="text" 
              value={ticker} 
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-full bg-[#1c2130] border border-[#2a3246] rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              placeholder="e.g. AAPL"
            />
          </div>
        )}

        {/* Review Queue nav link */}
        <button
          className={`w-full flex items-center gap-2.5 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 cursor-pointer border-0 mb-2 ${
            view === 'review'
              ? 'bg-[#1c2130] text-blue-400'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1c2130] bg-transparent'
          }`}
          onClick={() => setView('review')}
        >
          <ClipboardList size={16} />
          Review Queue
        </button>

        {/* Back to chat button when in review view */}
        {view === 'review' && (
          <button
            className="w-full flex items-center gap-2.5 py-2 px-3 rounded-md text-sm font-medium text-gray-400 hover:text-gray-200 bg-transparent hover:bg-[#1c2130] border-0 cursor-pointer transition-all duration-200 mb-2"
            onClick={() => setView('chat')}
          >
            <Search size={16} />
            Back to Chat
          </button>
        )}

        {/* Clear chat button — only in chat view */}
        {view === 'chat' && (
          <div className="mt-auto">
            <button
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm text-gray-400 hover:text-gray-200 bg-transparent border-0 cursor-pointer transition-all duration-200 hover:bg-[#1c2130]"
              onClick={() => {
                setMessages([]);
                setPipelineStatus({});
              }}
            >
              <RefreshCcw size={16} />
              Clear Chat
            </button>
          </div>
        )}

        {/* Drift alert at bottom of sidebar */}
        <DriftAlert />
      </aside>

      {/* Main content */}
      {view === 'review' ? (
        <ReviewQueue />
      ) : (
        <div className="flex-1 flex flex-row h-full min-w-0">
          {/* Chat Pane */}
          <div className="flex-1 flex flex-col h-full border-r border-[#2a3246]">
            {/* Header */}
            <header className="px-6 py-4 border-b border-[#2a3246] flex items-center justify-between flex-shrink-0">
              <div className="text-sm text-gray-400">
                Mode:{' '}
                <strong className="text-white">
                  {mode === 'sql' ? 'Database (SQL)' : mode === 'rag' ? 'Knowledge Base (RAG)' : 'Auditable Filing QA'}
                </strong>
              </div>
            </header>

            {/* Chat area */}
            <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-6">
              {messages.length === 0 && (
                <div className="text-center mt-24 text-gray-400">
                  <h3 className="text-lg font-medium mb-2">
                    How can I help you with your financial data today?
                  </h3>
                  <p className="text-sm">
                    {mode === 'auditable' 
                      ? `Ask a question about ${ticker}'s latest 10-K filing.`
                      : 'Try asking: "Show me AAPL closing prices for the last 30 days"'}
                  </p>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex gap-4 max-w-[95%] ${
                    msg.role === 'user' ? 'self-end flex-row-reverse' : 'self-start'
                  }`}
                >
                  <div
                    className={`px-4 py-3 rounded-2xl leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-[#1e293b] text-gray-100'
                    }`}
                  >
                    <ReactMarkdown
                      allowedElements={['p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'a', 'br', 'hr']}
                      skipHtml
                    >
                      {msg.content}
                    </ReactMarkdown>

                    {msg.role === 'assistant' && (msg.sources || msg.verification) && (
                      <AuditTrail
                        sources={msg.sources}
                        xbrl_facts={msg.xbrl_facts}
                        verification={msg.verification}
                        math_steps={msg.math_steps}
                      />
                    )}

                    {msg.sql && (
                      <pre className="mt-3 bg-black text-gray-300 rounded p-3 text-sm font-mono whitespace-pre-wrap overflow-x-auto">
                        <code>{msg.sql}</code>
                      </pre>
                    )}

                    {msg.data && msg.data.length > 0 && (
                      <div className="mt-3 bg-[#0a0c10] border border-[#2a3246] rounded-lg overflow-x-auto">
                        <table className="w-full border-collapse text-sm">
                          <thead>
                            <tr>
                              {Object.keys(msg.data[0]).map(key => (
                                <th
                                  key={key}
                                  className="text-left px-3 py-3 bg-[#161b22] border-b border-[#2a3246] text-gray-400 font-medium"
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
                                className={i % 2 === 0 ? '' : 'bg-[#0d1117]'}
                              >
                                {Object.values(row).map((val, j) => (
                                  <td
                                    key={j}
                                    className="px-3 py-3 border-b border-[#2a3246]"
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
                        {msg.data.length > 10 && (
                          <div className="px-3 py-2 text-xs text-gray-400 text-center">
                            Showing 10 of {msg.data.length} rows
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex gap-4 max-w-[85%] self-start">
                  <div className="px-4 py-3 rounded-2xl bg-[#1e293b] text-gray-100 italic opacity-70">
                    Thinking...
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input bar */}
            <div className="px-6 py-6 bg-[#0e1117] flex-shrink-0">
              <form
                onSubmit={handleSubmit}
                className="max-w-3xl mx-auto flex items-center bg-[#1c2130] border border-[#2a3246] rounded-xl px-4 py-2 transition-colors duration-200 focus-within:border-blue-600"
              >
                <input
                  className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 py-3 text-base outline-none"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    mode === 'sql'
                      ? 'Ask a SQL question...'
                      : mode === 'rag' 
                      ? 'Ask a Knowledge Base question...'
                      : `Ask about ${ticker}'s SEC filing...`
                  }
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="flex items-center justify-center w-9 h-9 bg-blue-600 text-white rounded-lg border-0 cursor-pointer transition-opacity duration-200 disabled:opacity-50 disabled:cursor-not-allowed ml-2"
                >
                  <Send size={18} />
                </button>
              </form>
            </div>
          </div>

          {/* Pipeline Flow Pane */}
          <div className="hidden lg:flex w-80 flex-shrink-0 bg-[#0e1117] flex col">
            <header className="px-6 py-4 border-b border-[#2a3246] flex items-center justify-between">
              <div className="text-sm font-semibold">Pipeline Execution</div>
            </header>
            <div className="flex-1">
              <PipelineFlow status={pipelineStatus} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
