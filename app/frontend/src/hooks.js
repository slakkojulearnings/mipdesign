import { useCallback, useEffect, useRef, useState } from "react";

// Loads data, exposes {data, err, loading, reload}, and auto-reloads on a rescan.
export function useData(loader, deps = []) {
  const [state, setState] = useState({ data: null, err: null, loading: true });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    loaderRef.current()
      .then((d) => setState({ data: d, err: null, loading: false }))
      .catch((e) => setState({ data: null, err: String(e), loading: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const h = () => load();
    window.addEventListener("mip-rescan", h);
    return () => window.removeEventListener("mip-rescan", h);
  }, [load]);

  return { ...state, reload: load };
}
