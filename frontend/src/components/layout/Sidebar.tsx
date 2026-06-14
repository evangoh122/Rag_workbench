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
    <aside className="w-72 flex-shrink-0 bg-[#121212] border-r border-[#2A2A2A] flex flex-col p-5 shadow-[4px_0_24px_rgba(0,0,0,0.2)] z-10 relative">
      {/* Logo */}
      <div className="flex items-center gap-3 mb-8 px-1">
        <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl shadow-lg shadow-blue-500/20">
          <Search size={22} className="text-white" />
        </div>
        <h2 className="m-0 text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-gray-100 to-gray-400 tracking-tight">RAG Workbench</h2>
      </div>

      {/* Main Navigation */}
      <nav className="flex flex-col gap-2 mb-8">
        <div className="text-[11px] font-bold text-gray-500 uppercase tracking-widest px-2 mb-2">Sections</div>
        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'chat'
              ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('chat')}
        >
          <MessageSquare size={18} className={view === 'chat' ? 'text-blue-400' : 'text-gray-500'} />
          Testing Chat
        </button>
        
        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'traceability'
              ? 'bg-purple-500/10 text-purple-400 border-purple-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('traceability')}
        >
          <Activity size={18} className={view === 'traceability' ? 'text-purple-400' : 'text-gray-500'} />
          Pipeline Traceability
        </button>

        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'results'
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('results')}
        >
          <BarChart3 size={18} className={view === 'results' ? 'text-emerald-400' : 'text-gray-500'} />
          Results & Testing
        </button>

        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'audit'
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('audit')}
        >
          <ClipboardList size={18} className={view === 'audit' ? 'text-amber-400' : 'text-gray-500'} />
          Audit Log
        </button>

        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'metrics'
              ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('metrics')}
        >
          <Activity size={18} className={view === 'metrics' ? 'text-cyan-400' : 'text-gray-500'} />
          Metrics Dashboard
        </button>

        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'system'
              ? 'bg-orange-500/10 text-orange-400 border-orange-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('system')}
        >
          <Server size={18} className={view === 'system' ? 'text-orange-400' : 'text-gray-500'} />
          System Overview
        </button>

        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'methodology'
              ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('methodology')}
        >
          <BookOpen size={18} className={view === 'methodology' ? 'text-indigo-400' : 'text-gray-500'} />
          Methodology
        </button>
        <button
          className={`w-full flex items-center gap-3 py-2.5 px-3 rounded-xl text-sm font-medium transition-all duration-300 cursor-pointer border border-transparent ${
            view === 'stocks'
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1A1A]'
          }`}
          onClick={() => setView('stocks')}
        >
          <Cpu size={18} className={view === 'stocks' ? 'text-emerald-400' : 'text-gray-500'} />
          Stocks
        </button>
      </nav>

      {/* Mode & Context (Only show if relevant) */}
      {(view === 'chat' || view === 'traceability') && (
        <div className="flex flex-col gap-2 mb-6">
          <div className="text-[11px] font-bold text-gray-500 uppercase tracking-widest px-2 mb-2">Configuration</div>
          
          {/* Engine Toggle */}
          <div className="bg-[#1A1A1A] p-1.5 rounded-xl flex flex-col gap-1 border border-[#2A2A2A]">
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'auditable'
                  ? 'bg-[#2A2A2A] text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#242424] bg-transparent'
              }`}
              onClick={() => setMode('auditable')}
            >
              <ShieldCheck size={16} />
              Auditable RAG
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'sql'
                  ? 'bg-[#2A2A2A] text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#242424] bg-transparent'
              }`}
              onClick={() => setMode('sql')}
            >
              <Database size={16} />
              SQL
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'rag'
                  ? 'bg-[#2A2A2A] text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#242424] bg-transparent'
              }`}
              onClick={() => setMode('rag')}
            >
              <BookOpen size={16} />
              Basic RAG
            </button>
            <button
              className={`flex items-center gap-2.5 py-2 px-3 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer border-0 ${
                mode === 'graph'
                  ? 'bg-[#2A2A2A] text-white shadow-sm'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#242424] bg-transparent'
              }`}
              onClick={() => setMode('graph')}
            >
              <Network size={16} />
              Graph RAG
            </button>
          </div>

          {/* Ticker Selector - Removed for mobile optimization/cleaner UI */}
        </div>
      )}

      {/* Clear chat button */}
      {(view === 'chat' || view === 'traceability') && (
        <div className="mt-auto">
          <button
            className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-sm font-medium text-gray-400 hover:text-red-400 bg-transparent border border-[#2A2A2A] hover:border-red-900/50 hover:bg-red-500/5 cursor-pointer transition-all duration-300"
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
