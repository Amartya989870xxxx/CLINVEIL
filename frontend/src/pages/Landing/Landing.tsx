import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router";

import { useTheme, type ThemePreference } from "../../app/providers/ThemeProvider";
import { LinkButton } from "../../components/common/Button";
import { Icon } from "../../components/common/Icon";
import { Segmented } from "../../components/common/Segmented";
import { BrandMark } from "../../components/layout/BrandMark";
import { HomeLink } from "../../components/layout/HomeLink";
import { RedactionReel } from "../../components/motion/RedactionReel";
import { RevealWords } from "../../components/motion/RevealWords";
import { ScrambleText } from "../../components/motion/ScrambleText";
import { AFTER, BEFORE } from "../../fixtures/exampleRecord";
import s from "./Landing.module.css";

// Four lines of the recorded engine run, picked by label so the excerpt can never drift from the real output.
const PICK = ["Patient Name:", "W/o ", "Consultant:", " 1. Tab"];
const lines = (text: string) => PICK.map((p) => text.split("\n").find((l) => l.startsWith(p)) ?? "").join("\n");

const SECTIONS = [
  { id: "how", label: "How it works" },
  { id: "example", label: "An example" },
  { id: "limits", label: "Limitations" },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

const reducedMotion = () => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** In-page links that glide to their section and an underline that slides to the section being read. */
function SectionNav() {
  const [active, setActive] = useState<SectionId | null>(null);
  const [bar, setBar] = useState<{ x: number; w: number } | null>(null);
  const links = useRef<Partial<Record<SectionId, HTMLAnchorElement | null>>>({});

  // a shared link such as /#limits: the section only exists after render, so scroll to it now
  useEffect(() => {
    const id = window.location.hash.slice(1);
    const match = SECTIONS.find((x) => x.id === id);
    if (match) {
      document.getElementById(match.id)?.scrollIntoView({ block: "start", behavior: "instant" });
      setActive(match.id);
    }
  }, []);

  // which section is crossing the upper-middle of the viewport
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id as SectionId);
      },
      { rootMargin: "-35% 0px -60% 0px" },
    );
    for (const { id } of SECTIONS) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
    // above the first section (hero), nothing is active
    const onScroll = () => {
      const first = document.getElementById(SECTIONS[0].id);
      if (first && first.getBoundingClientRect().top > window.innerHeight * 0.4) setActive(null);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const a = active ? links.current[active] : null;
    // the <li>'s offsetLeft is relative to the positioned <nav>, which also holds the indicator
    if (a && a.offsetWidth) setBar({ x: a.parentElement?.offsetLeft ?? 0, w: a.offsetWidth });
  }, [active]);

  function go(e: MouseEvent<HTMLAnchorElement>, id: SectionId) {
    const target = document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    history.replaceState(null, "", `#${id}`);
    // move focus to the section heading so keyboard and screen-reader users land there too
    target.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
    setActive(id);
  }

  return (
    <nav aria-label="On this page" className={s.nav}>
      <ul className={s.links}>
        {SECTIONS.map(({ id, label }) => (
          <li key={id}>
            <a
              ref={(el) => {
                links.current[id] = el;
              }}
              href={`#${id}`}
              aria-current={active === id ? "location" : undefined}
              onClick={(e) => go(e, id)}
            >
              {label}
            </a>
          </li>
        ))}
      </ul>
      <span
        className={s.indicator}
        aria-hidden="true"
        style={bar ? { width: bar.w, transform: `translateX(${bar.x}px)`, opacity: active ? 1 : 0 } : undefined}
      />
    </nav>
  );
}

const IN = [
  { tag: "CSV", text: "Registration desk exports" },
  { tag: "JSON", text: "OPD visits and lab reports" },
  { tag: "FHIR", text: "FHIR R4 patient bundles" },
  { tag: "TXT", text: "Discharge summaries, Hindi prescriptions, Hinglish notes" },
];
const OUT = [
  { tag: "SAME", text: "Every file, same format and structure, details replaced" },
  { tag: "JSON", text: "report.json: counts and every file's status" },
  { tag: "JSONL", text: "records.jsonl: the record list" },
];

/** What goes in and what comes out: the formats and files the engine actually reads and writes. */
function TagRow({ tag, text, i }: { tag: string; text: string; i: number }) {
  const [n, setN] = useState(0);
  return (
    <li style={{ ["--i" as string]: i }} onMouseEnter={() => setN((x) => x + 1)}>
      <span className={s.tag}>
        <ScrambleText text={tag} trigger={n} />
      </span>
      {text}
    </li>
  );
}

