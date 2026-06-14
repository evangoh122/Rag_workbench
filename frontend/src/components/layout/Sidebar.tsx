import React from 'react';
import { Database, BookOpen, RefreshCcw, Search, ShieldCheck, MessageSquare, BarChart3, Network, Server, Activity, Cpu, ClipboardList } from 'lucide-react';
import DriftAlert from '../DriftAlert';

type AppView = 'chat' | 'traceability' | 'results' | 'metrics' | 'system' | 'methodology' | 'stocks' | 'audit';

interface SidebarProps {
  view: AppView;
  setView: (view: AppView) => void;
  mode: 'sql' | 'rag' | 'auditable' | 'graph';
  setMode: (mode: 'sql' | 'rag' | 'auditable' | 'graph') => void;
  ticker: string;
  setTicker: (ticker: string) => void;
  onReset: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ 
  view, 
  setView, 
  mode, 
  setMode, 
  ticker: _ticker, 
  setTicker: _setTicker, 
  onReset 
}) => {
  return (
    <aside className="w-72 flex-shrink-0 bg-surface border-r border-border flex flex-col p-5 shadow-none z-10 relative">
      {/* Logo */}
      <div className="flex items-center gap-3 mb-8 px-1">
        <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl">
          <Search size={22} className="text-white" />
        </div>
        <h2 className="m-0 text-xl font-bold text-primary tracking-tight">RAG Workbench</h2>
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
              onClick={() => setView('stocks')}
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
              onClick={() => setView('chat')}
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
              onClick={() => setView('traceability')}
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
              onClick={() => setView('methodology')}
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
              onClick={() => setView('results')}
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
              onClick={() => setView('audit')}
            >
              <ClipboardList size={18} className={view === 'audit' ? 'text-amber-400' : 'text-secondary'} />
              Audit Log
            </button>

            <button
              className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                view === 'metrics'
                  ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                  : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
              }`}
              onClick={() => setView('metrics')}
            >
              <Activity size={18} className={view === 'metrics' ? 'text-cyan-400' : 'text-secondary'} />
              Metrics Dashboard
            </button>

            <button
              className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                view === 'analytics'
                  ? 'bg-pink-500/10 text-pink-400 border-pink-500/20'
                  : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
              }`}
              onClick={() => setView('analytics')}
            >
              <BarChart3 size={18} className={view === 'analytics' ? 'text-pink-400' : 'text-secondary'} />
              Product Analytics
            </button>

            <button
              className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border ${
                view === 'system'
                  ? 'bg-orange-500/10 text-orange-400 border-orange-500/20'
                  : 'text-secondary border-transparent hover:text-primary hover:bg-surface-elevated'
              }`}
              onClick={() => setView('system')}
            >
              <Server size={18} className={view === 'system' ? 'text-orange-400' : 'text-secondary'} />
              System Overview
            </button>
          </div>
        </div>
      </nav>

      {/* Mode & Context (Only show if relevant) */}
      {(view === 'chat' || view === 'traceability') && (
        <div className="flex flex-col gap-2 mb-6">
          <div className="text-[11px] font-bold text-secondary uppercase tracking-widest px-2 mb-2">Configuration</div>
          
          {/* Engine Toggle */}
          <div className="bg-surface-elevated p-1.5 rounded-xl flex flex-col gap-1 border border-border">
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'auditable'
                  ? 'bg-surface text-primary shadow-none'
                  : 'text-secondary hover:text-primary hover:bg-surface bg-transparent'
              }`}
              onClick={() => setMode('auditable')}
            >
              <ShieldCheck size={16} />
              Auditable RAG
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'sql'
                  ? 'bg-surface text-primary shadow-none'
                  : 'text-secondary hover:text-primary hover:bg-surface bg-transparent'
              }`}
              onClick={() => setMode('sql')}
            >
              <Database size={16} />
              SQL
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'rag'
                  ? 'bg-surface text-primary shadow-none'
                  : 'text-secondary hover:text-primary hover:bg-surface bg-transparent'
              }`}
              onClick={() => setMode('rag')}
            >
              <BookOpen size={16} />
              Basic RAG
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'graph'
                  ? 'bg-surface text-primary shadow-none'
                  : 'text-secondary hover:text-primary hover:bg-surface bg-transparent'
              }`}
              onClick={() => setMode('graph')}
            >
              <Network size={16} />
              Graph RAG
            </button>
          </div>
        </div>
      )}

      {/* Clear chat button */}
      {(view === 'chat' || view === 'traceability') && (
        <div className="mt-auto">
          <button
            className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-sm font-medium text-secondary hover:text-bearish bg-transparent border border-border hover:border-bearish/50 hover:bg-bearish/5 cursor-pointer transition-all duration-300"
            onClick={onReset}
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
  );
};

export default Sidebar;
