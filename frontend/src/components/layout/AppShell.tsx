import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useDataMode } from "../../app/providers/DataModeProvider";
import { useTheme, type ThemePreference } from "../../app/providers/ThemeProvider";
import { ROUTES } from "../../app/routes";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useResource } from "../../hooks/useResource";
import { Icon } from "../common/Icon";
import { Segmented } from "../common/Segmented";
import { StatusTag } from "../common/StatusTag";
import { BrandMark } from "./BrandMark";
import { HomeLink } from "./HomeLink";
import s from "./layout.module.css";

function BackendStatus() {
  const { source, mode } = useDataMode();
  const health = useResource(() => source.health(), [source]);
  if (mode === "demo") return null;
  if (health.status === "loading") return <span className="meta">Checking backend…</span>;
  if (health.status === "ready") return <StatusTag state="complete" label="Backend connected" />;
  return <StatusTag state="needs_attention" label="Backend not reachable" />;
}

export function AppShell() {
  const { preference, setPreference } = useTheme();
  const { mode, setMode } = useDataMode();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);

  // close the mobile menu and move focus to the page heading on navigation
  useEffect(() => {
    setOpen(false);
    if (first.current) {
      first.current = false;
      return;
    }
    mainRef.current?.querySelector<HTMLElement>("h1")?.focus({ preventScroll: true });
  }, [loc.pathname]);

  // mobile menu: Escape or a tap outside closes it; Escape returns focus to the menu button
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      menuBtnRef.current?.focus();
    };
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Node;
      if (navRef.current?.contains(t) || menuBtnRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  // one highlight that slides to the current page's link (falls back to per-link styling until measured)
  const navRef = useRef<HTMLElement>(null);
  const [pill, setPill] = useState<{ y: number; h: number } | null>(null);
  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const measure = () => {
      const a = nav.querySelector<HTMLElement>('a[aria-current="page"]');
      setPill(a && a.offsetHeight ? { y: a.offsetTop, h: a.offsetHeight } : null);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(nav);
    return () => ro.disconnect();
  }, [loc.pathname, open]);

  const groups = ["Workflow", "Evidence"] as const;
  const route = ROUTES.find((r) => r.path === loc.pathname);
  useDocumentTitle(route ? route.label : "Page not found");

  return (
    <div className={s.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <nav
        id="site-nav"
        ref={navRef}
        className={`${s.sidebar} ${open ? s.sidebarOpen : ""}`}
        aria-label="Main"
        data-pill={pill ? "" : undefined}
      >
        {pill && <span className={s.navPill} aria-hidden="true" style={{ height: pill.h, transform: `translateY(${pill.y}px)` }} />}
        <HomeLink className={`${s.brand} ${s.sideBrand}`}>
          <BrandMark />
          <span className={s.wordmark}>
            CLINVEIL
            <span className={s.tagline}>Research data protection</span>
          </span>
        </HomeLink>
        {groups.map((g) => (
          <div key={g} className={s.navGroup}>
            <div className={`eyebrow ${s.navTitle}`}>{g}</div>
            {ROUTES.filter((r) => r.group === g).map((r) => (
              <NavLink key={r.path} to={r.path} end className={s.navLink}>
                <Icon name={r.icon} />
                {r.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className={s.main}>
        <header className={s.topbar}>
          <div className={s.topLeft}>
            <button
              ref={menuBtnRef}
              type="button"
              className={s.menuBtn}
              aria-expanded={open}
              aria-controls="site-nav"
              onClick={() => setOpen((o) => !o)}
            >
              <Icon name={open ? "cross" : "overview"} />
              <span className="visually-hidden">{open ? "Close menu" : "Open menu"}</span>
            </button>
            <HomeLink className={`${s.brand} ${s.mobileBrand}`}>
              <BrandMark size={24} />
              <span className={s.wordmark}>CLINVEIL</span>
            </HomeLink>
            <nav aria-label="Breadcrumb" className={s.crumbs}>
              <ol>
                <li>
                  <Link to="/overview">Workspace</Link>
                </li>
                {route && route.path !== "/overview" && (
                  <li>
                    <span className={s.crumbGroup}>{route.group}</span>
                  </li>
                )}
                <li>
                  <span aria-current="page">{route ? route.label : "Page not found"}</span>
                </li>
              </ol>
            </nav>
            <BackendStatus />
          </div>
          <div className={s.topRight}>
            <div className={s.ctrl}>
              <span className={s.ctrlLabel} aria-hidden="true">
                Data
              </span>
              <Segmented
                legend="Data source"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "demo", label: "Example data" },
                  { value: "backend", label: "Local backend" },
                ]}
              />
            </div>
            <div className={s.ctrl}>
              <span className={s.ctrlLabel} aria-hidden="true">
                Theme
              </span>
              <Segmented<ThemePreference>
                legend="Colour theme"
                value={preference}
                onChange={setPreference}
                options={[
                  { value: "system", label: "Match system", icon: "monitor", hideLabel: true },
                  { value: "light", label: "Light", icon: "sun", hideLabel: true },
                  { value: "dark", label: "Dark", icon: "moon", hideLabel: true },
                ]}
              />
            </div>
          </div>
        </header>
        <main id="main" ref={mainRef} className={s.content} tabIndex={-1}>
          <p className="print-only meta">
            Printed from the CLINVEIL interface {__APP_VERSION__} on{" "}
            {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}. Synthetic data only.
          </p>
          <div key={loc.pathname} className="page-enter">
            <Outlet />
          </div>
        </main>
        <footer className={s.appFoot}>
          <span>
            <HomeLink className={s.footHome}>CLINVEIL</HomeLink> interface {__APP_VERSION__}
          </span>
          <span>Synthetic data only · runs offline · no analytics or third-party requests</span>
          <Link to="/about">About and limitations</Link>
        </footer>
      </div>
    </div>
  );
}
