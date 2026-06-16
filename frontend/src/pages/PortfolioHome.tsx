import { Link } from 'react-router-dom';
import { Mail, ArrowRight, Cpu, Network, Database, Search, Terminal } from 'lucide-react';
import Presentation from './Presentation';

const GithubIcon = ({ size = 20 }: { size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);

const LinkedinIcon = ({ size = 20 }: { size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect width="4" height="12" x="2" y="9" />
    <circle cx="4" cy="4" r="2" />
  </svg>
);

export default function PortfolioHome() {
  return (
    <div className="min-h-screen bg-background text-primary font-sans selection:bg-accent/20 selection:text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-border/40 bg-surface/20 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center font-mono font-bold text-white shadow-[0_0_12px_rgba(46,139,87,0.2)]">
              E
            </div>
            <span className="font-semibold text-base tracking-tight">Evan Goh</span>
          </div>
          <nav className="flex items-center gap-5 text-sm">
            <a
              href="https://github.com/evangoh122"
              target="_blank"
              rel="noopener noreferrer"
              className="text-secondary hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <GithubIcon size={15} />
              <span className="hidden sm:inline">GitHub</span>
            </a>
            <a
              href="https://www.linkedin.com/in/eevangoh/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-secondary hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <LinkedinIcon size={15} />
              <span className="hidden sm:inline">LinkedIn</span>
            </a>
            <a
              href="mailto:evangohsg@gmail.com"
              className="text-secondary hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <Mail size={15} />
              <span className="hidden sm:inline">Contact</span>
            </a>
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-12 md:py-20 flex flex-col justify-center">
        {/* Hero Section */}
        <section className="mb-16 md:mb-24 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/25 bg-accent/8 text-xs font-semibold text-emerald-400 mb-6 tracking-wide animate-fade-in">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Solutions Architect & Product Manager
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-primary tracking-tight leading-[1.1] mb-6">
            Hi, I'm <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-500 bg-clip-text text-transparent">Evan Goh</span>.
          </h1>
          <p className="text-secondary text-base md:text-lg lg:text-xl leading-relaxed max-w-2xl font-light">
            I design and build high-performance data systems, agentic workflows, and semantic intelligence layers. Focused on absolute auditability, engineering durability, and clean architecture.
          </p>
          <div className="flex flex-wrap gap-4 mt-8">
            <Link
              to="/rag"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-bullish hover:bg-emerald-500 text-white font-semibold transition-all duration-200 active:scale-[0.98] shadow-[0_4px_20px_rgba(46,139,87,0.15)] group"
            >
              Launch RAG Workbench
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </Link>

          </div>
        </section>

        {/* Featured Projects */}
        <section className="mb-16 md:mb-24">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded animate-pulse" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Featured Work</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* RAG Workbench Card */}
            <div className="md:col-span-2 border border-border/80 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent animate-pulse">
                      <Search size={20} />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-primary tracking-tight">RAG Workbench</h3>
                      <p className="text-[11px] font-mono text-emerald-400">Auditable SEC Filing-QA</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border border-bullish/20 bg-bullish/10 text-emerald-400">
                    Production
                  </span>
                </div>
                <p className="text-sm text-secondary leading-relaxed mb-6 font-light">
                  An advanced agent-driven financial analyzer designed to inspect and cross-verify SEC 10-K filings. Escapes standard black-box LLM limitations by tracing numbers back to structured XBRL facts with calculations, citations, and an interactive execution path visualizer.
                </p>
                
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <Network size={13} />
                      Graph RAG
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Links facts in an interactive entity relation graph</p>
                  </div>
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <Database size={13} />
                      XBRL Verification
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Deterministic math checks directly on filed financial data</p>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FastAPI</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">DuckDB</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">LangGraph</span>
                </div>
                <Link
                  to="/rag"
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:text-emerald-300 transition-colors group-hover:underline"
                >
                  Launch App
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </Link>
              </div>
            </div>

            {/* Small Spec Card 1 */}
            <div className="border border-border/80 rounded-2xl bg-surface/30 p-6 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <div className="p-1.5 bg-accent/8 rounded-lg text-accent">
                    <Database size={16} />
                  </div>
                  <h4 className="text-sm font-bold text-primary tracking-tight">Data Engineering</h4>
                </div>
                <p className="text-xs text-secondary leading-relaxed font-light mb-4">
                  Experience indexing multi-gigabyte corpora of financial filings, building automated ingestion scripts (EDGAR/Polygon), and implementing fast vector databases + hybrid search pipelines.
                </p>
              </div>
              <div className="text-[10px] font-mono text-secondary/60">
                DuckDB &middot; sentence-transformers &middot; SEC API
              </div>
            </div>
          </div>
        </section>

        {/* Technical Core Values */}
        <section className="mb-16 md:mb-24">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Technical Approach</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="glass-sm p-5 border border-border/40">
              <div className="text-accent mb-3">
                <Cpu size={20} />
              </div>
              <h3 className="text-sm font-bold text-primary mb-2">Multi-Agent Control</h3>
              <p className="text-xs text-secondary leading-relaxed font-light m-0">
                Utilizing stateful multi-agent engines (LangGraph) for planning, query decomposition, execution verification, and self-correction loop.
              </p>
            </div>

            <div className="glass-sm p-5 border border-border/40">
              <div className="text-accent mb-3">
                <Terminal size={20} />
              </div>
              <h3 className="text-sm font-bold text-primary mb-2">Deterministic Math</h3>
              <p className="text-xs text-secondary leading-relaxed font-light m-0">
                Integrating LLMs with deterministic calculation engines to avoid hallucinated metrics and ground every calculation on XBRL.
              </p>
            </div>

            <div className="glass-sm p-5 border border-border/40">
              <div className="text-accent mb-3">
                <Database size={20} />
              </div>
              <h3 className="text-sm font-bold text-primary mb-2">Durability & Restore</h3>
              <p className="text-xs text-secondary leading-relaxed font-light m-0">
                Designing snapshots, boot restore systems, and automated persistence cycles to guarantee runtime stability across restarts.
              </p>
            </div>
          </div>
        </section>

        {/* Slide Deck Section */}
        <section className="mb-16 md:mb-24 animate-fade-in">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Strategic Document / How to Get Buy-In from Stakeholders</h2>
          </div>
          <div className="border border-border/40 rounded-2xl bg-surface/20 overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.35)]">
            <Presentation />
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50 mt-auto">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
          <div className="flex gap-4">
            <a href="https://github.com/evangoh122" target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">GitHub</a>
            <a href="https://www.linkedin.com/in/eevangoh/" target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">LinkedIn</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
