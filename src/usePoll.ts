// One polling lifecycle for every screen.
//
// Guarantees:
//  - loads once on mount, then every intervalMs
//  - never runs two requests at the same time: a request that is already open is
//    shared rather than duplicated
//  - clears its timer and ignores late responses on unmount
//  - a manual refresh reuses exactly the same loader as the timer
//  - stops when the data says the work is finished, and stops hammering after a
//    permanent (4xx) error or too many consecutive failures
//  - the loader is read through a ref, so an inline arrow function in the caller
//    does not restart the timer on every render
//
// The in-flight request is shared because React StrictMode mounts, unmounts and
// re-mounts effects in development. Skipping the second run instead of joining it
// would discard the first response and leave the screen empty for a whole
// interval; joining it means the first paint is immediate and still one request.

import { useEffect, useRef, useState } from "react";
import { ApiError, getTransport, type Source } from "./api";

const MAX_CONSECUTIVE_FAILURES = 5;

export interface PollOptions<T> {
  /** Milliseconds between requests. 0 or less loads once, on open. */
  intervalMs: number;
  enabled?: boolean;
  /** Return false to stop polling once the work behind this resource is finished. */
  shouldContinue?: (data: T) => boolean;
}

export interface PollState<T> {
  data: T | null;
  error: string;
  /** True only until the first response settles. */
  loading: boolean;
  /** True while a request is in flight, including refreshes. */
  busy: boolean;
  lastUpdated: number | null;
  /** True when polling stopped because the resource is finished or unrecoverable. */
  finished: boolean;
  /** Where the body on this panel came from: the real API, mock mode, or a fallback. */
  source: Source;
  /** Run the loader again now and restart the interval. */
  refresh: () => void;
}

export function usePoll<T>(
  load: () => Promise<T>,
  { intervalMs, enabled = true, shouldContinue }: PollOptions<T>,
): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [source, setSource] = useState<Source>("unknown");
  // Bumping this restarts the effect: an immediate load plus a fresh interval.
  const [nonce, setNonce] = useState(0);

  const loadRef = useRef(load);
  loadRef.current = load;
  const contRef = useRef(shouldContinue);
  contRef.current = shouldContinue;

  // The request currently open, shared by anything that asks while it is open.
  const pending = useRef<Promise<T> | null>(null);
  const failures = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: number | undefined;
    let stop = false;
    let running = false;
    const recurring = intervalMs > 0;

    setFinished(false);

    const join = (): Promise<T> => {
      if (!pending.current) {
        pending.current = loadRef.current().finally(() => {
          pending.current = null;
        });
      }
      return pending.current;
    };

    const tick = async (): Promise<void> => {
      if (!alive || stop || running) return;
      running = true;
      setBusy(true);
      try {
        const result = await join();
        if (!alive) return;
        failures.current = 0;
        setData(result);
        setError("");
        setLastUpdated(Date.now());
        if (contRef.current && !contRef.current(result)) {
          stop = true;
          setFinished(true);
        }
      } catch (e: any) {
        if (!alive) return;
        const status = e instanceof ApiError ? e.status : 0;
        setError(e?.message || "The request failed.");
        failures.current += 1;
        // A 4xx will not fix itself by asking again; a 401 already redirected.
        const permanent =
          (status >= 400 && status < 500) ||
          failures.current >= MAX_CONSECUTIVE_FAILURES;
        if (permanent) {
          stop = true;
          setFinished(true);
        }
      } finally {
        running = false;
        if (alive) {
          setBusy(false);
          setLoading(false);
          // The client records this for every completed request, including a
          // fallback that was answered from mock_for_now/.
          setSource(getTransport().source);
        }
      }

      if (alive && !stop && recurring)
        timer = window.setTimeout(tick, intervalMs);
    };

    void tick();

    return () => {
      alive = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, intervalMs, nonce]);

  return {
    data,
    error,
    loading,
    busy,
    lastUpdated,
    finished,
    source,
    refresh: () => setNonce((n) => n + 1),
  };
}
