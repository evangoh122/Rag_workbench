import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, X } from 'lucide-react';

const ACK_KEY = 'rw_analytics_notice_ack_v1';

function acked(): boolean {
  try {
    return localStorage.getItem(ACK_KEY) === '1';
  } catch {
    return true; // Storage blocked; do not nag.
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
  const [open, setOpen] = useState(() => !acked());

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
    <div className="fixed inset-x-0 bottom-0 z-[200] flex justify-center px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pointer-events-none">
      <div
        role="status"
        aria-label="Analytics notice"
        className="pointer-events-auto w-full max-w-xl flex items-start gap-3 rounded-xl border border-border bg-surface px-3 sm:px-4 py-3 shadow-lg"
      >
        <span className="mt-0.5 text-accent-bright shrink-0">
          <BarChart3 size={16} />
        </span>
        <p className="text-xs sm:text-[12.5px] text-secondary leading-relaxed m-0 flex-1">
          <span className="sm:hidden">Limited analytics help improve this app. No advertising use. </span>
          <span className="hidden sm:inline">This application uses limited analytics to understand feature usage and improve the experience. We do not use this data for advertising. </span>
          See our{' '}
          <button
            onClick={() => navigate('/privacy')}
            className="text-accent-bright hover:text-accent underline underline-offset-2 bg-transparent border-0 p-0 cursor-pointer"
          >
            Privacy Policy
          </button>{' '}
          for details.
        </p>
        <button
          onClick={dismiss}
          aria-label="Dismiss analytics notice"
          className="shrink-0 -mr-1 -mt-1 p-2 rounded-md text-secondary hover:text-primary hover:bg-surface-elevated transition-colors bg-transparent border-0 cursor-pointer"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
