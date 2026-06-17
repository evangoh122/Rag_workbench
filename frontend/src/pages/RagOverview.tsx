import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Play, Database, Network, BookOpen, Clock, AlertTriangle, CheckCircle } from 'lucide-react';
import Presentation from './Presentation';

export default function RagOverview() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background text-primary font-sans selection:bg-accent/20 selection:text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-border/40 bg-surface/20 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer font-medium text-sm"
          >
            <ArrowLeft size={16} />
            Back to Portfolio
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border border-accent/25 bg-accent/8 text-emerald-400">
              Product Overview & Deck
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-12 flex flex-col gap-12">
        {/* Hero / Intro Section */}
        <section className="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-3 duration-300">
          <div className="flex items-center gap-2.5">
            <div className="p-2.5 bg-accent/8 border border-accent/15 rounded-xl text-accent animate-pulse">
              <Database size={24} />
            </div>
            <div>
              <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-primary m-0">
                RAG Workbench
              </h1>
              <p className="text-xs font-mono text-emerald-400 mt-1">Auditable SEC Filing-QA & Verification</p>
            </div>
          </div>
          <p className="text-secondary text-base leading-relaxed font-light mt-2 max-w-3xl">
            RAG Workbench is an enterprise-grade financial intelligence platform built to eliminate hallucinations in SEC 10-K analysis. By integrating multi-agent reasoning, semantic Graph RAG, and deterministic XBRL mathematical cross-verification, it offers completely auditable answers anchored directly to filing data.
          </p>

          <div className="flex flex-wrap gap-4 mt-4">
            <button
              onClick={() => navigate('/rag')}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-emerald-500 text-white font-semibold transition-all duration-200 active:scale-[0.98] shadow-[0_4px_20px_rgba(16,185,129,0.15)] group cursor-pointer"
            >
              <Play size={16} className="fill-white" />
              Launch Live App
            </button>
            <button
              onClick={() => navigate('/rag', { state: { initialView: 'methodology' } })}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-border/80 hover:bg-surface-elevated/40 text-primary font-semibold transition-all duration-200 cursor-pointer"
            >
              <BookOpen size={16} />
              Read Technical Methodology
            </button>
          </div>
        </section>

        {/* Business Case & Challenge Section */}
        <section className="scroll-mt-20 animate-in fade-in slide-in-from-bottom-4 duration-450">
          <div className="flex items-center gap-2.5 mb-6">
            <div className="w-1 bg-accent h-6 rounded animate-pulse" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary m-0">The Business Case & Challenge</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* The Problem Card */}
            <div className="border border-red-500/20 rounded-2xl bg-red-500/5 p-6 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-full blur-2xl pointer-events-none" />
              <div className="flex items-center gap-2 text-red-400 font-semibold mb-4 text-xs uppercase tracking-wider font-mono">
                <AlertTriangle size={15} />
                The Bottleneck: Time-Intensive Reviews
              </div>
              <p className="text-sm text-secondary leading-relaxed mb-6 font-light">
                Financial analysts face critical bottlenecks when reviewing complex corporate financial disclosures. Trusting standard black-box LLMs is impossible due to hallucination risks, forcing a return to manual reviews:
              </p>
              
              <div className="space-y-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-12 text-center p-1.5 bg-red-500/10 border border-red-500/25 rounded-lg text-red-400 text-xs font-mono font-bold mt-0.5">
                    30m
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-primary">To Skim Reports</h4>
                    <p className="text-[11px] text-secondary/70 m-0">Finding relevant sections and disclosures quickly.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-12 text-center p-1.5 bg-red-500/10 border border-red-500/25 rounded-lg text-red-400 text-xs font-mono font-bold mt-0.5">
                    2h
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-primary">For Deep Analysis</h4>
                    <p className="text-[11px] text-secondary/70 m-0">Reading narrative details, risks, and tables word-for-word.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-12 text-center p-1.5 bg-red-500/10 border border-red-500/25 rounded-lg text-red-400 text-xs font-mono font-bold mt-0.5">
                    12h
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-primary">For Financial Modeling</h4>
                    <p className="text-[11px] text-secondary/70 m-0">Manually extracting, structuring, and verifying numbers to populate models.</p>
                  </div>
                </div>
              </div>
            </div>

            {/* The Solution Card */}
            <div className="border border-emerald-500/20 rounded-2xl bg-emerald-500/5 p-6 relative overflow-hidden flex flex-col justify-between">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
              <div>
                <div className="flex items-center gap-2 text-emerald-400 font-semibold mb-4 text-xs uppercase tracking-wider font-mono">
                  <CheckCircle size={15} />
                  Our Solution: Compressing Review Times
                </div>
                <p className="text-sm text-secondary leading-relaxed mb-6 font-light">
                  RAG Workbench cuts review times dramatically by automating retrieval, providing direct trace citations, and cross-checking claims using deterministic mathematical engines.
                </p>
                <div className="space-y-4">
                  <div className="flex items-start gap-3">
                    <div className="p-1 bg-emerald-500/15 rounded-lg text-emerald-400 mt-0.5">
                      <Clock size={14} />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-primary">Instant Citation Anchoring</h4>
                      <p className="text-[11px] text-secondary/70 m-0">Every numeric claim connects to its exact paragraph in the SEC filing.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="p-1 bg-emerald-500/15 rounded-lg text-emerald-400 mt-0.5">
                      <Database size={14} />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-primary">Deterministic XBRL Calculations</h4>
                      <p className="text-[11px] text-secondary/70 m-0">Cross-checks numbers via mathematical verification trees directly on XBRL facts.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="p-1 bg-emerald-500/15 rounded-lg text-emerald-400 mt-0.5">
                      <Network size={14} />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-primary">Knowledge Graph Mapping</h4>
                      <p className="text-[11px] text-secondary/70 m-0">Maps entity connections and trends across multi-year reporting cycles.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Slide Deck Section */}
        <section className="scroll-mt-20 animate-in fade-in slide-in-from-bottom-5 duration-600">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2.5">
              <div className="w-1 bg-accent h-6 rounded animate-pulse" />
              <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary m-0">Strategic Buy-In Slide Deck</h2>
            </div>
            <a
              href="https://docs.google.com/presentation/d/13ziiVDNATFpEPlh-tU24JFdmzaYr1qGe/edit?slide=id.g3f11adbf2af_0_507#slide=id.g3f11adbf2af_0_507"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent hover:text-emerald-300 font-semibold"
            >
              Open in Google Slides ↗
            </a>
          </div>

          <div className="border border-border/80 rounded-2xl overflow-hidden shadow-2xl bg-surface/30 p-2">
            <Presentation />
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50 mt-auto">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
}
