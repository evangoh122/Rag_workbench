import React from 'react';
import { Send, Database, Search, MessageSquare, Network } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import AuditTrail from '../components/AuditTrail';
import FinancialChart from '../components/FinancialChart';
import ChartView from '../components/ChartView';
import ChartErrorBoundary from '../components/ChartErrorBoundary';
import type { ChartSpec } from '../api/chat';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: Record<string, unknown>[];
  sources?: any[];
  xbrl_facts?: any[];
  relevant_xbrl?: any[];
  xbrl_badge?: string;
  xbrl_group?: string;
  verification?: {
    status: string;
    reasoning: string;
  };
  math_steps?: string[];
  entities?: string[];
  triples?: Record<string, string>[];
  chart?: ChartSpec;
}

interface PipelineStatus {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
}

const PIPELINE_STEPS: Array<{ key: keyof PipelineStatus; label: string }> = [
  { key: 'input', label: 'Input' },
  { key: 'retrieval', label: 'Retrieve' },
  { key: 'extraction', label: 'Extract' },
  { key: 'math', label: 'Calculate' },
  { key: 'verification', label: 'Verify' },
  { key: 'output', label: 'Answer' },
];

interface ChatViewProps {
  messages: Message[];
  input: string;
  setInput: (input: string) => void;
  loading: boolean;
  mode: 'sql' | 'rag' | 'auditable' | 'graph';
  ticker: string;
  pipelineStatus: PipelineStatus;
  handleSubmit: (e: React.FormEvent) => void;
  chatEndRef: React.RefObject<HTMLDivElement>;
}

