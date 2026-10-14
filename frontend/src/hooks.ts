import { useCallback, useEffect, useRef, useState } from "react";

export function usePoll<T>(
  load: (signal: AbortSignal) => Promise<T>,
  interval = 10000,
  key = "",
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [revision, setRevision] = useState(0);
  const ref = useRef(load);
  ref.current = load;
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    setData(undefined);
    setError("");
    setLoading(true);
  }, [key]);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;
    async function run() {
      if (document.hidden) {
        if (interval > 0) timer = setTimeout(run, interval);
        return;
      }
      request?.abort();
      request = new AbortController();
      const current = request;
      setLoading(true);
      try {
        const result = await ref.current(current.signal);
        if (!disposed && current === request) {
          setData(result);
          setError("");
          setUpdatedAt(Date.now());
        }
      } catch (err) {
        if (!disposed && current === request && !current.signal.aborted)
          setError(err instanceof Error ? err.message : "Could not load data.");
      } finally {
        if (!disposed && current === request) {
          setLoading(false);
          if (interval > 0) timer = setTimeout(run, interval);
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
  }, [interval, revision, key]);
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
