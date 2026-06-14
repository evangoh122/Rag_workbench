// Shared PostHog loader. Single source of truth for the lazy import + init,
// so the boilerplate isn't duplicated across components and — critically —
// init happens *inside* the same promise the callers chain their capture()
// off, eliminating the init-vs-capture race.

let _posthog: Promise<typeof import('posthog-js').default> | null = null;
let _initialized = false;

/**
 * Fire-and-forget mirror of an event into our own DuckDB sink
 * (POST /api/analytics/track). Never blocks or throws — analytics must never
 * affect the app's UX. Lets the Product Analytics page read from owned data
 * without depending on PostHog's API.
 */
function _sinkToDuckDB(
  event: string,
  properties: Record<string, unknown>,
  distinctId?: string,
) {
  try {
    const base = import.meta.env.VITE_API_BASE ?? '/api';
    fetch(`${base}/analytics/track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, properties, distinct_id: distinctId }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* ignore */
  }
}

/**
 * Lazily load PostHog, initialising it exactly once. Any `.capture()` chained
 * off the returned promise is guaranteed to run after `init()` because init is
 * performed synchronously inside this promise before the client is returned.
 *
 * No-op-safe: callers still guard on `import.meta.env.VITE_POSTHOG_KEY`, and if
 * the key is unset the client loads but is never initialised, so captures drop.
 */
export function getPosthog() {
  if (!_posthog) {
    _posthog = import('posthog-js').then(({ default: posthog }) => {
      const key = import.meta.env.VITE_POSTHOG_KEY;
      if (key && !_initialized) {
        posthog.init(key, {
          api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
          person_profiles: 'identified_only',
        });
        // Mirror every captured event into our own DuckDB sink so the Product
        // Analytics page can read from owned, persisted data.
        const _origCapture = posthog.capture.bind(posthog);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (posthog as any).capture = (event: any, properties?: any, options?: any) => {
          try {
            const did = typeof posthog.get_distinct_id === 'function'
              ? posthog.get_distinct_id()
              : undefined;
            _sinkToDuckDB(String(event), (properties ?? {}) as Record<string, unknown>, did);
          } catch {
            /* ignore */
          }
          return _origCapture(event, properties, options);
        };
        _initialized = true;
      }
      return posthog;
    });
  }
  return _posthog;
}
