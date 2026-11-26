# System architecture

Authoritative contract: `organiser-toolkit/docs/SPEC.md`. This document describes how CLINVEIL meets
it. Where it says "Phase N", the component is designed but not implemented yet.

## 1. Component diagram

```
                                 ┌───────────────────────┐
                                 │  raksha.toml (root)   │  run = python main.py --input {input} --output {output}
                                 └──────────┬────────────┘
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ main.py (shim) ─► clinveil.cli  ── args, ReleaseSecret.from_env(), Policy, exit codes       │
│                        │                                                                   │
│                        ▼                                                                   │
│  clinveil.pipeline ───────────────────────────────────────────────────────────────────┐    │
│   PASS 1 (Phase 3: evidence)                    PASS 2 (transform + export)            │    │
│   ┌───────────┐  ┌──────────┐  ┌────────────┐   ┌──────────┐  ┌────────────┐  ┌───────┐│    │
│   │ ingestion │─►│ parsing  │─►│ detection  │──►│ linking  │─►│ privacy    │─►│ sanit-││    │
│   │ discover  │  │ CSV/TSV  │  │ Findings   │   │ evidence │  │ pseudonym  │  │ ization│    │
│   │ guard     │  │ JSON     │  │ (typed,    │   │ blocking │  │ date shift │  │ per-   ││    │
│   │ decode    │  │ FHIR     │  │  read-only)│   │ scoring  │  │ generalise │  │ format ││    │
│   │ sniff(P1) │  │ text     │  │            │   │ clusters │  │ suppress   │  │        ││    │
│   └───────────┘  └──────────┘  └────────────┘   └──────────┘  └────────────┘  └───┬───┘│    │
│                                                                                   ▼    │    │
│                                                  ┌──────────┐   ┌─────────────────────┐│    │
│                                                  │validation│◄──│ export: sanitized/, ││    │
│                                                  │ pre-exit │   │ report.json,        ││    │
│                                                  │ check    │   │ records.jsonl       ││    │
│                                                  └──────────┘   └─────────────────────┘│    │
│   cross-cutting: security (secret, paths, reason codes) · models · utils               │    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
        optional, never on the evaluator path:  demo API (Phase 7) ◄── frontend dashboard
```

## 2. Processing pipeline

