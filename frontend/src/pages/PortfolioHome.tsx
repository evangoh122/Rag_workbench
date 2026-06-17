import React, { useState } from 'react';
import { Mail, ArrowRight, Cpu, Network, Database, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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
  const navigate = useNavigate();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchEnd, setTouchEnd] = useState<number | null>(null);

  const totalSlides = 2;

  const nextSlide = () => {
    setCurrentIndex((prev) => (prev + 1) % totalSlides);
  };

  const prevSlide = () => {
    setCurrentIndex((prev) => (prev - 1 + totalSlides) % totalSlides);
  };

  const onTouchStart = (e: React.TouchEvent) => {
    setTouchEnd(null);
    setTouchStart(e.targetTouches[0].clientX);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    setTouchEnd(e.targetTouches[0].clientX);
  };

  const onTouchEnd = () => {
    if (!touchStart || !touchEnd) return;
    const distance = touchStart - touchEnd;
    const isLeftSwipe = distance > 50;
    const isRightSwipe = distance < -50;
    if (isLeftSwipe) {
      nextSlide();
    } else if (isRightSwipe) {
      prevSlide();
    }
  };


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
        <section className="mb-16 md:mb-24 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/25 bg-accent/8 text-xs font-semibold text-emerald-400 mb-6 tracking-wide">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Solutions Architect, Product Manager & AI Transformation Leader
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-primary tracking-tight leading-[1.1] mb-6">
            Hi, I'm <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-500 bg-clip-text text-transparent">Evan Goh</span>.
          </h1>
          <p className="text-secondary text-base md:text-lg lg:text-xl leading-relaxed max-w-2xl font-light">
            I enjoy working where data, AI, and product meet. I build systems that help people understand complex information, trust the insights they see, and make better decisions.
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

          <div className="max-w-3xl border border-border/40 rounded-2xl bg-surface/20 p-6 sm:p-8 relative overflow-hidden flex flex-col justify-center">
            <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
            <h3 className="text-base font-bold text-primary mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent" />
              The Translation Layer & AI Transformation
            </h3>
            <p className="text-sm text-secondary leading-relaxed font-light m-0">
              My core strength is leading AI Transformation by acting as the translation layer between deep engineering teams and executive business stakeholders. I work with stakeholders to architect solutions that are maintainable and secure.
            </p>
          </div>
        </section>

        {/* Featured Work Carousel Section */}
        <section id="projects" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-center justify-between mb-8 max-w-3xl">
            <div className="flex items-center gap-2.5">
              <div className="w-1 bg-accent h-6 rounded animate-pulse" />
              <h2 className="text-lg md:text-xl font-bold tracking-tight text-primary">Featured Work</h2>
            </div>
            
            {/* Carousel Navigation Arrows */}
            <div className="flex items-center gap-2">
              <button
                onClick={prevSlide}
                aria-label="Previous slide"
                className="p-2 border border-border/80 rounded-xl bg-surface/20 hover:bg-surface-elevated/40 text-secondary hover:text-primary transition-colors cursor-pointer"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={nextSlide}
                aria-label="Next slide"
                className="p-2 border border-border/80 rounded-xl bg-surface/20 hover:bg-surface-elevated/40 text-secondary hover:text-primary transition-colors cursor-pointer"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div 
            className="relative overflow-hidden w-full max-w-3xl"
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
          >
            <div
              className="flex transition-transform duration-500 ease-in-out"
              style={{ transform: `translateX(-${currentIndex * 100}%)` }}
            >
              {/* Slide 1: RAG Workbench & Strategic Slide Deck */}
              <div className="w-full flex-shrink-0 px-1">
                <div
                  onClick={() => navigate('/rag-overview')}
                  className="border border-accent/20 hover:border-accent/50 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden cursor-pointer shadow-[0_4px_20px_rgba(16,185,129,0.02)] hover:shadow-[0_4px_25px_rgba(16,185,129,0.08)] min-h-[460px]"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-colors pointer-events-none" />
                  <div>
                    <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent animate-pulse">
                          <Search size={20} />
                        </div>
                        <div>
                          <h3 className="text-base sm:text-lg font-bold text-primary tracking-tight">RAG Workbench & Strategic Slide Deck</h3>
                          <p className="text-[11px] font-mono text-emerald-400">Helping investors and analysts find answers faster without sacrificing trust</p>
                        </div>
                      </div>
                      <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border border-border/25 bg-accent/8 text-[11px] font-semibold text-emerald-400">
                        Case Study & App
                      </span>
                    </div>

                    {/* Business Case & Challenge Section */}
                    <div className="mb-5 bg-surface-elevated/35 border border-border/30 rounded-xl p-4">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 mb-2 font-mono uppercase tracking-wider">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Business Case & Challenge
                      </div>
                      <p className="text-xs text-secondary leading-relaxed mb-3 font-light">
                        Financial analysts spend an excessive amount of time reviewing SEC reports:
                      </p>
                      
                      <div className="grid grid-cols-3 gap-2 text-center mb-3">
                        <div className="bg-background/60 border border-border/40 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-emerald-400">30 Min</div>
                          <div className="text-[9px] text-secondary/70">To Skim</div>
                        </div>
                        <div className="bg-background/60 border border-border/40 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-emerald-400">2 Hrs</div>
                          <div className="text-[9px] text-secondary/70">Deep Analysis</div>
                        </div>
                        <div className="bg-background/60 border border-border/40 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-emerald-400">12 Hrs</div>
                          <div className="text-[9px] text-secondary/70">To Model</div>
                        </div>
                      </div>
                      
                      <p className="text-xs text-secondary leading-relaxed font-light m-0">
                        Our solution: compress review times and make verification immediate and completely auditable.
                      </p>
                    </div>

                    <p className="text-xs text-secondary leading-relaxed mb-6 font-light">
                      An advanced agent-driven financial analyzer designed to inspect and cross-verify SEC 10-K filings. Escapes standard black-box LLM limitations by tracing numbers back to structured XBRL facts with calculations, citations, and an interactive execution path visualizer.
                    </p>

                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div className="glass-sm p-3.5">
                        <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                          <Network size={13} />
                          Graph RAG & Strategy
                        </div>
                        <p className="text-[11px] text-secondary/70 m-0">Links facts in an interactive entity relation graph & outlines strategic design alignment</p>
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
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">RAG</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">AI Engineering</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">LLM Application</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">Embeddings & Vector Search</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">AI Governance</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">AI Evaluation & Validation</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FAST API</span>
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-emerald-300 transition-colors group-hover:underline">
                      View Pitch & Deck
                      <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </div>
              </div>

              {/* Slide 3: Enterprise Infrastructure */}
              <div className="w-full flex-shrink-0 px-1">
                <div
                  onClick={() => navigate('/rag', { state: { initialView: 'stocks' } })}
                  className="border border-accent/20 hover:border-accent/50 rounded-2xl bg-surface/40 hover:bg-surface-elevated/40 transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden cursor-pointer shadow-[0_4px_20px_rgba(16,185,129,0.02)] hover:shadow-[0_4px_25px_rgba(16,185,129,0.08)] min-h-[460px]"
                >
                  <div>
                    <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 bg-border/20 border border-border/35 rounded-xl text-secondary">
                          <Database size={20} />
                        </div>
                        <div>
                          <h3 className="text-base sm:text-lg font-bold text-primary tracking-tight">Enterprise Infrastructure</h3>
                          <p className="text-[11px] font-mono text-secondary">Data Platforms & High-Availability Scalability</p>
                        </div>
                      </div>
                      <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border border-border/25 bg-accent/8 text-[11px] font-semibold text-emerald-400">
                        Live App Link
                      </span>
                    </div>

                    {/* Business Case & Challenge Section */}
                    <div className="mb-5 bg-surface-elevated/20 border border-border/20 rounded-xl p-4">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-secondary mb-2 font-mono uppercase tracking-wider">
                        <span className="w-1.5 h-1.5 rounded-full bg-secondary/50" />
                        Business Case & Challenge
                      </div>
                      <p className="text-xs text-secondary/80 leading-relaxed mb-3 font-light">
                        Customers and trading systems require high-performance queries on historical stock OHLCV data to analyze market patterns and price action:
                      </p>
                      
                      <div className="grid grid-cols-3 gap-2 text-center mb-3">
                        <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-secondary">10B+</div>
                          <div className="text-[9px] text-secondary/60">OHLCV Bars</div>
                        </div>
                        <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-secondary">&lt; 15ms</div>
                          <div className="text-[9px] text-secondary/60">Query Latency</div>
                        </div>
                        <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                          <div className="text-xs font-mono font-bold text-secondary">Sub-Sec</div>
                          <div className="text-[9px] text-secondary/60">Aggregations</div>
                        </div>
                      </div>
                      
                      <p className="text-xs text-secondary/70 leading-relaxed font-light m-0">
                        Our solution: build a partitioned, column-oriented database layout optimized for fast time-series analytical scans.
                      </p>
                    </div>

                    {/* Infrastructure Blueprint Details */}
                    <div className="mb-5 bg-surface-elevated/20 border border-border/20 rounded-xl p-4">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-secondary mb-2 font-mono uppercase tracking-wider">
                        Pipeline Blueprint
                      </div>
                      <div className="font-mono text-[9px] text-secondary/60 leading-relaxed">
                        Kafka Ingress ➜ Flink SQL stream engine ➜ ClickHouse Warehouse ➜ App API Tier
                      </div>
                    </div>

                    <p className="text-xs text-secondary/70 leading-relaxed mb-6 font-light">
                      Architectural blueprint designs for large-scale data platforms. Directly feeds historical market pricing data into our AI RAG Workbench sandbox to enable price-performance analysis and charting.
                    </p>

                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div className="glass-sm p-3.5 opacity-60">
                        <div className="flex items-center gap-2 text-secondary text-xs font-semibold mb-1">
                          <Database size={13} />
                          Stream Processing
                        </div>
                        <p className="text-[11px] text-secondary/70 m-0">Real-time state tracking and stream schemas</p>
                      </div>
                      <div className="glass-sm p-3.5 opacity-60">
                        <div className="flex items-center gap-2 text-secondary text-xs font-semibold mb-1">
                          <Cpu size={13} />
                          Distributed DBs
                        </div>
                        <p className="text-[11px] text-secondary/70 m-0">Partitioning strategies, indices, and clickhouse shards</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                    <div className="flex flex-wrap gap-1">
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kafka</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kubernetes</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">AWS</span>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">ClickHouse</span>
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-emerald-300 transition-colors group-hover:underline">
                      Explore Charts
                      <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Slide Indicators / Dots */}
            <div className="flex justify-center gap-1.5 mt-5">
              {[0, 1].map((idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentIndex(idx)}
                  className={`w-1.5 h-1.5 rounded-full transition-all duration-300 cursor-pointer ${
                    currentIndex === idx ? 'bg-accent w-4' : 'bg-secondary/40'
                  }`}
                  aria-label={`Go to slide ${idx + 1}`}
                />
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50 mt-auto">
        <div className="max-w-5xl mx-auto px-6 flex flex-col items-center gap-4">
          <div className="flex w-full flex-col sm:flex-row items-center justify-between gap-4">
            <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
            <div className="flex gap-4">
              <a href="https://www.linkedin.com/in/eevangoh/" target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">LinkedIn</a>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-secondary/40 leading-relaxed max-w-2xl text-center">
            Disclaimer: This is a personal portfolio and ongoing area of exploration. All views expressed are my own. All data is publicly sourced and not related to my work.
          </p>
        </div>
      </footer>
    </div>
  );
}

