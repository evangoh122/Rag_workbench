import React from 'react';
import { Send, Database, Search, MessageSquare, Network } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import AuditTrail from '../components/AuditTrail';

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
  entities?: string[];
  triples?: Record<string, string>[];
}

interface PipelineStatus {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
}

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
  ticker,
  pipelineStatus,
  handleSubmit,
  chatEndRef,
}) => {
  return (
    <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
      {/* Header */}
      <header className="px-4 lg:px-8 py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm z-10 flex-shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-3">
            <MessageSquare className="text-blue-400" />
            Testing Interface
          </h1>
          <div className="text-sm text-gray-400 mt-1 flex items-center gap-2">
            Engine: <span className="text-gray-200 font-medium px-2 py-0.5 bg-[#161b24] rounded-md border border-[#202532]">{mode === 'sql' ? 'SQL Database' : mode === 'rag' ? 'Basic RAG' : mode === 'graph' ? 'Graph RAG' : 'Auditable Filing QA'}</span>
          </div>
        </div>
        {/* Mini Pipeline Status Indicator */}
        <div className="flex items-center gap-2 bg-[#161b24] px-4 py-2 rounded-xl border border-[#202532] shadow-sm">
           <div className="text-xs font-semibold text-gray-400 uppercase mr-2">Pipeline</div>
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
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-8 flex flex-col gap-8 scroll-smooth pb-32">
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
                ? `Ask questions about ${ticker}'s SEC filings. The system will retrieve relevant excerpts, extract XBRL facts, and verify the math.`
                : mode === 'graph'
                ? `Ask about ${ticker}'s knowledge graph. The system will identify entities, query the knowledge graph, and synthesize insights.`
                : 'Test the basic retrieval or SQL capabilities of the platform.'}
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
               {mode === 'graph' ? (
                 <>
                   <button onClick={() => setInput(`What are the key relationships for ${ticker} in the knowledge graph?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                     "What are {ticker}'s key relationships?"
                   </button>
                   <button onClick={() => setInput(`Show me the suppliers and partners of ${ticker}`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                     "Show me {ticker}'s suppliers and partners"
                   </button>
                 </>
               ) : (
                 <>
               <button onClick={() => setInput(`What was ${ticker}'s total revenue in the last fiscal year?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                  "What was {ticker}'s total revenue?"
               </button>
               <button onClick={() => setInput(`Did ${ticker}'s gross margin improve year-over-year?`)} className="text-left px-4 py-3 bg-[#161b24] border border-[#202532] rounded-xl hover:bg-[#1c222e] hover:border-blue-500/30 transition-all text-sm text-gray-300">
                  "Did {ticker}'s gross margin improve?"
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

              {msg.role === 'assistant' && (msg.sources || msg.verification) && (
                <div className="mt-4 pt-4 border-t border-[#202532]/50">
                  <AuditTrail
                    sources={msg.sources}
                    xbrl_facts={msg.xbrl_facts}
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
              Processing query...
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Input bar */}
      <div className="px-4 lg:px-8 py-6 bg-gradient-to-t from-[#0a0c10] via-[#0a0c10] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto flex items-center bg-[#161b24]/90 backdrop-blur-md border border-[#202532] rounded-2xl p-2 shadow-2xl transition-all duration-300 focus-within:border-blue-500/50 focus-within:ring-4 focus-within:ring-blue-500/10 pointer-events-auto"
        >
          <input
            className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-4 py-3 text-base outline-none w-full"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              mode === 'sql'
                ? 'Ask a SQL question...'
                : mode === 'rag' 
                ? 'Ask a Knowledge Base question...'
                : mode === 'graph'
                ? `Ask about ${ticker}'s knowledge graph...`
                : `Ask about ${ticker}'s SEC filing...`
            }
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex items-center justify-center px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl border-0 cursor-pointer transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed font-medium gap-2 ml-2"
          >
            Send <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatView;