function Schematic() {
  return (
    <figure className={s.schematic} aria-labelledby="schematic-caption">
      <div className={s.schemBlock}>
        <span className={s.schemLabel}>Hospital exports</span>
        <ul>
          {IN.map((x, i) => (
            <TagRow key={x.tag} tag={x.tag} text={x.text} i={i} />
          ))}
        </ul>
      </div>
      <div className={s.schemCore}>
        <span className={s.schemLine} aria-hidden="true">
          <span className={s.packet} />
        </span>
        <HomeLink className={s.schemEngine}>
          <BrandMark size={18} />
          CLINVEIL
          <span className={s.schemSteps} aria-hidden="true">
            find · replace · check
          </span>
        </HomeLink>
        <span className={s.schemLine} aria-hidden="true" />
      </div>
      <div className={`${s.schemBlock} ${s.schemOut}`}>
        <span className={s.schemLabel}>Research release</span>
        <ul>
          {OUT.map((x, i) => (
            <TagRow key={x.text} tag={x.tag} text={x.text} i={i + IN.length + 1} />
          ))}
        </ul>
        <p className={s.schemAside}>
          <Icon name="dash" size={14} /> Set aside, never copied: PDF, images, XML and broken files.
        </p>
      </div>
      <figcaption id="schematic-caption" className="visually-hidden">
        CLINVEIL reads CSV, JSON, FHIR R4 and text exports and writes a release with the same files in the same
        formats, plus report.json and records.jsonl. Files it cannot check are set aside and never copied.
      </figcaption>
    </figure>
  );
}

/** Public landing page. Deliberately shows no run data, statuses or controls: that lives in the workspace. */
/** Fades sections in as they enter the viewport; marks the page so CSS only hides content while this runs. */
function useReveal(root: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const page = root.current;
    if (!page || typeof IntersectionObserver === "undefined") return;
    const items = Array.from(page.querySelectorAll<HTMLElement>(`.${s.reveal}`));
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.setAttribute("data-shown", "");
          io.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    // anything already on screen (or scrolled past, e.g. a #limits deep link) is shown at once
    for (const el of items) {
      if (el.getBoundingClientRect().top < window.innerHeight) el.setAttribute("data-shown", "");
      else io.observe(el);
    }
    page.setAttribute("data-reveal", "");
    return () => io.disconnect();
  }, [root]);
}

/** Thin accent line under the bar showing how far down the page you are. */
function ScrollProgress() {
  const bar = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        bar.current?.style.setProperty("transform", `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`);
      });
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  return <span ref={bar} className={s.progress} aria-hidden="true" />;
}

function useScrolled(): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return scrolled;
}