| # | Step | Today (Phase 1) | Target |
|---|---|---|---|
| 1 | **Discover** | `sorted(rglob)`, symlink-escape flag, size | stable order independent of locale |
| 2 | **Guard** | escaping symlink → quarantine; `> max_file_bytes` → quarantine (streamed hash); JSON size, depth (64) and node limits | record-count limits for huge CSVs |
| 3 | **Detect + decode** | signatures (PDF/images/archives/executables) → decode (BOM-UTF-8, UTF-16 with or without BOM, UTF-8, cp1252 with mojibake/binary plausibility) → JSON-first if `{`/`[` → XML markup → delimiter sniffing for `.csv`/`.tsv` → text; extension is supporting evidence | XML/CDA parsing |
| 4 | **Parse** | common IR `Document{source, records[], fields[], native, fhir}`; each `Field` has address, path, record, channel, kind, label, FHIR context, base64 segments | |
| 5 | **Detect** | Phase 2 engine: semantics → structured/free-text detectors → loose-channel rules → value-index and document-local propagation → clinical protection → resolution; typed offset-only findings | layered detectors emit `Finding`s: column semantics, patterns with dose guards, labels and context, gazetteers and transliteration, propagation of known PII values, preserve rules |
| 6 | **Link** | Phase 3 (`clinveil.linking`): two-pass IR evidence extraction with identifier **ownership** (patient / relative / ambiguous, 3.1), hospital-scoped and **typed** MRNs, reliable-hospital cross-hospital guard, hard conflict vetoes (incl. relative-ID owner, same-issuer MRN rule), complete-linkage vetoes for weak merges, bounded blocking with abstention, 3-stage conservative clustering, `null` when ambiguous | complete (Phase 3 + 3.1 remediation) |
| 7 | **Privatise** | Phase 3: domain-separated HMAC-SHA256 (`psn\|v1\|...`) pseudonym written inside each linked record (CSV/TSV/JSON/FHIR/text) & `records.jsonl`; date shifting & generalisation in Phase 4 | + per-patient date shift; 5-year age bands; village → tehsil/district; PIN → 3-digit prefix; k-anonymity pass on rare cells |
| 8 | **Sanitise** | IR field transformer (Phase 2.1 redactions + Phase 3 schema-preserving pseudonym placement) + renderers; base64 payloads decoded, cleaned, re-encoded; binary attachments withheld | + Phase 4 generalisation transforms |
| 9 | **Export** | `sanitized/`, `report.json` (honest counts + `entities`), `records.jsonl` (linked pseudonyms), `logs/detection_summary.json` (safe aggregate detection + linking counts) | + `out` locators after suppression (Phase 4) |
| 10 | **Self-check** | report completeness, outputs exist, pseudonym format & **per-record** placement (each linked record holds its own pseudonym, none holds another's; 3.1), `records_linked` verified | + PII re-scan of side channels with the release's own known-PII set |

### The common IR (Phase 1)

```
Document
├── source   SourceFile(rel, sha256, size, ext, format, encoding, delimiter, extension_mismatch)
├── records  ["row:0", …] | ["/visits/0", …] | ["doc"]          ← exactly what records.jsonl reports
├── fields   Field(address, path, record, channel, kind, value, label, fhir, segments, parent)
│              address  "@header/2" · "row:3/1" · "/visits/0/doctor" · "/a/b#key" · "doc" · "@filename/0" · "<parent>#b64/0"
│              channel  content · header · key · metadata · base64 · filename
│              kind     header · cell · json_key · json_string/number/bool/null · text · filename · base64_text
├── native   parsed rows / JSON tree / text (renderers rebuild output from this)
└── fhir     FhirIndex(entries[fullUrl, type, id], references[pointer → target entry | contained | unresolved])
```

Detectors read `fields` and never parse formats themselves. The sanitiser returns
`address → new value`; the renderer rebuilds the file with the same structure. A base64 payload is a
child `Field` (channel `base64`), and its parent's segment says how to re-encode it.

### Detection (Phase 2)

```
Field ─► decoded view (2.1: XHTML tags, HTML entities, %-escapes; exact offset map back; None if plain)
      ─► semantics (header / key path / FHIR role) ─┬─ PII-typed: structured findings over the value
                                                     ├─ preserved (2.1: guarded): value kept, but validated IDs,
                                                     │   cue-based names and confirmed values inside are removed
                                                     ├─ free text: identifiers · names · addresses · DOB labels
                                                     ├─ loose channel: ID-shaped tokens + adjacent names
                                                     ├─ FHIR id/fullUrl/reference (2.1): flagged id segments
                                                     └─ propagation: run-wide index (pass 1) + doc-local
        clinical keep spans ─► resolve (threshold, protection, overlap, merge; O(n log n)) ─► Finding
```

Only `resourceType` is skipped outright. No semantic switches detection off any more. Since Phase 2.1
the sanitiser also rewrites identifying FHIR ids together with their `fullUrl`s and references
(`rid-<entry>`), and withholds binary attachments (`data` removed) instead of quarantining the file. Memo
caches are cleared when a run ends (`detection/caches.py`).

Details and measurements: [PHASE2_DETECTION.md](../evaluation/PHASE2_DETECTION.md) and
[PHASE2_REMEDIATION.md](../evaluation/PHASE2_REMEDIATION.md).

### Why two passes
Identity resolution needs evidence from **every** file before any record can be pseudonymised. A
patient's Hindi prescription may be processed before the registration row that anchors their
identity. Pass 1 extracts normalised evidence and findings. Pass 2 writes output. The evidence index
lives only in memory and is never serialised (see the threat model).

## 3. Data flow and trust boundaries

```
 untrusted ──────────────────────► trusted-in-memory ─────────────────────► release (public)
 {input} files                     decoded text, findings (repr-safe),       sanitized/ (PII-free)
 (read-only, may contain           evidence index, cluster keys              report.json (hashes + counts)
  symlinks, bombs, PII names)      ReleaseSecret (unprintable)              records.jsonl (pseudonyms)
                                                                             stdout/stderr (counts only)
```

| Boundary | Rule |
|---|---|
| input → process | never open a symlink target outside the root (not even to hash it: an empty placeholder is declared `suppressed`); every read opens the verified real path inside the root with `O_NOFOLLOW \| O_NONBLOCK` and requires a regular file; broken symlinks and FIFOs/devices are reported unopened; cap sizes; content-based detection (the extension is only evidence); bounded JSON |
| process → release | only sanitised content crosses; quarantined files cross as a hash and a reason code only |
| process → stdout/stderr/logs | counts and fixed strings only; no tracebacks (they can contain values) |
| secret | env → `ReleaseSecret` → HMAC only; refuses `repr`, `str`, format and pickle |
| process → disk (non-release) | Phase 0 writes no temp files. If any become necessary: AES-GCM with an ephemeral in-memory key, inside `TMPDIR`, deleted in `finally` |

## 4. Determinism

- Fixed file order (`sorted`), no `set`/`dict` iteration over unordered sources in output paths.
  The organisers' own reference lost about 1 point to exactly this.
- No time, randomness, PID or locale in output. Timing appears only in `report.json`, which is
  excluded from the evaluator's byte comparison.
- All keyed derivations are HMAC-SHA256 of canonical cluster keys. Cluster keys must be derived
  from sorted evidence (for example the minimum record locator), never from processing order.

## 5. Performance envelope

Budget: 2 CPUs, 4 GB RSS for the whole process tree, 15 minutes (`time_good_s` = 60 s on the standard
profile). Phase 1 handles the 200-file practice set in 0.31 s at 27 MB peak RSS, and a 10× replica
(2,000 files) in 2.76 s at 34 MB (linear time, flat memory). With Phase 2.1 detection: 2.1 s / 32 MB
(200 files) and 19.8 s / 39 MB (2,000 files). Design rules:
stream-hash oversized files, keep one decoded copy per file, block-based linking (no O(n²)
all-pairs), and use no multiprocessing unless it is measured to help, because a second process doubles RSS.
