# Threat model

Assumption from the problem statement: *"Assume your server will be breached one day."*

## Assets

| Asset | Why it matters |
|---|---|
| Raw input records | direct PII of patients and relatives |
| Detected PII set, evidence index, cluster keys (in memory) | a ready-made identity map; more sensitive than any single input |
| `RAKSHA_SECRET` | inverts nothing alone, but lets anyone recompute pseudonyms and date shifts from guessed identities and link releases |
| The release (`sanitized/`, `report.json`, `records.jsonl`) | public by design; must not enable re-identification |
| Side channels (stdout, stderr, `logs/`, `TMPDIR`, `HOME`, filenames) | scanned by the evaluator, and real-world leak paths |

## Threat actors

1. **Release attacker** (the arena): holds a voter register, leaked contacts and known visit facts.
   Runs direct exposure, Sweeney linkage, profile aggregation, targeted attacks with global-shift
   recovery, pseudonym inversion and cross-release linkage (`organiser-toolkit/docs/ATTACKS.md`).
2. **Malicious or malformed input:** path tricks, symlinks, decompression- or recursion-bombs, huge files,
   invalid encodings, polyglot files.
3. **Host compromise after the run:** reads leftovers on disk (temp files, logs, caches).
4. **Insider or repository reader:** reads the public repo for secrets, answer keys and real data.

## Attack surfaces and mitigations

| Surface | Threat | Mitigation | Status |
|---|---|---|---|
| Input traversal | symlink to `/etc` or `~/.ssh` exported as a "sanitised" file | escaping symlinks quarantined, never parsed; symlinked dirs not traversed | ✅ P0 |
| Input size | memory exhaustion | `max_file_bytes` cap, streamed hashing | ✅ P0 |
| Deep / huge JSON | `RecursionError`, memory blow-up | linear pre-parse depth scan (limit 64), size (64 MiB) and node (2M) limits, no raised recursion limit; quarantine with stable codes | ✅ P1 |
| Extension spoofing | JSON behind `.csv` mangled as CSV | content-based detection: signatures, JSON-first, markup, delimiter sniffing | ✅ P1 |
| Wrong decoding | invalid UTF-8 decoded as cp1252 mojibake and exported | plausibility: UTF-8 fragments, mid-file BOMs, non-ASCII ratio; binary control chars | ✅ P1 |
| Output paths | write outside `sanitized/` | `safe_join` (no absolute paths, no `..`, symlinked-dir check); input/output overlap refused | ✅ P0 |
| Input mutation | penalised (−5) and destructive | read-only access pattern; overlap guard; test hashes the input before and after | ✅ P0 |
| Error messages | exception text echoes values | reasons are allowlisted codes or type names; CLI prints only the type name, never a traceback | ✅ P0 |
| Logs/stdout | PII or secret | counts-only output; `ReleaseSecret`, `Finding`, `InputFile` have redacting `repr` | ✅ P0 |
| Secret | written or logged; weak or missing key | env-only, unprintable, unpicklable; fail closed when missing; test scans every output byte for it | ✅ P0 |
| Temp files | PII left in `TMPDIR` | none written; if ever needed, AES-GCM with an ephemeral key, deleted in `finally` | ✅ P0 (by absence) |
| Filenames | `Discharge_Summary_<Name>_<UHID>.txt` | rename and record the mapping by hash | ⏳ P2 |
| Base64 payloads | PII exported inside raw attachments | declared and embedded payloads decoded, cleaned, re-encoded; binary or invalid payloads quarantine the file; 16 MiB decoded cap | ✅ P1 (baseline rules) |
| Hidden channels | keys, headers, metadata, FHIR narrative | channel-tagged IR (P1) plus channel-aware detection and propagation | ⏳ P2 |
| Pseudonym inversion (A6) | unkeyed hash of the UHID | HMAC-SHA256 keyed with the release secret; no identifier material in the code | ✅ helper; ⏳ applied P3 |
| Cross-release (A7) | stable pseudonyms or shifts across releases | every derivation keyed by the secret | ⏳ applied P3/P4 |
| Global shift recovery (A5) | one shift for everyone | per-patient keyed shift | ⏳ applied P4 |
| Quasi-identifier linkage (A2–A4) | age, village, PIN, dates, rare dx | bands, generalisation, k-anonymity on rare cells | ⏳ P4 |
| Repository | secrets or answer keys committed | `.gitignore` covers `.env*`, keys, the toolkit, `truth.json`, `registry.csv`, outputs; tests and fixtures synthetic | ✅ P0 |
| Frontend | raw records or secret exposed in the browser | the UI reads only release artefacts and aggregate metrics; no secret ever sent to the client | ⏳ P7 |

## Security assumptions

- The evaluator provides `RAKSHA_SECRET` via the environment and never via argv.
- The input copy is read-only and comes from the organisers (untrusted in content, not in location).
- Python's `json`, `csv` and `hashlib` are memory-safe for hostile input (no native parsers are added).
- The machine that runs the release is trusted *during* the run. Memory is not protected against a
  concurrent root attacker.

## Known limitations

- In-memory PII (decoded text, evidence index) is not zeroed. Python cannot guarantee wiping.
- The size cap is per file. A tree of many medium files could still approach the RSS budget (Phase 6
  scale test).
- A symlink that escapes the root is still *hashed* for the report (read-only), because SPEC requires every
  input file to be listed. Its content is never parsed or exported.
- Release privacy is measured only against the published attack suite. No finite synthetic attack
  proves anonymity.
