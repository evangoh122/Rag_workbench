import { Mail, ArrowRight, Network, Database, Search, Sparkles, Flame, ShieldCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent, PointerEvent } from 'react';
import { motion, useMotionValue, useTransform, animate } from 'motion/react';
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

const GithubIcon = ({ size = 20 }: { size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.335-1.756-1.335-1.756-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
  </svg>
);

const PROJECT_TITLES = ['RAG Workbench', 'Haze Watch', 'Quant Platform'];
const PROJECT_COUNT = PROJECT_TITLES.length;

// How far (in px) a drag must travel to fully traverse one card position -
// independent of the resting peek distance below, which is a much smaller
// visual offset. Tuned so a deliberate swipe, not an accidental nudge, commits.
const DRAG_CARD_PITCH = 320;

// Apple's exponential-decay projection (Designing Fluid Interfaces, WWDC18):
// projects where a release velocity would coast to, so a flick lands further
// than a slow drag released at the same point. Works in "cards" units here
// (not px) since that's what `position` below is measured in - the formula
// is unit-agnostic.
function projectMomentum(velocity: number, decelerationRate = 0.998) {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

function wrap(index: number) {
  return ((index % PROJECT_COUNT) + PROJECT_COUNT) % PROJECT_COUNT;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

export default function PortfolioHome() {
  const navigate = useNavigate();
  const [activeProject, setActiveProject] = useState(0);
  const deckRef = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();

  // `position` is the single continuous value driving the whole deck: it
  // equals `activeProject` at rest, and tracks the pointer 1:1 while
  // dragging ("touch and content should move together"). Every card's
  // transform is derived from its own distance to this value, so dragging
  // between cards 0 and 1 moves every card in the stack at once, not just
  // the one under the finger.
  const position = useMotionValue(activeProject);
  const settleAnimation = useRef<ReturnType<typeof animate> | null>(null);

  // The resting peek distances (index.css: --deck-peek / --deck-peek-2) stay
  // CSS-driven across breakpoints; this just mirrors their current computed
  // value so the JS-driven interpolation below agrees with them at rest.
  const [peek, setPeek] = useState({ near: 40, far: 80 });
  useEffect(() => {
    const read = () => {
      const el = deckRef.current;
      if (!el) return;
      const style = getComputedStyle(el);
      const near = parseFloat(style.getPropertyValue('--deck-peek')) || 40;
      const far = parseFloat(style.getPropertyValue('--deck-peek-2')) || 80;
      setPeek({ near, far });
      // Nudge the derived card transforms (keyed off `position`, not `peek`)
      // to recompute with the latest peek closure immediately on resize,
      // rather than waiting for the next drag/commit.
      position.set(position.get());
    };
    read();
    window.addEventListener('resize', read);
    return () => window.removeEventListener('resize', read);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const commitTo = (target: number, velocity = 0) => {
    const next = wrap(target);
    setActiveProject(next);
    settleAnimation.current?.stop();
    settleAnimation.current = animate(
      position,
      next,
      reducedMotion
        ? { duration: 0.15, ease: 'easeOut' }
        : {
            type: 'spring',
            velocity,
            // Bounce only when the gesture itself carried momentum - overshoot
            // on a button/dot click (no gesture behind it) would feel wrong.
            bounce: velocity ? 0.2 : 0,
            duration: 0.4,
          },
    );
  };

  const moveProject = (delta: number) => commitTo(activeProject + delta);

  const activateCardOnKeyDown = (event: KeyboardEvent<HTMLDivElement>, action: () => void) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    action();
  };
  // Static a11y attributes only - no ref access here, so this stays a plain
  // helper. The ref-touching onClick/onKeyDown (commitTo closes over the
  // settleAnimation ref) are set directly inline in JSX at each card site
  // instead of flowing through a returned object, so the compiler can see
  // the ref is only ever read inside a real, directly-authored event handler.
  type DeckCardA11y = {
    role?: 'button';
    tabIndex?: number;
    'aria-label'?: string;
    inert?: boolean;
    'aria-hidden'?: boolean;
  };
  const deckCardA11y = (index: number): DeckCardA11y => {
    const offset = index - activeProject;
    if (offset === 0) return {};
    if (Math.abs(offset) > 2) return { inert: true, 'aria-hidden': true };
    // A card behind the active one is hidden from assistive tech, so the wrapper
    // is the control that brings it forward.
    return { role: 'button', tabIndex: 0, 'aria-label': `Show ${PROJECT_TITLES[index]}` };
  };
  const onDeckKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      moveProject(1);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      moveProject(-1);
    }
  };

  // Drag: 1:1 pointer tracking the whole way through (never animate only on
  // release), a short position/time history for release velocity, and
  // momentum projection so a flick lands further than a slow drag released
  // at the same point. Grabbing the deck again mid-settle interrupts the
  // in-flight spring at its live value - no waiting for it to finish first.
  const dragFrom = useRef<number | null>(null);
  const dragStartPosition = useRef(0);
  const dragHistory = useRef<Array<{ x: number; t: number }>>([]);
  const dragged = useRef(false);
  const onDeckPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    settleAnimation.current?.stop();
    dragFrom.current = event.clientX;
    dragStartPosition.current = position.get();
    dragHistory.current = [{ x: event.clientX, t: event.timeStamp }];
    dragged.current = false;
  };
  const onDeckPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragFrom.current;
    if (start === null) return;
    const deltaX = event.clientX - start;
    if (Math.abs(deltaX) > 6) dragged.current = true;
    position.set(dragStartPosition.current - deltaX / DRAG_CARD_PITCH);
    const history = dragHistory.current;
    history.push({ x: event.clientX, t: event.timeStamp });
    while (history.length > 1 && event.timeStamp - history[0].t > 100) history.shift();
  };
  const onDeckPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragFrom.current;
    dragFrom.current = null;
    if (start === null) return;
    const history = dragHistory.current;
    const first = history[0];
    const last = history[history.length - 1] ?? { x: event.clientX, t: event.timeStamp };
    const dt = last.t - first.t;
    // Finger velocity in px/s, converted to the same "cards" unit `position`
    // is measured in, then handed off as the spring's initial velocity so
    // there's no visible seam between drag and animation.
    const pxVelocity = dt > 0 ? (last.x - first.x) / (dt / 1000) : 0;
    const cardVelocity = -pxVelocity / DRAG_CARD_PITCH;
    const projected = position.get() + projectMomentum(cardVelocity);
    const startIndex = dragStartPosition.current;
    const target = clamp(Math.round(projected), startIndex - 1, startIndex + 1);
    commitTo(target, cardVelocity);
  };
  const onDeckClickCapture = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragged.current) return;
    dragged.current = false;
    event.preventDefault();
    event.stopPropagation();
  };

  // One derived-value set per card, keyed off its live distance to
  // `position` - dragging or settling moves every card in the stack at
  // once. Called at a fixed number of sites (3 literal cards), same order
  // every render, so this satisfies the rules of hooks despite not being a
  // .map() - see cardStyle0/1/2 below.
  function useCardStyle(index: number) {
    const offset = useTransform(position, (p) => index - p);
    const x = useTransform(offset, (v) => {
      const magnitude = Math.min(Math.abs(v), 2);
      const sign = v < 0 ? -1 : 1;
      const px = magnitude <= 1 ? peek.near * magnitude : peek.near + (peek.far - peek.near) * (magnitude - 1);
      return sign * px;
    });
    const scale = useTransform(offset, [-2, -1, 0, 1, 2], [0.88, 0.94, 1, 0.94, 0.88]);
    // Opacity only hides cards past the visible stack (|offset| > 2) - the
    // "receding" dimming within the stack is brightness (below), not opacity.
    // The wrapper's own opaque backing lives on this same element, so fading
    // *its* opacity as a card is dragged out would fade the backing too,
    // letting whatever's behind it bleed through mid-drag.
    const opacity = useTransform(offset, [-3, -2, 2, 3], [0, 1, 1, 0]);
    const brightness = useTransform(offset, [-2, -1, 0, 1, 2], [0.6, 0.6, 1, 0.6, 0.6]);
    const filter = useTransform(brightness, (b) => `brightness(${b})`);
    const zIndex = useTransform(offset, (v) => Math.round(30 - Math.min(Math.abs(v), 3) * 10));
    const transformOrigin = useTransform(offset, (v) => (v >= 0 ? 'right center' : 'left center'));
    return { x, scale, opacity, filter, zIndex, transformOrigin };
  }
  const cardStyle0 = useCardStyle(0);
  const cardStyle1 = useCardStyle(1);
  const cardStyle2 = useCardStyle(2);

  const landingTour = useTour(LANDING_TOUR_KEY);

  return (
    <div className="min-h-screen bg-background text-primary font-sans flex flex-col">
      <a href="#portfolio-content" className="skip-link">Skip to main content</a>
      <header className="border-b border-border/40 bg-background/72 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent-fill flex items-center justify-center font-mono font-bold text-accent-ink">
              E
            </div>
            <span className="font-semibold text-base tracking-tight">Evan Goh</span>
          </div>
          <nav data-tour="contact" className="flex items-center gap-4 sm:gap-5 text-sm">
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
              aria-label="Visit Evan Goh's LinkedIn profile"
              title="LinkedIn"
              className="text-secondary hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <LinkedinIcon size={15} />
              <span className="hidden sm:inline">LinkedIn</span>
            </a>
            <a
              href="https://github.com/evangoh122"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Visit Evan Goh's GitHub profile"
              title="GitHub"
              className="text-secondary hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <GithubIcon size={15} />
              <span className="hidden sm:inline">GitHub</span>
            </a>
            <a
              href="mailto:evangohsg@gmail.com"
              aria-label="Contact Evan Goh"
              title="Contact"
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

          <div className="relative max-w-5xl">
            <div
              ref={deckRef}
              data-tour="project-deck"
              className="haze-deck relative"
              role="group"
              aria-roledescription="carousel"
              aria-label="Selected work"
              tabIndex={0}
              onKeyDown={onDeckKeyDown}
              onPointerDown={onDeckPointerDown}
              onPointerMove={onDeckPointerMove}
              onPointerUp={onDeckPointerUp}
              onPointerCancel={onDeckPointerUp}
              onClickCapture={onDeckClickCapture}
            >
              <motion.div
                className="haze-deck-card"
                style={cardStyle0}
                {...deckCardA11y(0)}
                onClick={activeProject === 0 ? undefined : () => commitTo(0)}
                onKeyDown={activeProject === 0 ? undefined : (event) => activateCardOnKeyDown(event, () => commitTo(0))}
              >
            <div
              data-tour="project-card"
              onClick={() => navigate('/projects/rag-workbench')}
              onKeyDown={(event) => activateCardOnKeyDown(event, () => navigate('/projects/rag-workbench'))}
              role="button"
              tabIndex={activeProject === 0 ? 0 : -1}
              aria-hidden={activeProject !== 0}
              inert={activeProject !== 0}
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
              </motion.div>

              <motion.div
                className="haze-deck-card"
                style={cardStyle1}
                {...deckCardA11y(1)}
                onClick={activeProject === 1 ? undefined : () => commitTo(1)}
                onKeyDown={activeProject === 1 ? undefined : (event) => activateCardOnKeyDown(event, () => commitTo(1))}
              >
            <div
              data-tour="project-card"
              onClick={() => navigate('/projects/haze-watch')}
              onKeyDown={(event) => activateCardOnKeyDown(event, () => navigate('/projects/haze-watch'))}
              role="button"
              tabIndex={activeProject === 1 ? 0 : -1}
              aria-hidden={activeProject !== 1}
              inert={activeProject !== 1}
              className="product-glass-preview hover:border-accent/50 rounded-2xl transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden cursor-pointer min-h-[520px]"
            >
              <div className="absolute top-0 right-0 w-40 h-40 bg-accent/10 rounded-full blur-3xl group-hover:bg-accent/15 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent">
                      <Flame size={20} />
                    </div>
                    <div>
                      <h3 className="text-xl sm:text-2xl font-semibold text-primary tracking-tight">Haze Watch</h3>
                      <p className="text-[11px] font-mono text-accent-bright">Geospatial climate risk for lenders</p>
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
                    Banks and insurers hold plantation portfolios exposed to recurring wildfire and haze, yet the link from environmental hazard to borrower cash flow is rarely modeled end to end. Haze Watch joins real NASA fire observations to concession geography and runs auditable credit stress scenarios.
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-left">
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">300</div>
                      <div className="text-[10px] text-secondary/70">real concession polygons</div>
                    </div>
                    <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">24-72h</div>
                      <div className="text-[10px] text-secondary/70">hazard horizons</div>
                    </div>
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">75</div>
                      <div className="text-[10px] text-secondary/70">pipeline tests</div>
                    </div>
                  </div>
                </div>

                <p className="text-sm text-secondary leading-7 mb-6 font-light max-w-xl">
                  Real environmental data, entirely synthetic commercial data. Every credit ratio traces to a documented formula, every dataset carries its provenance and licence, and hazard scores are labeled baselines - never probabilities of default.
                </p>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <Flame size={13} />
                      Real fire observations
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">NASA FIRMS detections and ERA5 weather joined to concession geography</p>
                  </div>
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <ShieldCheck size={13} />
                      Auditable stress tests
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Scenario engines with full calculation traces and guardrailed analyst chat</p>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1.5 max-w-md">
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">Geospatial</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FastAPI</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">MapLibre</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">DuckDB</span>
                </div>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-accent-bright transition-colors group-hover:underline">
                  View case study
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </div>
              </motion.div>
              <motion.div
                className="haze-deck-card"
                style={cardStyle2}
                {...deckCardA11y(2)}
                onClick={activeProject === 2 ? undefined : () => commitTo(2)}
                onKeyDown={activeProject === 2 ? undefined : (event) => activateCardOnKeyDown(event, () => commitTo(2))}
              >
            <a
              data-tour="project-card"
              href="https://github.com/evangoh122/quant_platform_1"
              target="_blank"
              rel="noopener noreferrer"
              tabIndex={activeProject === 2 ? 0 : -1}
              aria-hidden={activeProject !== 2}
              inert={activeProject !== 2}
              className="product-glass-preview hover:border-accent/50 rounded-2xl transition-all duration-300 flex flex-col justify-between p-6 sm:p-8 relative group overflow-hidden cursor-pointer min-h-[520px]"
            >
              <div className="absolute top-0 right-0 w-40 h-40 bg-accent/10 rounded-full blur-3xl group-hover:bg-accent/15 transition-colors pointer-events-none" />
              <div>
                <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-accent/8 border border-accent/15 rounded-xl text-accent">
                      <Database size={20} />
                    </div>
                    <div>
                      <h3 className="text-xl sm:text-2xl font-semibold text-primary tracking-tight">Quant Platform</h3>
                      <p className="text-[11px] font-mono text-accent-bright">Point-in-time equity research on Databricks</p>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md border border-accent/20 bg-accent/8 text-accent-bright">
                    Open Source - Repo
                  </span>
                </div>

                <div className="mb-6 bg-background/42 border border-white/[0.06] rounded-xl p-4">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-accent-bright mb-3 font-mono">
                    why it exists
                  </div>
                  <p className="text-sm text-secondary leading-7 mb-4 font-light">
                    A backtest is only as honest as what it was allowed to know. Quant Platform ingests market, options, SEC, COT and macro data with PySpark into a Delta medallion lakehouse, stamps every row with when it became available so features join point-in-time, and lets an LLM-directed agent research a company and save a note through a deterministic validator.
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-left">
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">287M</div>
                      <div className="text-[10px] text-secondary/70">rows ingested</div>
                    </div>
                    <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">5</div>
                      <div className="text-[10px] text-secondary/70">data domains</div>
                    </div>
                    <div className="bg-white/[0.035] border border-white/[0.06] rounded-lg p-3">
                      <div className="text-sm font-mono font-semibold text-accent-bright">8+</div>
                      <div className="text-[10px] text-secondary/70">Lakebase tables</div>
                    </div>
                  </div>
                </div>

                <p className="text-sm text-secondary leading-7 mb-6 font-light max-w-xl">
                  Real market and filing data, with the limits stated as plainly as the results: signals are labelled an untuned baseline with no predictive edge claimed, and agent writes are validated, idempotent and logged before they reach the database.
                </p>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <Network size={13} />
                      Point-in-time joins
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Silver stamps information_available_ts so features cannot see the future</p>
                  </div>
                  <div className="glass-sm p-3.5">
                    <div className="flex items-center gap-2 text-accent text-xs font-semibold mb-1">
                      <ShieldCheck size={13} />
                      Validated agent writes
                    </div>
                    <p className="text-[11px] text-secondary/70 m-0">Allowlist, roles, write scope and idempotency checked before any Lakebase write</p>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/30 pt-5 mt-2 flex-wrap gap-3">
                <div className="flex flex-wrap gap-1.5 max-w-md">
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">Databricks</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">PySpark</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">Delta Lake</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">FastAPI</span>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 bg-surface-elevated border border-border text-secondary rounded">React</span>
                </div>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent group-hover:text-accent-bright transition-colors group-hover:underline">
                  View the repo
                  <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </a>
              </motion.div>
            </div>
          <div className="mt-6 flex items-center justify-center gap-4" role="group" aria-label="Project carousel">
            <button
              type="button"
              aria-label="Previous project"
              onClick={() => moveProject(-1)}
              className="haze-proj-prev flex h-9 w-9 items-center justify-center rounded-full border border-border/80 bg-surface-elevated/40 text-secondary transition-colors hover:border-accent/50 hover:text-primary cursor-pointer"
            >
              ‹
            </button>
            <div className="flex items-center gap-2">
              {PROJECT_TITLES.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  aria-label={`Show project ${i + 1}`}
                  aria-current={activeProject === i}
                  onClick={() => commitTo(i)}
                  className={`h-2 rounded-full transition-all duration-200 cursor-pointer ${activeProject === i ? 'w-6 bg-accent' : 'w-2 bg-border hover:bg-secondary'}`}
                />
              ))}
            </div>
            <button
              type="button"
              aria-label="Next project"
              onClick={() => moveProject(1)}
              className="haze-proj-next flex h-9 w-9 items-center justify-center rounded-full border border-border/80 bg-surface-elevated/40 text-secondary transition-colors hover:border-accent/50 hover:text-primary cursor-pointer"
            >
              ›
            </button>
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
            Disclaimer: This is a personal portfolio and ongoing area of exploration. All views expressed are my own. Environmental data is publicly sourced; demo companies and financial figures are synthetic. Not related to my work.
          </p>
        </div>
      </footer>

      <CoachMarks steps={LANDING_TOUR} run={landingTour.run} onClose={landingTour.close} />
    </div>
  );
}
