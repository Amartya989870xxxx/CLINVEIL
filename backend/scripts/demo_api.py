#!/usr/bin/env python3
"""Optional local demo API for the CLINVEIL frontend (contract "clinveil-frontend/1").

    .venv/bin/python backend/scripts/demo_api.py            # http://127.0.0.1:8765/api/v1
    cd frontend && npm run dev                              # proxies /api to it

NOT part of the evaluator path and never imported by the engine. Standard library only. It does not change
or re-implement the engine: each run is the real CLI (`main.py --input ... --output ...`) in a subprocess, and
every number it serves is read from that run's own files (report.json, logs/detection_summary.json) or from
the organiser's unmodified checkers. Contract: docs/api-contract/frontend-v1.md (proposed; additions marked).

Safety rules (see also the contract):
* binds to 127.0.0.1 only; rejects requests whose Host or Origin is not local (DNS rebinding, CSRF);
* runs only allowlisted synthetic datasets, chosen by id; the client never sends a path;
* RAKSHA_SECRET is random per server process, passed only to the engine's environment, never served or logged;
* engine and checker stdout/stderr are never forwarded: only numbers parsed with fixed patterns;
* error bodies are fixed text; one run at a time; a 20-minute timeout; run folders live in a private temp
  directory that is deleted when the server stops.
"""

from __future__ import annotations

import argparse
import atexit
import difflib
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
TOOLKIT = REPO / "organiser-toolkit"
CONTRACT = "clinveil-frontend/1"
RUN_TIMEOUT_S = 20 * 60
MAX_BODY = 4096
JOB_ID = re.compile(r"^[a-f0-9]{16}$")
SECRET = secrets.token_hex(32)  # per process; never leaves this process except into the engine's environment
RUN_ROOT = Path(tempfile.mkdtemp(prefix="clinveil-demo-runs-"))
atexit.register(shutil.rmtree, RUN_ROOT, True)

# What the engine at this commit implements. Kept in step with docs/PROJECT_HANDOFF.md §3 by hand: the engine
# exposes no capability flags, so this table is the one place a human must update when Phase 3/4 land.
CAPABILITIES = {
    "ingestion": "implemented",
    "detection": "implemented",
    "linking": "not_available",
    "privacy_transforms": "partial",
    "export": "implemented",
    "validation": "implemented",
}

# ---------------------------------------------------------------------------------------------------- datasets


def sniff(head: bytes) -> str:
    """Same rules as frontend/src/utils/inspect.ts, so both sides describe a dataset identically."""
    if not head:
        return "empty"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF")):
        return "image"
    if head.startswith((b"PK\x03\x04", b"\x1f\x8b", b"7z\xbc\xaf")):
        return "archive"
    utf16 = head.startswith((b"\xff\xfe", b"\xfe\xff"))
    if not utf16 and b"\x00" in head[:4096]:
        return "binary"
    enc = ("utf-16-le" if head[:1] == b"\xff" else "utf-16-be") if utf16 else "utf-8"
    text = head.decode(enc, errors="replace").lstrip("﻿").lstrip()
    if text.startswith("<"):
        return "xml"
    if text.startswith(("{", "[")):
        return "fhir" if re.search(r'"resourceType"\s*:\s*"Bundle"', text) else "json"
    first = text.splitlines()[0] if text else ""
    if first.count("\t") >= 2:
        return "tsv"
    if len(re.findall(r"[,;|]", first)) >= 2:
        return "csv"
    return "text"


UNSUPPORTED = {"pdf", "image", "archive", "binary", "xml", "empty"}


@dataclass
class Dataset:
    id: str
    label: str
    description: str
    root: Path
    has_practice_checks: bool
    files: int = 0
    bytes: int = 0
    formats: dict[str, int] = field(default_factory=dict)
    expected_unsupported: int = 0
    by_sha: dict[str, tuple[str, str]] = field(default_factory=dict)  # sha256 -> (relative path, format)

    def scan(self) -> None:
        for p in sorted(self.root.rglob("*")):
            if p.is_symlink() or not p.is_file():
                continue
            data = p.read_bytes()
            fmt = sniff(data[:8192])
            self.files += 1
            self.bytes += len(data)
            self.formats[fmt] = self.formats.get(fmt, 0) + 1
            self.expected_unsupported += fmt in UNSUPPORTED
            self.by_sha[hashlib.sha256(data).hexdigest()] = (str(p.relative_to(self.root)), fmt)

    def info(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "synthetic": True,
            "description": self.description,
            "files": self.files,
            "bytes": self.bytes,
            "formats": self.formats,
            "expected_unsupported": self.expected_unsupported,
        }