export function Landing() {
  const { preference, setPreference } = useTheme();
  const pageRef = useRef<HTMLDivElement>(null);
  useReveal(pageRef);
  const scrolled = useScrolled();
  useEffect(() => {
    document.title = "CLINVEIL: privacy-protected medical data for research";
    return () => {
      document.title = "CLINVEIL";
    };
  }, []);

  return (
    <div ref={pageRef} className={s.page}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className={s.bar} data-scrolled={scrolled ? "" : undefined}>
        <ScrollProgress />
        <div className={`${s.wrap} ${s.barInner}`}>
          <HomeLink className={s.brand}>
            <BrandMark size={26} />
            <span className={s.word}>CLINVEIL</span>
          </HomeLink>
          <SectionNav />
          <div className={s.barRight}>
            <span className={s.themeCtl}>
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
            </span>
            <LinkButton to="/overview" variant="secondary">
              Open workspace
            </LinkButton>
          </div>
        </div>
      </header>

      <main id="main">
        <section className={s.hero} aria-labelledby="landing-title">
          <div className={`${s.wrap} ${s.heroGrid}`}>
          <div className={s.heroInner}>
          <span className="eyebrow">Privacy infrastructure for trusted medical data sharing</span>
          <h1 id="landing-title" className={s.title} tabIndex={-1}>
            <RevealWords text="Protecting patient identities." start={80} />{" "}
            <em>
              <RevealWords text="Preserving medical value." start={330} />
            </em>
          </h1>
          <p className={s.lead}>
            CLINVEIL prepares hospital exports for responsible research. It finds and removes the details that identify
            a patient, wherever they hide, and leaves the clinical record exactly as it was written.
          </p>
          <div className={s.actions}>
            <LinkButton to="/overview" variant="primary" icon="arrowRight">
              Open the workspace
            </LinkButton>
            <LinkButton to="/overview?path=judge" variant="secondary">
              Follow the five-minute demo
            </LinkButton>
          </div>
          <ul className={s.facts} aria-label="Operating constraints">
            <li><Icon name="lock" size={15} /> Runs fully offline</li>
            <li><Icon name="monitor" size={15} /> CPU only, 4 GB</li>
            <li><Icon name="dash" size={15} /> No language models</li>
            <li><Icon name="file" size={15} /> Demonstrated on synthetic data</li>
          </ul>
          </div>
          <RedactionReel />
          </div>
        </section>

        <section className={s.section} aria-labelledby="problem">
          <div className={`${s.wrap} ${s.split} ${s.reveal}`}>
            <h2 id="problem" className={s.h2}>
              The same patient, in five systems and three scripts.
            </h2>
            <div className={s.body}>
              <p>
                An Indian hospital's records come out of registration desks, OPD software, laboratory systems, FHIR
                servers and typed discharge summaries, in English, Hindi and Hinglish. Names and numbers turn up in
                notes, file names, column headers and attachments, not just in the fields labelled for them.
              </p>
              <p>
                Researchers need the diagnoses, medicines, vitals and results. They must not be able to tell
                <strong> who</strong> the patient is.
              </p>
            </div>
          </div>
        </section>

        <section id="how" className={s.section} aria-labelledby="how-title">
          <div className={`${s.wrap} ${s.reveal} ${s.howGrid}`}>
            <div>
            <h2 id="how-title" className={s.h2} tabIndex={-1} style={{ marginBottom: "var(--s-8)" }}>
              How it works
            </h2>
            <ol className={s.steps}>
              <li>
                <span className={s.num}>01</span>
                <span className={s.stepTitle}>Find</span>
                <p className={s.stepText}>
                  Patient and family names, hospital and government ID numbers, phone numbers and addresses, in text,
                  tables, keys, file names and attachments. A detail confirmed in one file is looked for again in
                  every other file.
                </p>
              </li>
              <li>
                <span className={s.num}>02</span>
                <span className={s.stepTitle}>Replace in place</span>
                <p className={s.stepText}>
                  Each detail becomes a placeholder such as [NAME] or [PHONE]. Formats, columns and structure stay as
                  they were, and medical vocabulary is protected from being redacted by mistake.
                </p>
              </li>
              <li>
                <span className={s.num}>03</span>
                <span className={s.stepTitle}>Check before release</span>
                <p className={s.stepText}>
                  Files that cannot be checked safely are set aside and listed, never copied. The release is validated
                  before the run reports success.
                </p>
              </li>
            </ol>
            </div>
            <Schematic />
          </div>
        </section>

        <section id="example" className={s.section} aria-labelledby="example-title">
          <div className={`${s.wrap} ${s.reveal}`}>
            <div className={s.split} style={{ marginBottom: "var(--s-8)" }}>
              <h2 id="example-title" className={s.h2} tabIndex={-1}>
                The doctor stays. The relative goes.
              </h2>
              <p className={s.body}>
                A doctor and the patient's husband share a first name. Only one of them is a clinician whose name belongs
                in the record, and the dose of a common fever medicine must survive untouched.
              </p>
            </div>
            <div className={s.excerpt}>
              <div className={s.col}>
                <div className={s.colHead}>Hospital export</div>
                <pre className={s.lines}>{lines(BEFORE)}</pre>
              </div>
              <div className={s.col}>
                <div className={s.colHead}>CLINVEIL release</div>
                <pre className={s.lines}>{lines(AFTER)}</pre>
              </div>
            </div>
            <div className={s.caption}>
              <span>An invented synthetic record. The release side is unedited output of the real engine.</span>
              <Link to="/preview">See the whole record</Link>
            </div>
          </div>
        </section>

        <section id="limits" className={s.section} aria-labelledby="limits-title">
          <div className={`${s.wrap} ${s.split} ${s.reveal}`}>
            <h2 id="limits-title" className={s.h2} tabIndex={-1}>
              A prototype, honestly labelled.
            </h2>
            <div className={s.body}>
              <p>
                CLINVEIL is a prototype, not a certified medical system. Today it removes direct identifiers.
                Connecting records of the same patient, age bands, and generalising places and dates are
                <strong> not built yet</strong>, so a release can still contain exact ages, villages and visit dates.
              </p>
              <p>
                <Link to="/about">Read the limitations</Link>
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className={s.foot}>
        <div className={`${s.wrap} ${s.footGrid}`}>
          <div className={s.footBrand}>
            <HomeLink className={s.brand}>
              <BrandMark size={22} />
              <span className={s.word}>CLINVEIL</span>
            </HomeLink>
            <p>Privacy infrastructure for trusted medical data sharing.</p>
          </div>
          <nav aria-label="Workspace" className={s.footCol}>
            <span className={s.footHead}>Workspace</span>
            <Link to="/overview">Overview</Link>
            <Link to="/process">Process a dataset</Link>
            <Link to="/overview?path=judge">Five-minute demo</Link>
          </nav>
          <nav aria-label="Evidence" className={s.footCol}>
            <span className={s.footHead}>Evidence</span>
            <Link to="/privacy">Privacy and quality</Link>
            <Link to="/preview">Data preview</Link>
            <Link to="/architecture">Architecture</Link>
          </nav>
          <nav aria-label="Project" className={s.footCol}>
            <span className={s.footHead}>Project</span>
            <Link to="/about">About and limitations</Link>
            <a href="#how">How it works</a>
          </nav>
        </div>
        <div className={s.wrap}>
          <div className={s.footBase}>
            <span>
              <HomeLink className={s.baseHome}>CLINVEIL</HomeLink> interface {__APP_VERSION__}
            </span>
            <span>Synthetic data only · no analytics or third-party requests · fonts under the SIL Open Font License</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
