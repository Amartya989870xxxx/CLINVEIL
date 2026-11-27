import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { backendSource, demoSource, type DataMode, type DataSource } from "../../services/dataSource";

interface ModeCtx {
  mode: DataMode;
  source: DataSource;
  setMode: (m: DataMode) => void;
}

const KEY = "clinveil.mode";
const Ctx = createContext<ModeCtx | null>(null);

function readMode(): DataMode {
  try {
    return localStorage.getItem(KEY) === "backend" ? "backend" : "demo";
  } catch {
    return "demo";
  }
}

export function DataModeProvider({ children, initial }: { children: ReactNode; initial?: DataMode }) {
  const [mode, setModeState] = useState<DataMode>(initial ?? readMode);
  const setMode = useCallback((m: DataMode) => {
    setModeState(m);
    try {
      localStorage.setItem(KEY, m);
    } catch {
      /* ignore */
    }
  }, []);
  const value = useMemo(
    () => ({ mode, source: mode === "demo" ? demoSource : backendSource, setMode }),
    [mode, setMode],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDataMode(): ModeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDataMode outside DataModeProvider");
  return v;
}
