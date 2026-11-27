// Fails if the production bundle contains anything that must never ship to a browser.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const DIST = new URL("../dist/", import.meta.url).pathname;
const RULES = [
  // Allowed inert identifiers: XML namespace URIs (www.w3.org/...) used by react-dom for SVG/MathML, and React's
  // error-decoder link and React Router's docs and polyfill links embedded in warning text. Neither is ever fetched (CSP connect-src is localhost only).
  { name: "external URL", re: /https?:\/\/(?!127\.0\.0\.1|localhost|www\.w3\.org\/|reactjs\.org\/docs\/error-decoder|react\.dev\/errors|reactrouter\.com\/|github\.com\/ungap\/url-search-params)[a-z0-9.-]+\.[a-z]{2,}/gi },
  { name: "answer key / attacker reference", re: /dev\/(truth|attacker)|truth\.json|known_facts|registry\.csv|ground_truth/gi },
  { name: "secret-like assignment", re: /RAKSHA_SECRET\s*[=:]\s*["']?[A-Za-z0-9+/_-]{8,}/g },
  { name: "Aadhaar-like 12-digit number", re: /(?<![\w.])[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?![\w.])/g },
  { name: "Indian mobile-like number", re: /(?<![\w.])(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w.])/g },
];
// The single synthetic Data Preview record is allowed to contain its invented values; nothing else is.
const ALLOW = new Set(["9876512034", "98765 12034", "+91 98765 12034"]);

const files = [];
(function walk(d) {
  for (const f of readdirSync(d)) {
    const p = join(d, f);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|css|html|json|txt|svg)$/.test(f)) files.push(p);
  }
})(DIST);

let bad = 0;
for (const f of files) {
  const text = readFileSync(f, "utf8");
  for (const r of RULES) {
    for (const m of text.matchAll(r.re)) {
      if (ALLOW.has(m[0].trim())) continue;
      bad++;
      console.error(`${r.name}: ${f.replace(DIST, "dist/")}: ${m[0].slice(0, 60)}`);
    }
  }
}
console.log(`scanned ${files.length} files, ${bad} findings`);
process.exit(bad ? 1 : 0);
