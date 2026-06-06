import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, Database, BookOpen, RefreshCcw, Search, Table as TableIcon } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './App.css';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'table' | 'error';
  sql?: string;
  data?: any[];
}

const API_BASE = 'http://localhost:8000/api';

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<'sql' | 'rag'>('sql');
  const [loading, setLoading] = useState(false);
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

    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const endpoint = mode === 'sql' ? '/chat/sql' : '/chat/rag';
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      
      const response = await axios.post(`${API_BASE}${endpoint}`, {
        message: input,
        history: history
      });

      const data = response.data;
      const assistantMsg: Message = {
        role: 'assistant',
        content: data.answer || data.detail || 'No response',
        type: data.type,
        sql: data.sql,
        data: data.data
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `Error: ${err.response?.data?.detail || err.message}`,
        type: 'error'
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '32px' }}>
          <Search size={24} color="#3b82f6" />
          <h2 style={{ margin: 0, fontSize: '18px' }}>RAG Workbench</h2>
        </div>

        <div className="mode-toggle">
          <button 
            className={`mode-btn ${mode === 'sql' ? 'active' : ''}`}
            onClick={() => setMode('sql')}
          >
            <Database size={16} style={{ marginBottom: '-3px', marginRight: '6px' }} />
            SQL
          </button>
          <button 
            className={`mode-btn ${mode === 'rag' ? 'active' : ''}`}
            onClick={() => setMode('rag')}
          >
            <BookOpen size={16} style={{ marginBottom: '-3px', marginRight: '6px' }} />
            RAG
          </button>
        </div>

        <div style={{ marginTop: 'auto' }}>
          <button 
            className="mode-btn" 
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            onClick={() => setMessages([])}
          >
            <RefreshCcw size={16} />
            Clear Chat
          </button>
        </div>
      </div>

      <div className="main-content">
        <header className="header">
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            Mode: <strong>{mode === 'sql' ? 'Database (SQL)' : 'Knowledge Base (RAG)'}</strong>
          </div>
        </header>

        <div className="chat-container">
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: '100px', color: 'var(--text-secondary)' }}>
              <h3>How can I help you with your financial data today?</h3>
              <p>Try asking: "Show me AAPL closing prices for the last 30 days"</p>
            </div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.role}`}>
              <div className="message-bubble">
                <ReactMarkdown>{msg.content}</ReactMarkdown>
                
                {msg.sql && (
                  <div className="sql-block">
                    <code>{msg.sql}</code>
                  </div>
                )}

                {msg.data && msg.data.length > 0 && (
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          {Object.keys(msg.data[0]).map(key => (
                            <th key={key}>{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {msg.data.slice(0, 10).map((row, i) => (
                          <tr key={i}>
                            {Object.values(row).map((val: any, j) => (
                              <td key={j}>{typeof val === 'number' ? val.toLocaleString() : String(val)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {msg.data.length > 10 && (
                      <div style={{ padding: '8px', fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'center' }}>
                        Showing 10 of {msg.data.length} rows
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div className="message-bubble" style={{ fontStyle: 'italic', opacity: 0.7 }}>
                Thinking...
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="input-container">
          <form onSubmit={handleSubmit} className="input-wrapper">
            <input 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={mode === 'sql' ? "Ask a SQL question..." : "Ask a Knowledge Base question..."}
              disabled={loading}
            />
            <button type="submit" className="send-btn" disabled={loading || !input.trim()}>
              <Send size={18} />
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

export default App;
