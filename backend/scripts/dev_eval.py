#!/usr/bin/env python3
"""Development evaluator approximating the OFFICIAL leak semantics (docs/SCORING.md).

    python backend/scripts/dev_eval.py --output OUT [--truth organiser-toolkit/dev/truth/truth.json] [--show 20]

``check_dev.py`` counts a leak only if an entity's whole surface survives. The
official scorer is stricter, and this script mirrors it as published:

* names: every *identifying* token (generic tokens such as Devi/Kumar/Md./ji are
  ignored) is a key; a token surviving as a whole word is a leak;
* digits: the digit key is searched in the output with separators removed between
  digits (``digits``); PIN keys must match a whole digit run (``digits_exact``);
* text: exact, case-folded text; DOB: the true date in any common format;
* both sides normalised (NFKC, case-fold, Indic digits -> ASCII, zero-width removed,
  diacritics stripped) and base64 runs decoded and appended;
* occurrences inside the unit's preserve probes are allowed (``Dr. Ramesh …``).

It also reports non-PII token retention (the over-redaction detector) and preserve-probe
survival. DEVELOPMENT ONLY: it reads the practice answer key, which the production
engine never does. It is an approximation, not the official score.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import datetime as dt
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

GENERIC = set(
    "devi kumar kumari md mohd ji jee sahab sahib saheb didi behenji babu amma bhaiya bhai mama chachu "
    "chacha papa mummy bibi bano begum khatoon singh kaur bai lal ram prasad".split()
)
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_DEVA = str.maketrans("०१२३४५६७८९", "0123456789")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_ZW).translate(_DEVA)
    s = "".join(
        c
        for c in unicodedata.normalize("NFD", s)
        if not (unicodedata.combining(c) and c.isascii() is False and "̀" <= c <= "ͯ")
    )
    return unicodedata.normalize("NFC", s).casefold()


def with_b64(text: str) -> str:
    extra = []
    for m in _B64.finditer(text):
        tok = m.group()
        with contextlib.suppress(binascii.Error, ValueError):
            extra.append(base64.b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8", errors="ignore"))
    return text + "\n" + "\n".join(extra)


def decode_b64(text: str) -> str:
    """Replace base64 runs that decode to UTF-8 with their decoded text."""

    def rep(m: re.Match) -> str:
        try:
            return base64.b64decode(m.group() + "=" * (-len(m.group()) % 4)).decode("utf-8")
        except (binascii.Error, ValueError):
            return m.group()

    return _B64.sub(rep, text)


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
    return [t for t in re.findall(r"[\wऀ-ॿ]+", norm(surface)) if t not in GENERIC and len(t) > 1]


def count(hay: str, needle: str, word: bool) -> int:
    if not needle:
        return 0
    if word:
        return len(re.findall(r"(?<![\wऀ-ॿ])" + re.escape(needle) + r"(?![\wऀ-ॿ])", hay))
    return hay.count(needle)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument(
        "--truth", default=str(Path(__file__).resolve().parents[2] / "organiser-toolkit/dev/truth/truth.json")
    )
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.output)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))
    inp = Path(a.truth).resolve().parents[1] / "input"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    renamed = {e["input_sha256"]: e.get("output") for e in report["files"]}
    keys_total, keys_leaked = Counter(), Counter()
    by_script, by_channel = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    examples = []
    probe_ok = probe_all = 0
    tok_in, tok_out = Counter(), Counter()
    for rel, f in truth["files"].items():
        o = renamed.get(f["sha256"])
        p = out / o if o else None
        exists = bool(p and p.is_file())
        raw_out = p.read_text(encoding="utf-8", errors="replace") if exists else ""
        text = norm(with_b64(raw_out))
        dtext = digits_view(text)
        fname = norm(o or "")
        src = inp / rel
        pii_tokens = set()
        # the output is searched file-wide, so allowed preserve-probe occurrences are counted file-wide too
        allowed_hay = "\n".join(norm(pv["text"]) for uu in f["units"].values() for pv in (uu.get("preserve") or []))
        for u in f["units"].values():
            probes = [norm(pv["text"]) for pv in (u.get("preserve") or [])]
            for e in u["entities"]:
                if e["type"] == "CANARY":
                    continue
                hay = fname if e["channel"] == "filename" else text
                m, key = e.get("match"), e.get("key")
                pii_tokens.update(re.findall(r"[a-z\u0900-\u097f]{3,}", norm(e["surface"])))  # all PII words
                if m == "name":
                    keys = [(t, True) for t in name_tokens(e["surface"])]
                elif m in ("digits", "digits_exact"):
                    keys = [(key, m == "digits_exact")]
                    hay = digits_view(hay) if m == "digits" else hay
                elif m == "dob":
                    keys = [(x, False) for x in dob_forms(key)]
                else:
                    keys = [(norm(key or e["surface"]), False)]
                leaked_any = False
                for k, word in keys:
                    if not k:
                        continue
                    allowed = count(allowed_hay, k, word)
                    occ = count(dtext if m == "digits" and e["channel"] != "filename" else hay, k, word)
                    if occ - allowed > 0 and (exists or e["channel"] == "filename"):
                        leaked_any = True
                keys_total[e["type"]] += 1
                by_script[e["script"]][1] += 1
                by_channel[e["channel"]][1] += 1
                if leaked_any:
                    keys_leaked[e["type"]] += 1
                    by_script[e["script"]][0] += 1
                    by_channel[e["channel"]][0] += 1
                    if len(examples) < a.show:
                        examples.append((e["type"], e["script"], e["channel"], rel))
            if exists:
                for pv in probes:
                    probe_all += 1
                    probe_ok += pv in text
        # non-PII token retention (multiset), over-redaction detector
        if exists and src.is_file():
            try:
                raw_in = src.read_bytes().decode(
                    f.get("encoding")
                    if f.get("encoding") not in (None, "utf-16")
                    else "utf-16"
                    if f.get("encoding") == "utf-16"
                    else "utf-8",
                    errors="replace",
                )
            except LookupError:
                raw_in = ""
            # payloads are compared decoded: re-encoding a cleaned attachment changes its base64 "tokens"
            word = r"[a-zऀ-ॿ]{3,}"
            ti = Counter(t for t in re.findall(word, norm(decode_b64(raw_in))) if t not in pii_tokens)
            to = Counter(re.findall(word, norm(decode_b64(raw_out))))
            tok_in.update(ti)
            tok_out.update({k: min(v, to.get(k, 0)) for k, v in ti.items()})
    tot, lk = sum(keys_total.values()), sum(keys_leaked.values())
    print(f"OFFICIAL-STYLE LEAK (token/digit-core): {lk}/{tot} = {100 * lk / max(tot, 1):.1f}%")
    for t in sorted(keys_total, key=lambda x: -keys_leaked[x]):
        print(f"   {t:<16} {keys_leaked[t]:>4}/{keys_total[t]:<4} {100 * keys_leaked[t] / keys_total[t]:5.1f}%")
    print("   by script:  " + ", ".join(f"{k} {100 * v[0] / max(v[1], 1):.1f}%" for k, v in sorted(by_script.items())))
    print("   by channel: " + ", ".join(f"{k} {100 * v[0] / max(v[1], 1):.1f}%" for k, v in sorted(by_channel.items())))
    print(f"PRESERVE PROBES kept: {probe_ok}/{probe_all} = {100 * probe_ok / max(probe_all, 1):.1f}%")
    print(
        f"NON-PII TOKEN RETENTION: {sum(tok_out.values())}/{sum(tok_in.values())} = "
        f"{100 * sum(tok_out.values()) / max(sum(tok_in.values()), 1):.1f}%"
    )
    for ex in examples:
        print("   leak:", " | ".join(ex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
