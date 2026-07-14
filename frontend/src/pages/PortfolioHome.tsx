import { Mail, ArrowRight, Cpu, Network, Database, Search, Sparkles } from 'lucide-react';
import type { KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import CoachMarks, { useTour } from '../components/CoachMarks';
import { LANDING_TOUR, LANDING_TOUR_KEY } from '../components/tourSteps';
import { DisclaimerFooter } from '../components/Disclaimer';

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
  const landingTour = useTour(LANDING_TOUR_KEY);
  const activateCardOnKeyDown = (event: KeyboardEvent<HTMLDivElement>, action: () => void) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    action();
  };

  return (
    <div className="min-h-screen bg-background text-primary font-sans selection:bg-accent/20 selection:text-white flex flex-col">
      <a href="#portfolio-content" className="skip-link">Skip to main content</a>
      <header className="border-b border-border/40 bg-background/72 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent-fill flex items-center justify-center font-mono font-bold text-white">
              E
            </div>
            <span className="font-semibold text-base tracking-tight">Evan Goh</span>
          </div>
          <nav className="flex items-center gap-4 sm:gap-5 text-sm">
            <button
              onClick={landingTour.start}
              className="flex items-center gap-1.5 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer p-0"
            >
              <Sparkles size={15} className="text-accent-bright" />
              <span className="hidden sm:inline">Tour</span>
            </button>
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

      <main id="portfolio-content" tabIndex={-1} className="flex-1 max-w-6xl w-full mx-auto px-5 sm:px-6 py-12 md:py-20">
        <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-10 lg:gap-16 items-center mb-18 md:mb-28">
          <div className="max-w-3xl pt-6 md:pt-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="editorial-rule" />
              <span className="editorial-kicker">product-minded AI systems</span>
            </div>
            <h1 className="text-[2.7rem] md:text-[4rem] lg:text-[4.55rem] font-semibold text-primary tracking-tight leading-[0.98] mb-7 text-balance">
              Evan Goh builds tools for reading messy financial evidence.
            </h1>
            <p className="text-secondary text-base md:text-lg leading-8 max-w-2xl font-light text-pretty">
              I work at the translation layer between product, engineering, and business judgment. The work below is about making AI systems easier to inspect, question, and trust.
            </p>
            <div className="flex flex-wrap items-center gap-5 mt-9">
              <button
                data-tour="hero-cta"
                onClick={() => document.getElementById('projects')?.scrollIntoView({ behavior: 'smooth' })}
                className="fintech-button px-5 py-3 group"
              >
                View selected work
                <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
              </button>
              <button
                onClick={() => document.getElementById('profile')?.scrollIntoView({ behavior: 'smooth' })}
                className="quiet-link bg-transparent border-0 cursor-pointer text-sm"
              >
                Read the profile
              </button>
            </div>
          </div>

          <figure className="portrait-card relative m-0 max-w-[360px] sm:max-w-[400px] lg:max-w-none">
            <div className="portrait-frame">
              <img
                src="/evan-goh.jpg"
                alt="Evan Goh in a grey suit"
                width="800"
                height="799"
                className="block w-full aspect-square object-cover object-center"
              />
            </div>
            <figcaption className="flex items-center justify-between gap-4 border-x border-b border-border bg-surface px-4 py-3 rounded-b-xl">
              <div>
                <p className="m-0 text-sm font-semibold text-primary">Evan Goh</p>
                <p className="m-0 mt-0.5 text-xs text-secondary">AI product &amp; systems builder</p>
              </div>
              <span className="inline-flex items-center gap-2 text-xs font-medium text-secondary whitespace-nowrap">
                <span className="h-2 w-2 rounded-full bg-bullish" aria-hidden="true" />
                Singapore
              </span>
            </figcaption>
          </figure>
        </section>

        <section id="profile" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-center gap-3 mb-8">
            <span className="editorial-rule" />
            <h2 className="text-lg md:text-xl font-semibold tracking-tight text-primary">Profile</h2>
          </div>

          <div className="max-w-3xl product-glass-preview rounded-2xl p-6 sm:p-8 relative overflow-hidden flex flex-col justify-center">
            <div className="absolute top-0 right-0 w-32 h-32 bg-accent/10 rounded-full blur-2xl pointer-events-none" />
            <h3 className="text-base font-semibold text-primary mb-4 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent" />
              From AI ideas to working systems
            </h3>
            <p className="text-sm text-secondary leading-7 font-light m-0 max-w-2xl">
              I turn loosely defined AI opportunities into scoped workflows, inspectable outputs, and evaluation loops that teams can operate and improve.
            </p>
          </div>
        </section>

        <section id="projects" className="mb-16 md:mb-24 scroll-mt-20">
          <div className="flex items-end justify-between mb-8 max-w-4xl gap-6">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <span className="editorial-rule" />
                <span className="editorial-kicker">selected work</span>
              </div>
              <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-primary m-0">Built around evidence, not demos.</h2>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.12fr)_minmax(280px,0.88fr)] gap-5 lg:gap-6 max-w-5xl">
            <div
              data-tour="project-card"
              onClick={() => navigate('/rag-overview')}
              onKeyDown={(event) => activateCardOnKeyDown(event, () => navigate('/rag-overview'))}
              role="button"
              tabIndex={0}
              className="product-glass-preview hover:border-accent/50 rounded-2xl transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden cursor-pointer min-h-[520px]"
            >
              <div className="absolute top-0 right-0 w-40 h-40 bg-accent/10 rounded-full blur-3xl group-hover:bg-accent/15 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent">
                      <Search size={20} />
                    </div>
                    <div>
                      <h3 className="text-xl sm:text-2xl font-semibold text-primary tracking-tight">RAG Workbench</h3>
                      <p className="text-[11px] font-mono text-accent-bright">SEC filing answers with a paper trail</p>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md border border-accent/20 bg-accent/8 text-accent-bright">
                    Case Study & App
                  </span>
                </div>

                <div className="mb-6 bg-background/42 border border-white/[0.06] rounded-xl p-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-accent-bright mb-3 font-mono">
                    why it exists
                  </div>
                  <p className="text-sm text-secondary leading-7 mb-4 font-light">
                    Analyst workflows break down when answers cannot show where the number came from. This workbench keeps retrieval, XBRL math, citations, and graph context visible.
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-left">
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">30m</div>
                      <div className="text-[10px] text-secondary/70">section scan</div>
                    </div>
                    <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">2h</div>
                      <div className="text-[10px] text-secondary/70">deep read</div>
                    </div>
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">12h</div>
                      <div className="text-[10px] text-secondary/70">model pass</div>
                    </div>
                  </div>
                </div>

                <p className="text-sm text-secondary leading-7 mb-6 font-light max-w-xl">
                  The app is intentionally sober: citations before prose, deterministic checks before confident language, and a visible audit trail for every answer.
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
                      XBRL verification
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Deterministic math checks on filed financial data</p>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1.5 max-w-md">
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">RAG</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">XBRL</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">Graph RAG</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FastAPI</span>
                </div>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-accent-bright transition-colors group-hover:underline">
                  View pitch and deck
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </div>

            <div
              onClick={() => navigate('/rag', { state: { initialView: 'stocks' } })}
              onKeyDown={(event) => activateCardOnKeyDown(event, () => navigate('/rag', { state: { initialView: 'stocks' } }))}
              role="button"
              tabIndex={0}
              className="glass-card hover:border-accent/50 rounded-2xl transition-all duration-300 flex flex-col justify-between p-6 relative group overflow-hidden cursor-pointer lg:mt-16 min-h-[430px]"
            >
              <div>
                <div className="flex items-start justify-between mb-5 flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-border/20 border border-border/35 rounded-xl text-secondary">
                      <Database size={20} />
                    </div>
                    <div>
                      <h3 className="text-base sm:text-lg font-semibold text-primary tracking-tight">Enterprise infrastructure</h3>
                      <p className="text-[11px] font-mono text-secondary">Market data architecture notes</p>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md border border-white/10 bg-white/[0.04] text-secondary">
                    Blueprint
                  </span>
                </div>

                <div className="mb-5 bg-surface-elevated/20 border border-border/20 rounded-xl p-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-secondary mb-2 font-mono">
                    operating constraint
                  </div>
                  <p className="text-xs text-secondary/80 leading-relaxed mb-3 font-light">
                    A companion architecture sketch for moving historical market bars into an analysis layer without making every query feel like a batch job.
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-center mb-3">
                    <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                      <div className="text-xs font-mono font-semibold text-secondary">10B+</div>
                      <div className="text-[9px] text-secondary/60">bars</div>
                    </div>
                    <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                      <div className="text-xs font-mono font-semibold text-secondary">&lt;15ms</div>
                      <div className="text-[9px] text-secondary/60">lookup</div>
                    </div>
                    <div className="bg-background/40 border border-border/25 rounded-lg py-1.5">
                      <div className="text-xs font-mono font-semibold text-secondary">sub-sec</div>
                      <div className="text-[9px] text-secondary/60">rollups</div>
                    </div>
                  </div>
                  <p className="text-xs text-secondary/70 leading-relaxed font-light m-0">
                    Partitioning, columnar storage, and API boundaries matter more here than one heroic model call.
                  </p>
                </div>

                <div className="mb-5 bg-surface-elevated/20 border border-border/20 rounded-xl p-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-secondary mb-2 font-mono">
                    pipeline note
                  </div>
                  <div className="font-mono text-[9px] text-secondary/60 leading-relaxed">
                    Kafka ingress -&gt; Flink SQL -&gt; ClickHouse warehouse -&gt; App API
                  </div>
                </div>

                <p className="text-xs text-secondary/70 leading-relaxed mb-6 font-light">
                  Useful because the research app should eventually answer chart and price-context questions with the same traceability discipline as filing questions.
                </p>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="glass-sm p-3.5 opacity-60">
                    <div className="flex items-center gap-2 text-secondary text-xs font-semibold mb-1">
                      <Database size={13} />
                      Stream processing
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">State tracking and stream schemas</p>
                  </div>
                  <div className="glass-sm p-3.5 opacity-60">
                    <div className="flex items-center gap-2 text-secondary text-xs font-semibold mb-1">
                      <Cpu size={13} />
                      Distributed DBs
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Partitioning, indices, and shards</p>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1">
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kafka</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">Kubernetes</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary/50 rounded">ClickHouse</span>
                </div>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-accent-bright transition-colors group-hover:underline">
                  Explore charts
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>

      <DisclaimerFooter className="mt-auto" />

      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50">
        <div className="max-w-6xl mx-auto px-6 flex flex-col items-center gap-4">
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

      <CoachMarks steps={LANDING_TOUR} run={landingTour.run} onClose={landingTour.close} />
    </div>
  );
}
