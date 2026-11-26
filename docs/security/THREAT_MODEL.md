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
| Input traversal | symlink to `/etc` or `~/.ssh` read, hashed or exported | escaping symlink targets are **never opened** (verified with an audit hook): the path gets an empty placeholder declared `suppressed` under a synthetic id; broken symlinks and FIFOs/devices reported unopened; every read resolves the real path, requires it inside the root, opens it `O_NOFOLLOW \| O_NONBLOCK` and checks `fstat` is a regular file; symlinked dirs not traversed | ✅ P0 / 2.1 |
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
| Filenames | `Discharge_Summary_<Name>_<UHID>.txt` | PII components renamed (`DS_NAME_MRN.txt`), collision-safe, mapping declared by input SHA-256 | ✅ P2 |
| Base64 payloads | PII exported inside raw attachments | declared and embedded payloads decoded, cleaned, re-encoded (standard and URL-safe alphabets; runs of 12+ chars when they hide an identifier-length number, 2.1); binary payloads *withheld* (JSON member removed, `[ATTACHMENT-WITHHELD]` in text) instead of quarantining the file, including short payloads under a binary content type; `hash`/`size` of any rewritten or withheld payload removed so they cannot fingerprint the original (2.1); invalid declared payloads quarantine; 16 MiB decoded cap | ✅ P1 / 2.1 |
| Encoded text | PII hidden from patterns by HTML entities, XHTML markup, %-escapes, non-Devanagari digits, homoglyph digits | decoded views with an exact offset map back (markup preserved); %-escapes also inside spaced text when there is evidence of an escape; `\uXXXX` escapes; every Unicode decimal digit folded (2.1). Not decoded: hex in plain text | ✅ 2.1 (partial) |
| Preserved fields | PII inside a "clinical", "doctor" or "relation" field skipped by detection | no semantic disables detection any more: preserved fields are guarded (validated IDs, cue-based names, confirmed values still removed; 2.1) | ✅ 2.1 |
| FHIR ids | hospital IDs embedded in `id` / `fullUrl` / `reference` | identifying id segments rewritten to `rid-<entry>` together with every reference (2.1) | ✅ 2.1 |
| Hidden channels | keys, headers, metadata, FHIR narrative, filenames | channel-aware detection, loose-channel rules, cross-channel propagation, path renaming declared by hash | ✅ P2 |
| Value index | a run-wide map of confirmed PII is itself a breach target | memory only; refuses pickling; `repr` shows sizes only; deleted at the end of the run; never logged; complaint words, care-of names, doctor-protected names and non-person-shaped values never seeded (2.1) | ✅ P2 / 2.1 |
| Memo caches | `lru_cache`s of normalisation, transliteration, label classification and Phase 3 identity normalisation keep input fragments (names, villages, hospital names) in process memory after a run | central registry (`detection/caches.py`), cleared in a `finally` when every run ends (2.1 / P3, tested) | ✅ P2.1 / P3 |
| Identity evidence & clusters | run-local `RecordEvidence`, `ClusterProfile` and canonical cluster keys hold cross-file identity graphs in memory | memory-only; redacting `repr`; refuse pickling (`__reduce__`); discarded immediately after pseudonym assignment; never logged or persisted | ✅ P3 |
| Findings / stats | detection/linking metadata leaks values; counts overstate work | `Finding` stores offsets only (no text); `logs/detection_summary.json` and `report.json` hold aggregate counts only (tested); only transformations that changed the text are counted (2.1) | ✅ P2 / 2.1 / P3 |
| Pseudonym inversion (A6) | unkeyed hash of the UHID or reversible pseudonym | domain-separated versioned `HMAC-SHA256(RAKSHA_SECRET, "psn\|v1\|" + canonical_key)` with deterministic collision counter; no identifier material in `PSN-XXXXXX`; pre-exit format & consistency check | ✅ P3 |
| Cross-release (A7) | stable pseudonyms or shifts across releases | pseudonyms keyed strictly by `RAKSHA_SECRET` (verified: different secrets yield disjoint pseudonyms and distinct release output); date shifts pending Phase 4 | ✅ P3 (psn) / ⏳ P4 (dates) |
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
- A symlink that escapes the root is never opened, so its SHA-256 cannot be reported. It is declared under a
  synthetic id with an empty placeholder at its path, which `validate_output.py` accepts (one WARN). If the
  link's own filename holds PII the placeholder is renamed and the validator reports one undeclared input:
  privacy and no-read were preferred to that error (PHASE2_REMEDIATION.md §7, S1). The official validator
  itself reads link targets (it blocks on a FIFO and crashes on a dangling link).
- Hard links to files outside the root look like regular files and are read. Directory components swapped
  for symlinks during a run are not defended against (the final component is, via `O_NOFOLLOW`).
- Release privacy is measured only against the published attack suite. No finite synthetic attack
  proves anonymity.
