import { useEffect, useState } from "react";

import { SAFE_MESSAGES, SafeError } from "../services/api/client";

export type Resource<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "empty" }
  | { status: "error"; message: string };

/**
 * Runs an async loader and exposes honest loading / empty / error states.
 * `refresh` re-runs the loader without going back to "loading" (used to poll a live run without flicker);
 * a change in `deps` is a different resource and starts from "loading".
 */
export function useResource<T>(load: () => Promise<T | null>, deps: unknown[], refresh: unknown = 0): Resource<T> {
  const [state, setState] = useState<Resource<T>>({ status: "loading" });
  const [lastDeps, setLastDeps] = useState(deps);
  const depsChanged = deps.length !== lastDeps.length || deps.some((d, i) => !Object.is(d, lastDeps[i]));
  if (depsChanged) {
    setLastDeps(deps);
    setState({ status: "loading" });
  }
  useEffect(() => {
    let alive = true;
    load().then(
      (data) => alive && setState(data === null ? { status: "empty" } : { status: "ready", data }),
      (err: unknown) =>
        alive &&
        setState({ status: "error", message: err instanceof SafeError ? err.message : SAFE_MESSAGES.server_error }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refresh]);
  return state;
}
