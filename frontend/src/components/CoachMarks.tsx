import { type CSSProperties, useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { X, ArrowRight, ArrowLeft, Sparkles } from 'lucide-react';
import { disclaimerAcked, DISCLAIMER_ACK_EVENT } from './Disclaimer';

/**
 * A single step in a guided tour. When `selector` matches an element on the
 * page, that element is spotlighted and the tooltip is anchored to it. When the
 * selector is omitted (or matches nothing), the step renders as a centred card.
 */
export interface CoachStep {
  selector?: string;
  title: string;
  body: string;
  placement?: 'top' | 'bottom' | 'auto';
}

interface CoachMarksProps {
  steps: CoachStep[];
  run: boolean;
  onClose: () => void;
}

const PAD = 8; // spotlight padding around the target
const CARD_W = 320;

/**
 * Lightweight, dependency-free coach-mark / product-tour overlay. Dims the page,
 * spotlights the current step's target, and shows a tooltip with Back / Next /
 * Skip controls. Recomputes on resize + scroll, scrolls targets into view, and
 * degrades to a centred card when a target is missing (so a tour never gets
 * stuck on an element that didn't render).
 */
export default function CoachMarks({ steps, run, onClose }: CoachMarksProps) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const step = steps[index];

  const measure = useCallback(() => {
    if (!step?.selector) {
      setRect(null);
      return;
    }
    const el = document.querySelector(step.selector) as HTMLElement | null;
    if (!el) {
      setRect(null);
      return;
    }
    setRect(el.getBoundingClientRect());
  }, [step]);

  // Reset to the first step each time the tour is (re)started.
  useEffect(() => {
    if (run) setIndex(0);
  }, [run]);

  // Bring the target into view, then measure once it has settled.
  useLayoutEffect(() => {
    if (!run) return;
    const el = step?.selector
      ? (document.querySelector(step.selector) as HTMLElement | null)
      : null;
    el?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    const t = window.setTimeout(measure, el ? 280 : 0);
    return () => window.clearTimeout(t);
  }, [run, step, measure]);

  useEffect(() => {
    if (!run) return;
    const onChange = () => measure();
    window.addEventListener('resize', onChange);
    window.addEventListener('scroll', onChange, true);
    return () => {
      window.removeEventListener('resize', onChange);
      window.removeEventListener('scroll', onChange, true);
    };
  }, [run, measure]);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i >= steps.length - 1) {
        onClose();
        return i;
      }
      return i + 1;
    });
  }, [steps.length, onClose]);

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    if (!run) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') back();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [run, next, back, onClose]);

  if (!run || !step) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const isMobile = vw < 640;

  // Tooltip position. On mobile (or with no target) the card pins to the bottom
  // centre; on desktop it sits below the target, flipping above when there is no
  // room, and is clamped to stay on-screen.
  let cardStyle: CSSProperties;
  if (!rect || isMobile) {
    cardStyle = {
      left: Math.max(12, (vw - Math.min(CARD_W, vw - 24)) / 2),
      bottom: 20,
      width: Math.min(CARD_W, vw - 24),
    };
  } else {
    const below = rect.bottom + 12;
    const wantAbove = below + 180 > vh && rect.top > 200;
    const top = wantAbove ? undefined : below;
    const bottom = wantAbove ? vh - rect.top + 12 : undefined;
    let left = rect.left + rect.width / 2 - CARD_W / 2;
    left = Math.min(Math.max(12, left), vw - CARD_W - 12);
    cardStyle = { left, top, bottom, width: CARD_W };
  }

  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-label="Guided tour">
      {/* Spotlight (or full dim when no target). The huge box-shadow dims the rest
          of the page while leaving the target cut-out bright. */}
      {rect && !isMobile ? (
        <div
          className="absolute rounded-xl pointer-events-none transition-all duration-200"
          style={{
            left: rect.left - PAD,
            top: rect.top - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.58)',
            border: '2px solid rgba(167,139,250,0.9)',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/58" />
      )}

      {/* Click-catcher so the page underneath isn't interactive mid-tour. */}
      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />

      {/* Tooltip card */}
      <div
        className="absolute glass-modal p-4 sm:p-5 animate-in fade-in zoom-in-95 duration-200 shadow-2xl"
        style={cardStyle}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2 text-accent-bright">
            <Sparkles size={15} />
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
              Step {index + 1} of {steps.length}
            </span>
          </div>
          <button
            onClick={onClose}
            aria-label="Skip tour"
            className="p-1 -m-1 text-secondary hover:text-primary bg-transparent border-0 cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        <h3 className="text-[15px] font-semibold text-primary mb-1.5 tracking-tight">{step.title}</h3>
        <p className="text-[13px] text-secondary leading-relaxed m-0">{step.body}</p>

        {/* Progress dots */}
        <div className="flex items-center gap-1.5 mt-4 mb-3">
          {steps.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all duration-200 ${
                i === index ? 'w-5 bg-accent' : 'w-1.5 bg-white/15'
              }`}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            onClick={onClose}
            className="text-[12px] text-muted hover:text-secondary bg-transparent border-0 p-0 cursor-pointer"
          >
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {index > 0 && (
              <button
                onClick={back}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg glass-button text-[13px] text-secondary hover:text-primary"
              >
                <ArrowLeft size={13} /> Back
              </button>
            )}
            <button
              onClick={next}
              className="fintech-button px-3.5 py-1.5 text-[13px]"
            >
              {index >= steps.length - 1 ? 'Done' : 'Next'}
              {index < steps.length - 1 && <ArrowRight size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * localStorage helper: returns true the first time a tour key is seen (so a tour
 * auto-runs once), and exposes a setter to mark it complete. Versioned keys let
 * a materially-changed tour re-show.
 */
export function tourSeen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return true; // storage blocked → treat as seen, never nag
  }
}

export function markTourSeen(key: string): void {
  try {
    localStorage.setItem(key, '1');
  } catch {
    /* ignore */
  }
}

/**
 * Drives a single tour: auto-runs it once per `storageKey` (only after the
 * disclaimer is acknowledged, and only while `enabled`), marks it seen on close,
 * and exposes `start()` for a manual replay button. `delayMs` lets a host wait
 * for its target elements to mount before the spotlight measures them.
 */
export function useTour(storageKey: string, enabled = true, delayMs = 600) {
  const [run, setRun] = useState(false);

  useEffect(() => {
    if (!enabled || tourSeen(storageKey)) return;

    let timer = 0;
    const arm = () => {
      timer = window.setTimeout(() => setRun(true), delayMs);
    };
    if (disclaimerAcked()) {
      arm();
    } else {
      // Wait for the first-visit disclaimer to be acknowledged first.
      const onAck = () => arm();
      window.addEventListener(DISCLAIMER_ACK_EVENT, onAck, { once: true });
      return () => {
        window.removeEventListener(DISCLAIMER_ACK_EVENT, onAck);
        window.clearTimeout(timer);
      };
    }
    return () => window.clearTimeout(timer);
  }, [storageKey, enabled, delayMs]);

  const close = useCallback(() => {
    setRun(false);
    markTourSeen(storageKey);
  }, [storageKey]);

  const start = useCallback(() => setRun(true), []);

  return { run, start, close };
}
