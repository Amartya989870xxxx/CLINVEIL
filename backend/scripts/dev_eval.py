#!/usr/bin/env python3
"""Development evaluator approximating the OFFICIAL leak and utility semantics (docs/SCORING.md).

    python backend/scripts/dev_eval.py --output OUT [--truth organiser-toolkit/dev/truth/truth.json] [--show 20]

Phase 2.1 rewrite (audit "metric notes"), now mirroring SCORING.md as published:

* **record-level leaks**: every key is counted inside its *unit* (CSV row, JSON record
  pointer, whole document, header, filename, file-level metadata). A unit that cannot be
  located in the output falls back to the whole output file (as the scorer does);
* ``allowed`` = occurrences inside the unit's preserve-probes *in the input*;
  ``pii_occ`` = input occurrences - allowed; ``leaked`` = clamp(output occurrences -
  allowed, 0, pii_occ); a mention's leak is the mean over its keys. Both the
  fractional (official-style) rate and the share of mentions with any leak are shown;
* **decoding**: base64 (standard + URL-safe), hex, ``\\uXXXX``, HTML entities and
  %-encoding are decoded and appended on both sides; NFKC, Cyrillic/Greek homoglyph
  folding, zero-width removal, all Indic digits -> ASCII, Latin diacritics stripped;
* **canaries** are scored (reported separately) and their tokens are PII for retention;
* **preserve probes** are scored at field level: 1.0 at the original field (``col:<Header>``
  or a record-relative JSON pointer), 0.8 elsewhere in the record, 0 lost; weighted;
* **token retention** counts every letter/digit token (numbers, units, short
  abbreviations), excludes PII tokens, dates and ages, and never credits placeholder
  words (``[NAME]`` does not "retain" the input word ``name``).

DEVELOPMENT ONLY: it reads the practice answer key, which the production engine never
does. It is an approximation of the official scorer, not the official score.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import csv
import datetime as dt
import html
import io
import json
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

GENERIC = set(
    "devi kumar kumari md mohd ji jee sahab sahib saheb didi behenji babu amma bhaiya bhai mama chachu "
    "chacha papa mummy bibi bano begum khatoon singh kaur bai lal ram prasad".split()
)
_B64 = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")
_HEX = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")
_UESC = re.compile(r"(?:\\u[0-9A-Fa-f]{4})+")
_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z_\-]*\]|\b(?:NAME|RELATIVE|PHONE|MRN|AADHAAR|ABHA|PAN|EMAIL|PIN|DOB)\b")
_DATE = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?\b")
_AGE = re.compile(r"(?i)\b\d{1,3}\s*(?:y(?:rs?|ears?)?|m(?:onths?)?|d(?:ays?)?)\b|\bage[d]?\s*[:\-]?\s*\d{1,3}\b")
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_HOMOGLYPHS = str.maketrans(
    "аеорсухіјѕАВЕКМНОРСТХοαειкνρτυχΟΑΒΕΗΙΚΜΝΡΤΧΖ",
    "aeopcyxijsABEKMHOPCTXoaeikvptuxOABEHIKMNPTXZ",
)
_WORD = re.compile(r"[\wऀ-ॿ]+")


def _digit_table() -> dict[int, int]:
    return {
        cp: ord(str(unicodedata.digit(chr(cp))))
        for cp in range(0x80, 0x20000)
        if unicodedata.category(chr(cp)) == "Nd" and unicodedata.digit(chr(cp), None) is not None
    }


_DIGITS = _digit_table()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_ZW).translate(_DIGITS).translate(_HOMOGLYPHS)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not ("̀" <= c <= "ͯ"))
    return unicodedata.normalize("NFC", s).casefold()


def _b64_decode(tok: str) -> str | None:
    t = tok.replace("-", "+").replace("_", "/") if ("-" in tok or "_" in tok) else tok
    with contextlib.suppress(binascii.Error, ValueError, UnicodeDecodeError):
        out = base64.b64decode(t + "=" * (-len(t) % 4), validate=True).decode("utf-8")
        if out and all(c.isprintable() or c in "\n\r\t" for c in out):
            return out
    return None


def decoded_variants(text: str) -> list[str]:
    """Hidden payloads, decoded (the scorer appends them before counting)."""
    extra = []
    for m in _B64.finditer(text):
        d = _b64_decode(m.group())
        if d:
            extra.append(d)
    for m in _HEX.finditer(text):
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            d = bytes.fromhex(m.group()).decode("utf-8")
            if d.isprintable():
                extra.append(d)
    for m in _UESC.finditer(text):
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            extra.append(m.group().encode("ascii").decode("unicode_escape"))
    if "&" in text:
        extra.append(html.unescape(text))
    if "%" in text:
        extra.append(urllib.parse.unquote(text))
    return extra


def view(text: str) -> str:
    return norm("\n".join([text, *decoded_variants(text)]))


def digits_view(s: str) -> str:
    return re.sub(r"(?<=\d)[\s\-./_()]+(?=\d)", "", s)


def dob_forms(key: str) -> list[str]:
    try:
        d = dt.date.fromisoformat(key)
    except ValueError:
        return [key]
    return list(
        {
            d.strftime(f)
            for f in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y")
        }
        | {f"{d.day}/{d.month}/{d.year}"}
    )


def name_tokens(surface: str) -> list[str]:
    return [t for t in _WORD.findall(norm(surface)) if t not in GENERIC and len(t) > 1]


def count(hay: str, needle: str, word: bool) -> int:
    if not needle:
        return 0
    if word:
        return len(re.findall(r"(?<![\wऀ-ॿ])" + re.escape(needle) + r"(?![\wऀ-ॿ])", hay))
    return hay.count(needle)


# --------------------------------------------------------------------------- record location
class Parsed:
    """A file parsed just enough to locate scoring units and probe fields."""

    def __init__(self, raw: str, fmt: str, delimiter: str | None, name: str) -> None:
        self.raw, self.fmt, self.name = raw, fmt, name
        self.rows: list[list[str]] | None = None
        self.json = None
        if fmt in ("csv", "tsv"):
            with contextlib.suppress(csv.Error):
                self.rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter or ("\t" if fmt == "tsv" else ",")))
        elif fmt in ("json", "fhir"):
            with contextlib.suppress(ValueError, RecursionError):
                self.json = json.loads(raw)

    def _ptr(self, ptr: str):
        node = self.json
        for part in [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:]]:
            if isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node

    def unit(self, loc: str) -> str | None:
        """Text of one scoring unit, or ``None`` if it cannot be located."""
        if loc == "doc":
            return self.raw
        if loc == "@filename":
            return self.name
        if loc == "@header":
            return ",".join(self.rows[0]) if self.rows else None
        if loc.startswith("row:") and self.rows is not None:
            i = int(loc[4:]) + 1
            return ",".join(self.rows[i]) if i < len(self.rows) else None
        if loc.startswith("/") and self.json is not None:
            node = self._ptr(loc)
            return json.dumps(node, ensure_ascii=False) if node is not None else None
        return None  # "@file" and anything unknown: whole-file fallback

    def field(self, loc: str, path: str) -> str | None:
        if path.startswith("col:") and self.rows and loc.startswith("row:"):
            header, i = self.rows[0], int(loc[4:]) + 1
            col = path[4:]
            if col in header and i < len(self.rows) and header.index(col) < len(self.rows[i]):
                return self.rows[i][header.index(col)]
            return None
        if path.startswith("/") and self.json is not None and loc.startswith("/"):
            node = self._ptr(loc + path)
            return node if isinstance(node, str) else (json.dumps(node, ensure_ascii=False) if node else None)
        return None


def read_input(src: Path, enc: str | None) -> str:
    data = src.read_bytes()
    for e in ([enc] if enc else []) + ["utf-8-sig", "utf-16", "cp1252", "latin-1"]:
        with contextlib.suppress(LookupError, UnicodeDecodeError):
            return data.decode(e)
    return data.decode("utf-8", errors="replace")


def retention_tokens(text: str, exclude: set[str]) -> Counter:
    text = _AGE.sub(" ", _DATE.sub(" ", text))
    return Counter(t for t in _WORD.findall(norm(text)) if t not in exclude)


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument(
        "--truth", default=str(Path(__file__).resolve().parents[2] / "organiser-toolkit/dev/truth/truth.json")
    )
    ap.add_argument("--input", default=None, help="input directory (default: inferred sibling input/ of --truth)")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.output)
    truth_path = Path(a.truth)
    try:
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"dev_eval: truth file not found: {truth_path}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"dev_eval: invalid truth file ({type(exc).__name__})", file=sys.stderr)
        return 2
    if not isinstance(truth, dict) or not isinstance(truth.get("files"), dict):
        print("dev_eval: invalid truth schema (missing 'files' mapping)", file=sys.stderr)
        return 2
    inp = Path(a.input) if a.input else truth_path.resolve().parents[1] / "input"
    try:
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"dev_eval: invalid or missing report.json ({type(exc).__name__})", file=sys.stderr)
        return 2
    renamed = {e["input_sha256"]: e.get("output") for e in report.get("files") or []}

    frac_total, frac_leak = Counter(), Counter()  # official-style fractional leak per type
    any_leak = Counter()  # mentions with at least one leaked key
    by_script, by_channel = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])
    canary_total = canary_leaked = 0
    examples = []
    probe_score = probe_weight = 0.0
    probes_exact = probes_elsewhere = probes_lost = 0
    tok_in, tok_out = Counter(), Counter()
    located = unlocated = 0

    for rel, f in truth["files"].items():
        o = renamed.get(f["sha256"])
        p = out / o if o else None
        exists = bool(p and p.is_file())
        raw_out = p.read_text(encoding="utf-8", errors="replace") if exists else ""
        src = inp / rel
        raw_in = read_input(src, f.get("encoding")) if src.is_file() else ""
        fmt = f.get("format", "text")
        pin = Parsed(raw_in, fmt, f.get("delimiter"), rel)
        pout = Parsed(raw_out, fmt, f.get("delimiter"), o or "")
        out_file_view = view(raw_out)
        pii_tokens: set[str] = set()
        for loc, u in f["units"].items():
            unit_out = pout.unit(loc) if exists else None
            if exists and loc not in ("@file",) and unit_out is None:
                unlocated += 1
            elif exists:
                located += 1
            unit_in = pin.unit(loc) or raw_in
            unit_view = view(unit_out) if unit_out is not None else out_file_view
            hay_out = view(o or "") if loc == "@filename" else unit_view
            hay_in = view(rel) if loc == "@filename" else view(unit_in)
            probes = u.get("preserve") or []
            allowed_hay = "\n".join(norm(pv["text"]) for pv in probes)
            for e in u["entities"]:
                m, key = e.get("match"), e.get("key")
                pii_tokens.update(_WORD.findall(norm(e["surface"])))
                if m == "name":
                    keys = [(t, True) for t in name_tokens(e["surface"])]
                elif m in ("digits", "digits_exact"):
                    keys = [(key, m == "digits_exact")]
                elif m == "dob":
                    keys = [(x, False) for x in dob_forms(key)]
                else:
                    keys = [(norm(key or e["surface"]), False)]
                fracs = []
                for k, word in keys:
                    if not k:
                        continue
                    hin = digits_view(hay_in) if m == "digits" else hay_in
                    hout = digits_view(hay_out) if m == "digits" else hay_out
                    allowed = count(allowed_hay, k, word)
                    pii_occ = max(count(hin, k, word) - allowed, 1)
                    seen = exists or loc == "@filename"
                    leaked = min(max(count(hout, k, word) - allowed, 0), pii_occ) if seen else 0
                    fracs.append(leaked / pii_occ)
                if not fracs:
                    continue
                if m == "dob":  # any one format leaking is a leak of the date
                    fracs = [max(fracs)]
                leak = sum(fracs) / len(fracs)
                if e["type"] == "CANARY" or e.get("canary"):
                    canary_total += 1
                    canary_leaked += leak > 0
                    continue
                frac_total[e["type"]] += 1
                frac_leak[e["type"]] += leak
                any_leak[e["type"]] += leak > 0
                by_script[e["script"]][0] += leak
                by_script[e["script"]][1] += 1
                by_channel[e["channel"]][0] += leak
                by_channel[e["channel"]][1] += 1
                if leak > 0 and len(examples) < a.show:
                    examples.append((e["type"], e["script"], e["channel"], f"{leak:.2f}", rel))
            # preserve probes, field-level
            for pv in probes:
                w = float(pv.get("weight", 1.0))
                probe_weight += w
                t = norm(pv["text"])
                fv = pout.field(loc, pv["path"]) if exists and pv.get("path") else None
                rec = norm(unit_out) if unit_out is not None else (norm(raw_out) if exists else "")
                if fv is not None and t in norm(fv):
                    probe_score += w
                    probes_exact += 1
                elif t in rec and pv.get("path"):
                    probe_score += 0.8 * w
                    probes_elsewhere += 1
                elif t in rec:  # probe without a field path: record-level
                    probe_score += w
                    probes_exact += 1
                else:
                    probes_lost += 1
        # non-PII token retention (multiset); payloads compared decoded; placeholders never count
        if exists and raw_in:
            ti = retention_tokens("\n".join([raw_in, *decoded_variants(raw_in)]), pii_tokens)
            to = retention_tokens(_PLACEHOLDER.sub(" ", "\n".join([raw_out, *decoded_variants(raw_out)])), set())
            tok_in.update(ti)
            tok_out.update({k: min(v, to.get(k, 0)) for k, v in ti.items()})

    tot = sum(frac_total.values())
    lk = sum(frac_leak.values())
    print(f"OFFICIAL-STYLE LEAK (fractional, record-level): {lk:.1f}/{tot} = {100 * lk / max(tot, 1):.2f}%")
    print(f"   mentions with any leaked key: {sum(any_leak.values())}/{tot}")
    for t in sorted(frac_total, key=lambda x: -frac_leak[x]):
        print(
            f"   {t:<16} {frac_leak[t]:>6.1f}/{frac_total[t]:<4} {100 * frac_leak[t] / frac_total[t]:5.1f}%"
            f"  (any: {any_leak[t]})"
        )
    print("   by script:  " + ", ".join(f"{k} {100 * v[0] / max(v[1], 1):.1f}%" for k, v in sorted(by_script.items())))
    print("   by channel: " + ", ".join(f"{k} {100 * v[0] / max(v[1], 1):.1f}%" for k, v in sorted(by_channel.items())))
    print(f"CANARIES leaked: {canary_leaked}/{canary_total}")
    print(f"UNITS located in output: {located}, unlocated (whole-file fallback): {unlocated}")
    print(
        f"PRESERVE PROBES (weighted, field-level): {100 * probe_score / max(probe_weight, 1e-9):.1f}%  "
        f"[at field {probes_exact}, elsewhere {probes_elsewhere}, lost {probes_lost}]"
    )
    print(
        f"NON-PII TOKEN RETENTION: {sum(tok_out.values())}/{sum(tok_in.values())} = "
        f"{100 * sum(tok_out.values()) / max(sum(tok_in.values()), 1):.1f}%"
    )
    for ex in examples:
        print("   leak:", " | ".join(ex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
