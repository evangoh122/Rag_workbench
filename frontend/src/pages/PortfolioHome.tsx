import { useEffect } from 'react';

import { Mail, ArrowRight, Cpu, Network, Database, Search } from 'lucide-react';



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
  useEffect(() => {
    document.title = "Portfolio";
  }, []);

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
        <section className="mb-16 md:mb-24 max-w-3xl animate-fade-in">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/25 bg-accent/8 text-xs font-semibold text-emerald-400 mb-6 tracking-wide">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Solutions Architect & Product Manager
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-primary tracking-tight leading-[1.1] mb-6">
            Hi, I'm <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-500 bg-clip-text text-transparent">Evan Goh</span>.
          </h1>
          <p className="text-secondary text-base md:text-lg lg:text-xl leading-relaxed max-w-2xl font-light">
            I sit at the intersection of technology, data, and business. As a solutions architect and product manager, I design and build resilient, auditable AI frameworks that solve complex business and governance challenges.
          </p>
          <div className="flex flex-wrap gap-4 mt-8">
            <button
              onClick={() => document.getElementById('profile')?.scrollIntoView({ behavior: 'smooth' })}
              className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-accent hover:bg-emerald-500 text-white font-semibold transition-all duration-200 active:scale-[0.98] shadow-[0_4px_20px_rgba(16,185,129,0.15)] group cursor-pointer"
            >
              Walkthrough My Profile
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </button>
          </div>
        </section>

        {/* Profile Section */}
        <section id="profile" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded animate-pulse" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Professional Profile</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-stretch">
            {/* Left Column: About Me */}
            <div className="md:col-span-5 border border-border/40 rounded-2xl bg-surface/20 p-6 sm:p-8 relative overflow-hidden flex flex-col justify-center">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
              <h3 className="text-base font-bold text-primary mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                The Translation Layer
              </h3>
              <p className="text-sm text-secondary leading-relaxed font-light m-0">
                My core strength is acting as the translation layer between deep engineering teams and executive business stakeholders. I ensure that high-stakes technical projects are architected for security, maintainability, and absolute auditability, while remaining strictly aligned with regulatory standards like <strong>SR 11-7</strong>, <strong>MAS AI guidelines</strong>, and the <strong>EU AI Act</strong>.
              </p>
            </div>

            {/* Right Column: Specializations */}
            <div className="md:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="glass-sm p-5 border border-border/40">
                <div className="text-accent mb-3">
                  <Cpu size={18} />
                </div>
                <h4 className="text-sm font-bold text-primary mb-2">System Architecture</h4>
                <p className="text-xs text-secondary/80 leading-relaxed font-light m-0">
                  Designing multi-agent pipelines (LangGraph), resilient persistence/restore mechanisms, and structured data verification layers.
                </p>
              </div>

              <div className="glass-sm p-5 border border-border/40">
                <div className="text-accent mb-3">
                  <Network size={18} />
                </div>
                <h4 className="text-sm font-bold text-primary mb-2">AI Governance</h4>
                <p className="text-xs text-secondary/80 leading-relaxed font-light m-0">
                  Implementing honest confidence scoring models, robust human-in-the-loop (HITL) review queues, and drift detection metrics to guarantee system trust.
                </p>
              </div>

              <div className="glass-sm p-5 border border-border/40">
                <div className="text-accent mb-3">
                  <Database size={18} />
                </div>
                <h4 className="text-sm font-bold text-primary mb-2">Data Engineering</h4>
                <p className="text-xs text-secondary/80 leading-relaxed font-light m-0">
                  Orchestrating pipelines (SEC EDGAR, XBRL companyfacts), high-performance query optimization (DuckDB, Polars), and semantic embedding stores.
                </p>
              </div>

              <div className="glass-sm p-5 border border-border/40 flex flex-col justify-center bg-accent/5">
                <h4 className="text-sm font-bold text-accent mb-1">Solutions Architect</h4>
                <p className="text-[11px] text-secondary/70 leading-relaxed font-light mb-3">
                  Let's collaborate on building secure, auditable, and regulatory-aligned AI systems.
                </p>
                <a
                  href="mailto:evangohsg@gmail.com"
                  className="text-xs font-semibold text-accent hover:text-emerald-300 transition-colors inline-flex items-center gap-1"
                >
                  Get in touch <ArrowRight size={12} />
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* Portfolios Section */}
        <section id="portfolios" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded animate-pulse" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">My Portfolios</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-3xl">
            {/* Card 1: RAG & AI Portfolio (First Portfolio) */}
            <div className="border border-accent/30 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden shadow-[0_4px_20px_rgba(16,185,129,0.05)]">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent animate-pulse">
                      <Cpu size={20} />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-primary tracking-tight">RAG & AI Portfolio</h3>
                      <p className="text-[10px] font-mono text-emerald-400">Agentic & Auditable Systems</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-accent/30 bg-accent/10 text-emerald-400">
                    Active
                  </span>
                </div>
                <p className="text-xs text-secondary leading-relaxed mb-6 font-light">
                  A curated showcase of secure agentic frameworks, multi-agent control logic, and deterministic math validation built for financial and regulatory compliance analysis.
                </p>
              </div>
              <div className="flex items-center justify-between border-t border-border/30 pt-4 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1">
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FastAPI</span>
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">DuckDB</span>
                </div>
                <span className="text-xs font-semibold text-accent group-hover:underline">Current space</span>
              </div>
            </div>

            {/* Card 2: Enterprise Data & Solutions (Placeholder for next portfolio) */}
            <div className="border border-border/40 rounded-2xl bg-surface/10 hover:bg-surface-elevated/10 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden opacity-60 hover:opacity-80">
              <div>
                <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-border/20 border border-border/35 rounded-xl text-secondary">
                      <Database size={20} />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-primary tracking-tight">Enterprise Infrastructure</h3>
                      <p className="text-[10px] font-mono text-secondary">Data Platforms & Scalability</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-border/30 bg-surface text-secondary">
                    Coming Soon
                  </span>
                </div>
                <p className="text-xs text-secondary/70 leading-relaxed mb-6 font-light">
                  High-throughput streaming pipelines, distributed databases, and cloud infrastructure patterns tailored for enterprise scalability and high availability.
                </p>
              </div>
              <div className="flex items-center justify-between border-t border-border/30 pt-4 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1">
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kafka</span>
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kubernetes</span>
                  <span className="text-[9px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">AWS</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Projects Section */}
        <section id="projects" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-1 bg-accent h-6 rounded animate-pulse" />
            <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Projects I Have Done</h2>
          </div>

          <div className="flex flex-col gap-10 max-w-3xl">
            {/* 1. Slide Deck Project */}
            <div className="border border-border/80 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent animate-pulse">
                      <Network size={20} />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-primary tracking-tight">Strategic Buy-In Slide Deck</h3>
                      <p className="text-[11px] font-mono text-emerald-400">Model Risk Management Strategy</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border border-border/25 bg-accent/8 text-[11px] font-semibold text-emerald-400">
                    Case Study
                  </span>
                </div>
                <p className="text-sm text-secondary leading-relaxed mb-6 font-light">
                  Before building, a successful product requires strategic alignment. This presentation outlines the design methodology, model risk management principles (SR 11-7, MAS AI Guidelines), and architectural layout used to pitch this auditable RAG system to executive and compliance stakeholders.
                </p>
              </div>
            </div>

            {/* 2. RAG Workbench Project */}
            <div className="border border-border/80 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden">
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
                    UAT
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
              </div>
            </div>
          </div>
        </section>


      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50 mt-auto">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
          <div className="flex gap-4">
            <a href="https://www.linkedin.com/in/eevangoh/" target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">LinkedIn</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