def _readme_summary(readme: Path) -> str:
    """First paragraph after the title of a stress dataset's README."""
    try:
        paras = [p.strip() for p in readme.read_text(encoding="utf-8").split("\n\n")]
    except OSError:
        return "Synthetic stress-test dataset derived from the practice data."
    body = [p for p in paras if p and not p.startswith("#")]
    return " ".join(body[0].split()) if body else "Synthetic stress-test dataset."


def discover_datasets() -> dict[str, Dataset]:
    found: list[Dataset] = []
    practice = TOOLKIT / "dev" / "input"
    if practice.is_dir():
        found.append(
            Dataset(
                id="practice",
                label="Secret Wards practice dataset",
                description=(
                    "The organiser's synthetic practice exports from four fictional hospital systems: registrations, "
                    "OPD visits, discharge summaries, Hindi prescriptions, Hinglish nursing notes, lab reports, "
                    "FHIR R4 bundles and deliberately broken files."
                ),
                root=practice,
                has_practice_checks=True,
            )
        )
    # stress datasets are only accepted if the generator's marker file is present (synthetic by construction)
    for d in sorted(REPO.glob("stress_*")):
        if (d / ".stress_dataset").is_file() and (d / "input").is_dir():
            name = d.name.removeprefix("stress_").replace("_", " ")
            found.append(
                Dataset(
                    id=d.name,
                    label=f"Stress test: {name}",
                    description=_readme_summary(d / "README.md"),
                    root=d / "input",
                    has_practice_checks=False,
                )
            )
    for ds in found:
        ds.scan()
    return {ds.id: ds for ds in found}


# -------------------------------------------------------------------------------------------------------- jobs


@dataclass
class Job:
    id: str
    dataset: Dataset
    out: Path
    state: str = "queued"  # queued | running | complete | complete_with_quarantine | failed
    started: float | None = None
    finished: float | None = None
    exit_code: int | None = None
    report: dict | None = None
    detection: dict | None = None
    contract_ok: bool | None = None
    practice: dict | None = None  # parsed check_dev.py aggregates (practice dataset only)


JOBS: dict[str, Job] = {}
ORDER: list[str] = []
LOCK = threading.Lock()
KEEP_JOBS = 5


def _engine_env() -> dict[str, str]:
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")}
    keep["RAKSHA_SECRET"] = SECRET
    keep["PYTHONDONTWRITEBYTECODE"] = "1"
    return keep


