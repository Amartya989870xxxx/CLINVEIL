import { useEffect, useRef } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router";

import { AppShell } from "../components/layout/AppShell";
import { About } from "../pages/About/About";
import { Architecture } from "../pages/Architecture/Architecture";
import { Landing } from "../pages/Landing/Landing";
import { DataPreview } from "../pages/DataPreview/DataPreview";
import { Overview } from "../pages/Overview/Overview";
import { NotFound } from "../pages/NotFound/NotFound";
import { PrivacyQuality } from "../pages/PrivacyQuality/PrivacyQuality";
import { ProcessDataset } from "../pages/ProcessDataset/ProcessDataset";
import { ProcessingRun } from "../pages/ProcessingRun/ProcessingRun";
import { Results } from "../pages/Results/Results";
import { DataModeProvider } from "./providers/DataModeProvider";
import { ThemeProvider } from "./providers/ThemeProvider";

/** Every page change starts at the top, across both layouts; in-page #section links are left to the page. */
function ScrollReset() {
  const { pathname, hash } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (!hash) window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname, hash]);
  return null;
}

export function App() {
  return (
    <ThemeProvider>
      <DataModeProvider>
        <BrowserRouter>
          <ScrollReset />
          <Routes>
            <Route index element={<Landing />} />
            <Route element={<AppShell />}>
              <Route path="overview" element={<Overview />} />
              <Route path="process" element={<ProcessDataset />} />
              <Route path="run" element={<ProcessingRun />} />
              <Route path="results" element={<Results />} />
              <Route path="privacy" element={<PrivacyQuality />} />
              <Route path="preview" element={<DataPreview />} />
              <Route path="architecture" element={<Architecture />} />
              <Route path="about" element={<About />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </DataModeProvider>
    </ThemeProvider>
  );
}
