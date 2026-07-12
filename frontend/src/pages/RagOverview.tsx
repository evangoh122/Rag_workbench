import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Play, Database, Network, BookOpen, Clock, AlertTriangle, CheckCircle, Sparkles } from 'lucide-react';
import Presentation from './Presentation';
import CoachMarks, { useTour } from '../components/CoachMarks';
import { OVERVIEW_TOUR, OVERVIEW_TOUR_KEY } from '../components/tourSteps';
import { DisclaimerFooter } from '../components/Disclaimer';
import { getPosthog } from '../utils/posthog';

const TRACKING_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'ref'] as const;

export default function RagOverview() {
  const navigate = useNavigate();
  const { ref: refFromPath } = useParams();
  const tour = useTour(OVERVIEW_TOUR_KEY);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tracking: Record<string, string> = Object.fromEntries(
      TRACKING_PARAMS.map((k) => [k, params.get(k)]).filter(([, v]) => v) as [string, string][],
    );
    if (refFromPath) tracking.ref = refFromPath;
    getPosthog().then((p) => {
      p.capture('$pageview', { view: 'rag_overview' });
      if (Object.keys(tracking).length > 0) {
        p.capture('overview_link_visit', {
          ...tracking,
          referrer: document.referrer || null,
          path: window.location.pathname,
        });
      }
    });
  }, [refFromPath]);

  return (
    <div className="min-h-screen bg-background text-primary font-sans selection:bg-accent/20 selection:text-white flex flex-col">
      <header className="border-b border-border/40 bg-background/72 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer font-medium text-sm"
          >
            <ArrowLeft size={16} />
            Back to portfolio
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={tour.start}
              className="flex items-center gap-1.5 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer text-sm"
            >
              <Sparkles size={15} className="text-accent-bright" />
              <span className="hidden sm:inline">Tour</span>
            </button>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-md border border-accent/25 bg-accent/8 text-accent-bright">
              Product notes
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-12 md:py-16 flex flex-col gap-14">
        <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-10 lg:gap-14 items-end animate-in fade-in slide-in-from-bottom-3 duration-300">
          <div>
            <div className="flex items-center gap-3 mb-6">
              <span className="editorial-rule" />
              <span className="editorial-kicker">RAG Workbench</span>
            </div>
            <div className="flex items-center gap-3 mb-5">
              <div className="p-2.5 bg-accent/8 border border-accent/15 rounded-xl text-accent">
                <Database size={24} />
              </div>
              <p className="text-xs font-mono text-accent-bright m-0">SEC filing research with traceable answers</p>
            </div>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight leading-[0.98] text-primary m-0 max-w-3xl text-balance">
              A research app that shows its working.
            </h1>
            <p className="text-secondary text-base leading-8 font-light mt-7 max-w-3xl text-pretty">
              RAG Workbench answers financial filing questions in plain English, but the important part is what sits behind the answer: excerpts, XBRL facts, deterministic checks, graph context, and a review path a human can inspect.
            </p>

            <div className="flex flex-wrap gap-4 mt-8">
              <button
                data-tour="launch"
                onClick={() => navigate('/rag')}
                className="fintech-button px-5 py-2.5 group"
              >
                <Play size={16} className="fill-white" />
                Open the app
              </button>
              <button
                data-tour="methodology"
                onClick={() => navigate('/rag', { state: { initialView: 'methodology' } })}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-border/80 hover:bg-surface-elevated/40 text-primary font-semibold transition-all duration-200 cursor-pointer bg-transparent"
              >
                <BookOpen size={16} />
                Read methodology
              </button>
            </div>
          </div>

          <aside className="product-glass-preview rounded-2xl p-5 relative overflow-hidden">
            <div className="absolute -right-10 -top-10 w-36 h-36 bg-accent/15 blur-3xl" />
            <div className="text-[11px] font-mono text-secondary mb-4">answer anatomy</div>
            <div className="space-y-3">
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] p-3">
                <div className="text-xs text-primary font-semibold mb-2">Claim</div>
                <div className="h-2 w-5/6 rounded bg-white/10 mb-2" />
                <div className="h-2 w-2/3 rounded bg-white/8" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-accent/15 bg-accent/8 p-3">
                  <div className="text-[10px] text-accent-bright font-mono mb-3">XBRL</div>
                  <div className="h-8 rounded bg-background/50" />
                </div>
                <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] p-3">
                  <div className="text-[10px] text-secondary font-mono mb-3">source</div>
                  <div className="h-8 rounded bg-background/50" />
                </div>
              </div>
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] p-3">
                <div className="flex items-center justify-between text-[10px] font-mono text-secondary">
                  <span>verification</span>
                  <span className="text-accent-bright">reviewable</span>
                </div>
              </div>
            </div>
          </aside>
        </section>

        <section data-tour="business-case" className="scroll-mt-20 animate-in fade-in slide-in-from-bottom-4 duration-450">
          <div className="flex items-center gap-3 mb-7">
            <span className="editorial-rule" />
            <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-primary m-0">The work starts where trust breaks.</h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[0.82fr_1.18fr] gap-6 items-start">
            <div className="rounded-2xl border border-red-500/15 bg-red-500/[0.035] p-6 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-full blur-2xl pointer-events-none" />
              <div className="flex items-center gap-2 text-red-300 font-semibold mb-4 text-xs font-mono">
                <AlertTriangle size={15} />
                manual review drag
              </div>
              <p className="text-sm text-secondary leading-7 mb-6 font-light">
                Analysts can use language models for orientation, but numbers still need a source, a period, a unit, and a calculation path. Without that trail, the answer is just another thing to verify.
              </p>

              <div className="space-y-4">
                {[
                  ['30m', 'skim the filing', 'Find the right section before analysis starts.'],
                  ['2h', 'read closely', 'Check narrative, risk, and table context.'],
                  ['12h', 'model safely', 'Extract, normalize, and verify figures.'],
                ].map(([time, title, body]) => (
                  <div key={time} className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-12 text-center p-1.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300 text-xs font-mono font-semibold mt-0.5">
                      {time}
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-primary">{title}</h4>
                      <p className="text-[11px] text-secondary/70 m-0">{body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="product-glass-preview rounded-2xl p-6 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-40 h-40 bg-accent/10 rounded-full blur-3xl pointer-events-none" />
              <div className="flex items-center gap-2 text-accent-bright font-semibold mb-4 text-xs font-mono">
                <CheckCircle size={15} />
                what the app makes visible
              </div>
              <p className="text-sm text-secondary leading-7 mb-6 font-light max-w-2xl">
                The interface is less about chat and more about inspection. The answer is only one layer; the supporting evidence is treated as a first-class part of the product.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  [Clock, 'Citation anchoring', 'Numeric claims link back to filing text.'],
                  [Database, 'XBRL calculations', 'Filed facts are checked with deterministic math.'],
                  [Network, 'Graph context', 'Entities and relationships stay inspectable.'],
                ].map(([Icon, title, body]) => {
                  const LucideIcon = Icon as typeof Clock;
                  return (
                    <div key={title as string} className="glass-sm p-4">
                      <LucideIcon size={15} className="text-accent-bright mb-3" />
                      <h4 className="text-xs font-semibold text-primary mb-1">{title as string}</h4>
                      <p className="text-[11px] text-secondary/70 m-0 leading-relaxed">{body as string}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        <section className="scroll-mt-20 animate-in fade-in slide-in-from-bottom-5 duration-600">
          <div className="flex items-center justify-between mb-6 gap-4">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <span className="editorial-rule" />
                <span className="editorial-kicker">strategy deck</span>
              </div>
              <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-primary m-0">The buy-in story.</h2>
            </div>
            <a
              href="https://docs.google.com/presentation/d/1X0Bh06yYY2zbRe7yh7f0itSyiwb0ubVe/edit?usp=sharing&ouid=100592629992248688729&rtpof=true&sd=true"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent hover:text-accent-bright font-semibold"
            >
              Open in Google Slides
            </a>
          </div>

          <div className="product-glass-preview rounded-2xl overflow-hidden p-2">
            <Presentation />
          </div>
        </section>
      </main>

      <DisclaimerFooter className="mt-auto" />

      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
        </div>
      </footer>

      <CoachMarks steps={OVERVIEW_TOUR} run={tour.run} onClose={tour.close} />
    </div>
  );
}
