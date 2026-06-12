import React from 'react';
import { Activity, Send } from 'lucide-react';
import PipelineFlow from '../components/PipelineFlow';

interface PipelineStatus {
  input?: 'success' | 'error' | 'pending';
  retrieval?: 'success' | 'error' | 'pending';
  extraction?: 'success' | 'error' | 'pending';
  math?: 'success' | 'error' | 'pending';
  verification?: 'success' | 'error' | 'pending';
  output?: 'success' | 'error' | 'pending';
}

interface TraceabilityViewProps {
  pipelineStatus: PipelineStatus;
  input: string;
  setInput: (input: string) => void;
  loading: boolean;
  handleSubmit: (e: React.FormEvent) => void;
}

const TraceabilityView: React.FC<TraceabilityViewProps> = ({
  pipelineStatus,
  input,
  setInput,
  loading,
  handleSubmit,
}) => {
  return (
    <div className="flex-1 flex flex-col h-full animate-in fade-in duration-300">
      <header className="px-4 lg:px-8 py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm z-10 flex-shrink-0">
        <h1 className="text-xl font-semibold text-white flex items-center gap-3">
          <Activity className="text-purple-400" />
          Pipeline Traceability
        </h1>
        <p className="text-sm text-gray-400 mt-1">Live visualization of the execution steps for your last query.</p>
      </header>
      <div className="flex-1 relative bg-[#0a0c10]">
        <PipelineFlow status={pipelineStatus} />
      </div>
      {/* Input allowed in Traceability view too */}
      <div className="px-4 lg:px-8 py-6 bg-gradient-to-t from-[#0a0c10] to-transparent flex-shrink-0 absolute bottom-0 left-0 right-0 pointer-events-none">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto flex items-center bg-[#161b24]/90 backdrop-blur-md border border-[#202532] rounded-2xl p-2 shadow-2xl transition-all duration-300 focus-within:border-purple-500/50 focus-within:ring-4 focus-within:ring-purple-500/10 pointer-events-auto"
        >
          <input
            className="flex-1 bg-transparent border-0 text-white placeholder-gray-500 px-4 py-3 text-base outline-none w-full"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Test a query to trace its execution..."
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex items-center justify-center px-6 py-3 bg-purple-600 hover:bg-purple-500 text-white rounded-xl border-0 cursor-pointer transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed font-medium gap-2 ml-2"
          >
            Trace <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default TraceabilityView;
