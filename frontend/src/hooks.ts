import { useCallback, useEffect, useRef, useState } from "react";

export function usePoll<T>(
  load: (signal: AbortSignal) => Promise<T>,
  interval:
    number | ((data: T | undefined, receivedAt: number) => number) = 10000,
  key = "",
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [revision, setRevision] = useState(0);
  const ref = useRef(load);
  ref.current = load;
  const intervalRef = useRef(interval);
  intervalRef.current = interval;
  const latest = useRef<{ data?: T; receivedAt: number }>({ receivedAt: 0 });
  // Callback identity changes on render; only a fixed interval change restarts a request.
  const fixedInterval = typeof interval === "number" ? interval : undefined;
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    latest.current = { receivedAt: 0 };
    setData(undefined);
    setError("");
    setLoading(true);
  }, [key]);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;
    function schedule() {
      const delay =
        typeof intervalRef.current === "number"
          ? intervalRef.current
          : intervalRef.current(latest.current.data, latest.current.receivedAt);
      if (delay > 0) timer = setTimeout(run, delay);
    }
    async function run() {
      if (document.hidden) {
        schedule();
        return;
      }
      request?.abort();
      request = new AbortController();
      const current = request;
      setLoading(true);
      try {
        const result = await ref.current(current.signal);
        if (!disposed && current === request) {
          const receivedAt = Date.now();
          latest.current = { data: result, receivedAt };
          setData(result);
          setError("");
          setUpdatedAt(receivedAt);
        }
      } catch (err) {
        if (!disposed && current === request && !current.signal.aborted)
          setError(err instanceof Error ? err.message : "Could not load data.");
      } finally {
        if (!disposed && current === request) {
          setLoading(false);
          schedule();
        }
      }
    }
    function visible() {
      if (!document.hidden) {
        clearTimeout(timer);
        void run();
      }
    }
    void run();
    document.addEventListener("visibilitychange", visible);
    return () => {
      disposed = true;
      clearTimeout(timer);
      request?.abort();
      document.removeEventListener("visibilitychange", visible);
    };
  }, [fixedInterval, revision, key]);
  return { data, error, loading, updatedAt, refresh };
}

export function useClock() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

export function useRoute() {
  const [route, setRoute] = useState(location.hash.slice(2) || "overview");
  useEffect(() => {
    const change = () => setRoute(location.hash.slice(2) || "overview");
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return route;
}