def _run_quiet(args: list[str], timeout: int) -> tuple[int, str]:
    """Runs a command; returns (exit code, stdout). Output is only ever parsed, never forwarded."""
    try:
        p = subprocess.run(args, cwd=REPO, env=_engine_env(), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return -1, ""


_N = r"(\d+)"
PRACTICE_PATTERNS = {
    "pii": re.compile(rf"PERSONAL DATA: {_N} of {_N} pieces still visible"),
    "canaries": re.compile(rf"CANARIES: {_N} of {_N} planted canaries"),
    "medical": re.compile(rf"MEDICAL DATA KEPT: {_N} of {_N} medical values"),
    "raw": re.compile(rf"RAW COPIES: {_N} broken/unsupported files"),
    "f05": re.compile(r"PATIENT LINKING: precision [\d.]+, recall [\d.]+, F0\.5 ([\d.]+)"),
}


def _parse_practice(stdout: str) -> dict:
    out: dict = {}
    for key, rx in PRACTICE_PATTERNS.items():
        m = rx.search(stdout)
        if m:
            out[key] = [float(g) if "." in g else int(g) for g in m.groups()]
    out["linked_nothing"] = "you linked nothing yet" in stdout
    return out


def run_job(job: Job) -> None:
    job.state, job.started = "running", time.time()
    code, _ = _run_quiet(
        [sys.executable, str(REPO / "main.py"), "--input", str(job.dataset.root), "--output", str(job.out)],
        RUN_TIMEOUT_S,
    )
    job.exit_code = code
    try:
        job.report = json.loads((job.out / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        job.report = None
    try:
        job.detection = json.loads((job.out / "logs" / "detection_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        job.detection = None
    validator = TOOLKIT / "validate_output.py"
    if job.report and validator.is_file():
        vcode, vout = _run_quiet(
            [sys.executable, str(validator), "--input", str(job.dataset.root), "--output", str(job.out)], 300
        )
        job.contract_ok = vcode == 0 and "CONTRACT OK" in vout
    checker = TOOLKIT / "check_dev.py"
    if job.report and job.dataset.has_practice_checks and checker.is_file():
        _, cout = _run_quiet([sys.executable, str(checker), "--output", str(job.out)], 300)
        job.practice = _parse_practice(cout)
    job.finished = time.time()
    quarantined = (job.report or {}).get("counts", {}).get("files_quarantined", 0)
    if code == 0 and job.report:
        job.state = "complete_with_quarantine" if quarantined else "complete"
    else:
        job.state = "failed"


def start_job(ds: Dataset) -> Job:
    with LOCK:
        if any(j.state in ("queued", "running") for j in JOBS.values()):
            raise BusyError
        jid = secrets.token_hex(8)
        job = Job(id=jid, dataset=ds, out=RUN_ROOT / jid / "out")
        job.out.parent.mkdir(parents=True)
        JOBS[jid] = job
        ORDER.append(jid)
        while len(ORDER) > KEEP_JOBS:  # keep disk use bounded
            old = JOBS.pop(ORDER.pop(0))
            shutil.rmtree(old.out.parent, ignore_errors=True)
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job


class BusyError(Exception):
    pass


# ---------------------------------------------------------------------------------------------- serialisation


def _iso(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else None


def job_status(job: Job) -> dict:
    running = job.state in ("queued", "running")
    done_ok = job.state in ("complete", "complete_with_quarantine")
    stages = []
    for cap, cap_state in CAPABILITIES.items():
        if cap_state == "not_available":
            stages.append({"id": cap, "state": "not_available", "detail_code": "phase_3"})
        elif running:
            # the CLI reports nothing until it finishes (contract Q5): every built stage is honestly "in progress"
            stages.append({"id": cap, "state": "in_progress", "detail_code": "no_stage_progress"})
        elif not done_ok:
            stages.append({"id": cap, "state": "failed", "detail_code": None})
        elif cap_state == "partial":
            stages.append({"id": cap, "state": "needs_attention", "detail_code": "partial_dob_and_birth_year_only"})
        elif cap == "ingestion" and job.state == "complete_with_quarantine":
            stages.append({"id": cap, "state": "complete", "detail_code": "files_set_aside"})
        elif cap == "validation":
            stages.append({"id": cap, "state": "complete", "detail_code": "contract_ok" if job.contract_ok else None})
        else:
            stages.append({"id": cap, "state": "complete", "detail_code": None})
    seconds = (job.report or {}).get("timing", {}).get("seconds") if job.report else None
    if seconds is None and job.started:
        seconds = round((job.finished or time.time()) - job.started, 2)
    return {
        "contract": CONTRACT,
        "source": "live_backend",
        "job_id": job.id,
        "dataset_id": job.dataset.id,
        "dataset_label": job.dataset.label,  # addition to v1: human label for the run's dataset
        "state": job.state,
        "started_at": _iso(job.started),
        "finished_at": _iso(job.finished),
        "exit_code": job.exit_code,
        "seconds": seconds,
        "stages": stages,
    }


def summary(job: Job) -> dict:
    r = job.report or {}
    return {
        "contract": CONTRACT,
        "source": "live_backend",
        "job_id": job.id,
        "counts": r.get("counts", {}),
        "timing": r.get("timing"),
        "resources": r.get("resources"),
        "validation": {"contract_ok": job.contract_ok, "checker": "validate_output.py"},
    }


def findings(job: Job) -> dict:
    d = job.detection or {}
    langs = d.get("by_language") or {}
    script = {k: v for k, v in langs.items() if k in ("latin", "deva", "hinglish")} or None
    return {
        "contract": CONTRACT,
        "source": "live_backend",
        "job_id": job.id,
        "by_type": (job.report or {}).get("entities", {}),
        "by_script": script,
        "by_channel": d.get("by_channel") or None,
    }


def quarantine(job: Job) -> dict:
    files, reasons = [], {}
    for f in (job.report or {}).get("files", []):
        _, fmt = job.dataset.by_sha.get(f.get("input_sha256", ""), ("", "unknown"))
        row = {
            "input_sha256": f.get("input_sha256"),
            "output": f.get("output"),
            "status": f.get("status"),
            "format": fmt,
            "reason": f.get("reason"),
        }
        files.append(row)
        if row["status"] != "sanitized" and row["reason"]:
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    return {"contract": CONTRACT, "source": "live_backend", "job_id": job.id, "reasons": reasons, "files": files}


def metrics(job: Job) -> dict:
    today = datetime.now().astimezone().date().isoformat()  # the machine's local date: this is a local tool
    ds = job.dataset.label
    pr = job.practice or {}
    r = job.report or {}

    def m(key, label, value, unit, method, caveat=None, num=None, den=None, measured=True):
        out = {
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "dataset": ds,
            "method": method,
            "measured_at": today if measured and value is not None else None,
            "caveat": caveat,
        }
        if num is not None:
            out["numerator"], out["denominator"] = num, den
        return out

    no_key = "The organiser's checker has an answer key only for the practice dataset."
    pii, can, med, raw = pr.get("pii"), pr.get("canaries"), pr.get("medical"), pr.get("raw")
    return {
        "contract": CONTRACT,
        "source": "live_backend",
        "job_id": job.id,
        "dimensions": [
            {
                "id": "privacy_attacks",
                "measurements": [
                    m(
                        "attack_arena",
                        "Resistance to the organiser's attack arena (A1-A7)",
                        None,
                        "ratio",
                        "Official evaluator (not available to teams before the event)",
                        "Only the official evaluator runs the attacker.",
                    )
                ],
            },
            {
                "id": "detection",
                "measurements": [
                    m(
                        "pii_visible",
                        "Practice-set personal information still visible",
                        pii[0] if pii else None,
                        "count",
                        "organiser check_dev.py",
                        None if pii else no_key,
                        *(pii or [None, None]),
                    ),
                    m(
                        "canaries_found",
                        "Planted canary identities found in the output",
                        can[0] if can else None,
                        "count",
                        "organiser check_dev.py",
                        None if can else no_key,
                        *(can or [None, None]),
                    ),
                ],
            },
            {
                "id": "utility",
                "measurements": [
                    m(
                        "medical_values_kept",
                        "Medical values kept",
                        (med[0] / med[1]) if med and med[1] else None,
                        "ratio",
                        "organiser check_dev.py",
                        "Checks that listed values survive verbatim; it is not a clinical certification."
                        if med
                        else no_key,
                        *(med or [None, None]),
                    )
                ],
            },
            {
                "id": "identity",
                "measurements": [
                    m(
                        "linking_f05",
                        "Records confidently linked (pairwise F0.5)",
                        None if pr.get("linked_nothing", True) else (pr.get("f05") or [None])[0],
                        "ratio",
                        "organiser check_dev.py",
                        "Linking is not implemented yet (Phase 3).",
                    )
                ],
            },
            {
                "id": "integrity",
                "measurements": [
                    m(
                        "contract_ok",
                        "Output contract validation",
                        None if job.contract_ok is None else int(job.contract_ok),
                        "bool",
                        "organiser validate_output.py",
                        None
                        if job.contract_ok is not None
                        else "The organiser toolkit is not installed next to the repo.",
                    ),
                    m(
                        "raw_copies",
                        "Broken files copied out unchanged",
                        raw[0] if raw else None,
                        "count",
                        "organiser check_dev.py",
                        None if raw else no_key,
                    ),
                ],
            },
            {
                "id": "performance",
                "measurements": [
                    m(
                        "seconds",
                        "Processing time",
                        (r.get("timing") or {}).get("seconds"),
                        "seconds",
                        "report.json timing",
                        "Measured on this machine, without the official 2-CPU / 4 GB limits.",
                    ),
                    m(
                        "peak_rss_mb",
                        "Peak memory",
                        (r.get("resources") or {}).get("peak_rss_mb"),
                        "mb",
                        "report.json resources",
                    ),
                ],
            },
        ],
    }


PLACEHOLDER = re.compile(r"\[[A-Z_]+\]")
TOKEN = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)
TITLES = {
    "discharge": "Discharge summary",
    "notes": "Clinical note",
    "prescriptions": "Prescription",
    "lab": "Lab report",
    "opd": "OPD record",
    "registration": "Registration record",
}


def _removed_spans(before: str, after: str) -> list[dict]:
    """Spans of `before` that are not in `after`, from a token-level diff (never character soup)."""
    a = [m.group(0) for m in TOKEN.finditer(before)]
    b = [m.group(0) for m in TOKEN.finditer(after)]
    starts, pos = [], 0
    for t in a:
        starts.append(pos)
        pos += len(t)
    starts.append(pos)
    spans = []
    for op, i1, i2, _, _ in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("replace", "delete") and i2 > i1:
            s, e = starts[i1], starts[i2]
            while s < e and before[s].isspace():
                s += 1
            while e > s and before[e - 1].isspace():
                e -= 1
            if e > s:
                spans.append({"start": s, "end": e, "kind": "removed"})
    return spans


def examples(job: Job) -> dict:
    """Up to three short synthetic text records with changes, before and after. File names are never sent."""
    out = []
    seen: dict[str, int] = {}
    for f in (job.report or {}).get("files", []):
        if len(out) >= 3:
            break
        rel_out = f.get("output") or ""
        src = job.dataset.by_sha.get(f.get("input_sha256", ""))
        if f.get("status") != "sanitized" or not src or src[1] != "text" or not rel_out.endswith(".txt"):
            continue
        before_p, after_p = job.dataset.root / src[0], job.out / rel_out
        try:
            if before_p.stat().st_size > 6000:
                continue
            before = before_p.read_text(encoding="utf-8")
            after = after_p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if before == after:
            continue
        folder = Path(src[0]).parts[0] if len(Path(src[0]).parts) > 1 else ""
        kind = TITLES.get(folder, "Record")
        seen[kind] = seen.get(kind, 0) + 1
        out.append(
            {
                "id": f"example-{len(out) + 1}",
                "title": f"{kind} {seen[kind]} (synthetic)",
                "before": before,
                "after": after,
                "synthetic": True,
                "spans_before": _removed_spans(before, after),
                "spans_after": [
                    {"start": m.start(), "end": m.end(), "kind": "removed"} for m in PLACEHOLDER.finditer(after)
                ],
            }
        )
    return {"contract": CONTRACT, "source": "live_backend", "job_id": job.id, "examples": out}


def release_zip(job: Job) -> bytes:
    """sanitized/, report.json and records.jsonl only: never input, logs or anything set aside."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("report.json", "records.jsonl"):
            p = job.out / name
            if p.is_file():
                z.write(p, name)
        san = job.out / "sanitized"
        for p in sorted(san.rglob("*")) if san.is_dir() else []:
            if p.is_file() and not p.is_symlink():
                z.write(p, str(p.relative_to(job.out)))
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------------- HTTP

ERRORS = {
    "not_found": (HTTPStatus.NOT_FOUND, "The requested result does not exist."),
    "invalid_request": (HTTPStatus.BAD_REQUEST, "The request was not valid."),
    "unavailable": (HTTPStatus.CONFLICT, "Another run is in progress, or this run has not finished yet."),
    "forbidden": (HTTPStatus.FORBIDDEN, "Requests are accepted from this computer only."),
    "internal": (HTTPStatus.INTERNAL_SERVER_ERROR, "The demo server could not complete the request."),
}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


class Handler(BaseHTTPRequestHandler):
    server_version = "clinveil-demo"
    sys_version = ""
    datasets: dict[str, Dataset] = {}
    engine_commit: str | None = None

    def log_message(self, fmt: str, *args) -> None:  # method, path (ids only) and status; never bodies
        sys.stderr.write(f"demo-api {self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    # -- helpers
    def _local(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        origin = self.headers.get("Origin")
        if host not in LOCAL_HOSTS:
            return False
        return origin is None or (urlsplit(origin).hostname or "") in LOCAL_HOSTS

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code: str) -> None:
        status, msg = ERRORS[code]
        self._json({"contract": CONTRACT, "error": {"code": code, "message": msg}}, status)

    def _job(self, jid: str, finished: bool = False) -> Job | None:
        job = JOBS.get(jid) if JOB_ID.match(jid) else None
        if not job:
            self._error("not_found")
            return None
        if finished and job.state in ("queued", "running"):
            self._error("unavailable")
            return None
        return job

    # -- routes
    def do_GET(self) -> None:
        if not self._local():
            return self._error("forbidden")
        parts = [p for p in urlsplit(self.path).path.split("/") if p]
        if parts[:2] != ["api", "v1"]:
            return self._error("not_found")
        r = parts[2:]
        try:
            if r == ["health"]:
                return self._json(
                    {
                        "contract": CONTRACT,
                        "source": "live_backend",
                        "status": "ok",
                        "engine_version": _engine_version(),
                        "engine_commit": self.engine_commit,
                        "capabilities": CAPABILITIES,
                    }
                )
            if r == ["datasets"]:
                return self._json(
                    {
                        "contract": CONTRACT,
                        "source": "live_backend",
                        "datasets": [d.info() for d in self.datasets.values()],
                    }
                )
            if r == ["jobs", "latest"]:  # addition to v1: the most recent run, if any
                if not ORDER:
                    return self._error("not_found")
                return self._json(job_status(JOBS[ORDER[-1]]))
            if len(r) == 2 and r[0] == "jobs":
                job = self._job(r[1])
                return job and self._json(job_status(job))
            if len(r) == 3 and r[0] == "jobs":
                handlers = {
                    "summary": summary,
                    "findings": findings,
                    "quarantine": quarantine,
                    "metrics": metrics,
                    "examples": examples,
                }
                if r[2] in handlers:
                    job = self._job(r[1], finished=True)
                    return job and self._json(handlers[r[2]](job))
                if r[2] == "download":
                    job = self._job(r[1], finished=True)
                    if job:
                        if job.state == "failed":
                            return self._error("not_found")
                        data = release_zip(job)
                        return self._send(
                            200,
                            data,
                            "application/zip",
                            {"Content-Disposition": f'attachment; filename="clinveil-release-{job.id}.zip"'},
                        )
                    return None
            return self._error("not_found")
        except Exception:  # noqa: BLE001 - never leak a traceback: it could contain record content
            return self._error("internal")

    def do_POST(self) -> None:
        if not self._local():
            return self._error("forbidden")
        if [p for p in urlsplit(self.path).path.split("/") if p] != ["api", "v1", "jobs"]:
            return self._error("not_found")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._error("invalid_request")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                return self._error("invalid_request")
            body = json.loads(self.rfile.read(length))
            ds = self.datasets.get(body.get("dataset_id")) if isinstance(body, dict) else None
            if not ds or body.get("policy_preset", "competition_default") != "competition_default":
                return self._error("invalid_request")
            job = start_job(ds)
        except BusyError:
            return self._error("unavailable")
        except (ValueError, TypeError):
            return self._error("invalid_request")
        self._json({"contract": CONTRACT, "source": "live_backend", "job_id": job.id}, HTTPStatus.ACCEPTED)


def _engine_version() -> str:
    m = re.search(
        r'__version__\s*=\s*"([^"]+)"', (REPO / "backend/src/clinveil/__init__.py").read_text(encoding="utf-8")
    )
    return m.group(1) if m else "unknown"


def _engine_commit() -> str | None:
    git = shutil.which("git")  # absolute path: never run whatever "git" happens to resolve to later
    if not git:
        return None
    try:
        p = subprocess.run([git, "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=5)
        sha = p.stdout.strip()
        return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="CLINVEIL local demo API (optional; not used by the evaluator)")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    Handler.datasets = discover_datasets()
    Handler.engine_commit = _engine_commit()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    names = ", ".join(Handler.datasets) or "none (organiser-toolkit/dev/input not found)"
    print(f"CLINVEIL demo API on http://127.0.0.1:{a.port}/api/v1  datasets: {names}", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
