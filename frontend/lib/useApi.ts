"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export type ApiState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: T };

/** GET `path` and track loading / error / ready. `reload()` fetches again. */
export function useApi<T>(path: string): ApiState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    api
      .get<T>(path)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch((err) => {
        if (cancelled) return;
        const error = err instanceof ApiError ? err : new ApiError("unknown", "Something went wrong loading this page.");
        setState({ status: "error", error });
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
