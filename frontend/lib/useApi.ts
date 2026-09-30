"use client";

// Lightweight async-state helper: loading / success / error with stale-response
// protection (a newer call always wins). No global state library is needed.

import { useCallback, useRef, useState } from "react";

export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface UseAsyncResult<T> {
  data: T | null;
  error: Error | null;
  status: AsyncStatus;
  exec: (fn: () => Promise<T>) => Promise<T | null>;
  reset: () => void;
}

export function useAsync<T>(): UseAsyncResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [status, setStatus] = useState<AsyncStatus>("idle");
  const seq = useRef(0);

  const exec = useCallback(async (fn: () => Promise<T>) => {
    const id = ++seq.current;
    setStatus("loading");
    setError(null);
    try {
      const result = await fn();
      if (id === seq.current) {
        setData(result);
        setStatus("success");
      }
      return result;
    } catch (err) {
      if (id === seq.current) {
        setError(err instanceof Error ? err : new Error(String(err)));
        setStatus("error");
      }
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    seq.current += 1;
    setData(null);
    setError(null);
    setStatus("idle");
  }, []);

  return { data, error, status, exec, reset };
}