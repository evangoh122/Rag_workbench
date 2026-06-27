import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, X } from 'lucide-react';

const ACK_KEY = 'rw_analytics_notice_ack_v1';

function acked(): boolean {
  try {
    return localStorage.getItem(ACK_KEY) === '1';
  } catch {
    return true; // storage blocked → don't nag
  }
}

/**
 * Slim, dismissible analytics-transparency banner. Shown once (gated by
 * localStorage) so visitors are told, up front, that the app records anonymous
 * usage analytics and where to read the details. Deliberately lighter-weight
 * than the blocking not-investment-advice modal: analytics is non-blocking, so
 * this just informs and links to the Privacy Policy.
 */
export default function AnalyticsNotice() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!acked()) setOpen(true);
  }, []);

  if (!open) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(ACK_KEY, '1');
    } catch {
      /* ignore */
    }
    setOpen(false);
  };

  return (
    <div className="fixed inset-x-0 bottom-0 z-[200] flex justify-center px-3 pb-3 pointer-events-none">
      <div className="pointer-events-auto w-full max-w-2xl flex items-start gap-3 rounded-xl border border-border/60 bg-surface/95 backdrop-blur-md px-4 py-3 shadow-lg">
        <span className="mt-0.5 text-emerald-400 shrink-0">
          <BarChart3 size={16} />
        </span>
        <p className="text-[12.5px] text-secondary leading-relaxed m-0 flex-1">
          This application uses analytics to understand feature usage and improve the experience. We
          collect limited usage data and do not use it for advertising. By continuing, you acknowledge
          this collection. See our{' '}
          <button
            onClick={() => navigate('/privacy')}
            className="text-emerald-400/90 hover:text-emerald-300 underline underline-offset-2 bg-transparent border-0 p-0 cursor-pointer"
          >
            Privacy Policy
          </button>{' '}
          for details.
        </p>
        <button
          onClick={dismiss}
          aria-label="Dismiss analytics notice"
          className="shrink-0 -mr-1 -mt-1 p-1 rounded-md text-secondary/60 hover:text-primary hover:bg-surface-elevated transition-colors bg-transparent border-0 cursor-pointer"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