const ChatView: React.FC<ChatViewProps> = ({
  messages,
  input,
  setInput,
  loading,
  mode,
  pipelineStatus,
  handleSubmit,
  chatEndRef,
}) => {
  return (
    <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
      {/* Header */}
      <header className="px-4 lg:px-8 py-5 border-b border-border bg-surface/50 backdrop-blur-sm z-10 flex-shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-primary flex items-center gap-3">
            <MessageSquare className="text-accent" />
            Testing Interface
          </h1>
          <div className="text-sm text-secondary mt-1 flex items-center gap-2">
            Engine: <span className="text-primary font-medium px-2 py-0.5 bg-surface-elevated rounded-md border border-border">{mode === 'sql' ? 'SQL Database' : mode === 'rag' ? 'Basic RAG' : mode === 'graph' ? 'Graph RAG' : 'Auditable Filing QA'}</span>
          </div>
        </div>
        {/* Mini Pipeline Status Indicator */}
        <div className="hidden md:flex items-center gap-2 bg-surface-elevated px-3 py-2 rounded-lg border border-border" role="status" aria-live="polite">
           <div className="text-xs font-semibold text-secondary mr-2">Pipeline</div>
           {PIPELINE_STEPS.map(({ key, label }) => {
             const s = pipelineStatus[key];
             return (
               <div key={key} className="w-10 text-center" title={`${label}: ${s ?? 'idle'}`}>
                 <div className={`h-1 rounded-full transition-colors duration-200 ${
                   s === 'success' ? 'bg-bullish' : s === 'error' ? 'bg-bearish' : s === 'pending' ? 'bg-accent animate-pulse' : 'bg-border'
                 }`} />
                 <span className="mt-1 block truncate text-[8px] text-muted">{label}</span>
               </div>
             );
           })}
        </div>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-8 flex flex-col gap-8 scroll-smooth pb-32">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto">
            <div className="w-16 h-16 bg-accent/10 rounded-xl flex items-center justify-center mb-6 border border-accent/20">
              <MessageSquare size={32} className="text-accent" />
            </div>
            <h3 className="text-2xl font-semibold text-primary mb-3">
              Start a Testing Session
            </h3>
            <p className="text-secondary text-base leading-relaxed mb-8">
              {mode === 'auditable' 
                ? `Ask questions about SEC filings. The system will retrieve relevant excerpts, extract XBRL facts, and verify the math.`
                : mode === 'graph'
                ? `Ask about the knowledge graph. The system will identify entities, query the knowledge graph, and synthesize insights.`
                : 'Test the basic retrieval or SQL capabilities of the platform.'}
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
               {mode === 'graph' ? (
                  <>
                    <button onClick={() => setInput(`What are the key relationships in the knowledge graph?`)} className="text-left px-4 py-3 bg-surface-elevated border border-border rounded-xl transition-all text-sm text-secondary hover:text-primary">
                      "What are the key relationships?"
                    </button>
                    <button onClick={() => setInput(`Show me the suppliers and partners of a company`)} className="text-left px-4 py-3 bg-surface-elevated border border-border rounded-xl transition-all text-sm text-secondary hover:text-primary">
                      "Show me suppliers and partners"
                    </button>
                  </>
                ) : (
                  <>
               <button onClick={() => setInput(`What was the total revenue in the last fiscal year?`)} className="text-left px-4 py-3 bg-surface-elevated border border-border rounded-xl transition-all text-sm text-secondary hover:text-primary">
                  "What was total revenue?"
               </button>
               <button onClick={() => setInput(`Did the gross margin improve year-over-year?`)} className="text-left px-4 py-3 bg-surface-elevated border border-border rounded-xl transition-all text-sm text-secondary hover:text-primary">
                  "Did gross margin improve?"
               </button>
                 </>
               )}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-5 max-w-[90%] ${
              msg.role === 'user' ? 'self-end flex-row-reverse' : 'self-start'
            }`}
          >
            {/* Avatar */}
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border ${
               msg.role === 'user' ? 'bg-accent-fill border-accent-fill text-white' : 'bg-surface border-border text-accent'
            }`}>
              {msg.role === 'user' ? <Database size={18} /> : <Search size={18} />}
            </div>

            {/* Message Bubble */}
            <div
              className={`px-5 py-4 rounded-2xl leading-relaxed text-[15px] shadow-none ${
                msg.role === 'user'
                  ? 'bg-accent-fill text-white rounded-tr-sm'
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

              <ChartErrorBoundary>
                {msg.role === 'assistant' && msg.chart &&
                  ((msg.chart.data?.length ?? 0) > 0 || (msg.chart.series?.length ?? 0) > 0) && (
                  <ChartView chart={msg.chart} />
                )}

                {/* Only show raw XBRL chart when no backend chart is present */}
                {msg.role === 'assistant' && !((msg.chart?.data?.length ?? 0) > 0 || (msg.chart?.series?.length ?? 0) > 0) && ((msg.relevant_xbrl?.length ?? 0) > 0 || (msg.xbrl_facts?.length ?? 0) > 0) && (
                  <FinancialChart facts={(msg.relevant_xbrl?.length ?? 0) > 0 ? msg.relevant_xbrl : msg.xbrl_facts} />
                )}
              </ChartErrorBoundary>

              {msg.role === 'assistant' && (msg.sources || msg.verification || msg.relevant_xbrl?.length) && (
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
                    <Network size={14} className="text-accent" />
                    <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Search Entities</span>
                  </div>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {msg.entities.map((entity, i) => (
                      <span key={i} className="px-3 py-1 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent-bright font-mono">
                        {entity}
                      </span>
                    ))}
                  </div>
                  {msg.triples && msg.triples.length > 0 && (
                    <>
                      <div className="flex items-center gap-2 mb-3 mt-4">
                        <Search size={14} className="text-accent" />
                        <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Knowledge Graph Triples ({msg.triples.length})</span>
                      </div>
                      <div className="bg-background border border-border rounded-xl overflow-hidden shadow-none">
                        {msg.triples.map((triple, i) => (
                          <div key={i} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-mono ${i % 2 === 0 ? '' : 'bg-surface/30'} ${i > 0 ? 'border-t border-border/50' : ''}`}>
                            <span className="text-accent-bright">{triple.subject}</span>
                            <span className="text-secondary">&rarr;</span>
                            <span className="text-bullish text-xs px-1.5 py-0.5 bg-bullish/10 rounded border border-bullish/20">{triple.predicate}</span>
                            <span className="text-secondary">&rarr;</span>
                            <span className="text-accent-bright">{triple.object}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {msg.sql && (
                <pre className="mt-4 bg-background border border-border text-secondary rounded-xl p-4 text-sm font-mono whitespace-pre-wrap overflow-x-auto shadow-none">
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
                                className="px-4 py-3 border-b border-border/50 text-secondary tabular-nums"
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
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-5 max-w-[90%] self-start animate-in slide-in-from-bottom-2 duration-300">
            <div className="w-10 h-10 rounded-xl bg-surface border border-border text-accent flex items-center justify-center">
              <Search size={18} className="animate-pulse" />
            </div>
            <div className="px-6 py-4 rounded-xl rounded-tl-sm bg-surface-elevated text-secondary border border-border" role="status" aria-live="polite">
              <div className="mb-3 text-primary font-medium">Retrieving filing sections</div>
              <div className="space-y-2" aria-hidden="true">
                <div className="h-2 w-64 max-w-full rounded bg-border-subtle animate-pulse" />
                <div className="h-2 w-48 max-w-full rounded bg-border-subtle animate-pulse" />
              </div>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Input bar */}
      <div className="px-4 lg:px-8 py-6 bg-gradient-to-t from-background via-background to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto flex items-center glass-input p-2 pointer-events-auto"
        >
          <input
            name="query"
            aria-label="Research question"
            className="flex-1 bg-transparent border-0 text-primary placeholder-muted px-4 py-3 text-base outline-none w-full"
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
            className="fintech-button flex items-center justify-center px-6 py-3 disabled:opacity-50 disabled:cursor-not-allowed gap-2 ml-2"
          >
            Send <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatView;
