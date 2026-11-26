"""Cross-channel propagation end to end through the CLI (synthetic data).

One confirmed patient (structured registration row) reappears in a free-text note,
a filename, an export-metadata path, a dynamic JSON key, a CSV header and a base64
attachment. Every occurrence must disappear from every release channel, while
common words and short ambiguous tokens must not be over-propagated.
"""

import base64
import hashlib
import json

from conftest import run_cli

NAME, SURNAME = "Orvila", "Tamsen"
MRN, PHONE = "TST/26/004417", "9876543210"


def build(root):
    files = {
        "reg/master.csv": "Hospital ID,Name of Patient,Contact#\n"
        f"{MRN},{NAME} {SURNAME},{PHONE}\nTST/26/004418,Kelvar Dunmore,9123456780\n",
        f"notes/DS_{NAME}_{SURNAME}_TST-26-004417.txt": f"Seen today. {NAME} ki halat theek hai. Om Sai.\n"
        "Asha workers visited. Rose water given. BP 120/80.\n",
        "opd/export.json": json.dumps(
            {
                "_meta": {"source_path": f"D:\\HIS\\{NAME}_{SURNAME}_004417\\v.json"},
                "by_patient": {f"{NAME} {SURNAME}": "TST/26/004417"},
                "visits": [{"visit_id": "V1", "notes": f"{NAME} ji ka BP 118/76"}],
            }
        ),
        "misc/grid.csv": f"time,TST/26/004417 {NAME}\n06:00,120/80\n",
        "forms/referral.json": json.dumps(
            {
                "attachment": {
                    "contentType": "text/plain",
                    "data": base64.b64encode(f"Referral for {NAME} {SURNAME}, mobile {PHONE}.".encode()).decode(),
                }
            }
        ),
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def all_release_text(out):
    chunks = []
    for p in out.rglob("*"):
        if p.is_file():
            chunks.append(p.relative_to(out).as_posix())
            t = p.read_text(encoding="utf-8")
            chunks.append(t)
            if p.suffix == ".json":
                for m in __import__("re").finditer(r"[A-Za-z0-9+/]{24,}={0,2}", t):
                    chunks.append(base64.b64decode(m.group() + "=" * (-len(m.group()) % 4)).decode("utf-8", "ignore"))
    return "\n".join(chunks)


def test_confirmed_values_vanish_from_every_channel(tmp_path):
    inp = tmp_path / "in"
    build(inp)
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    text = all_release_text(r.out) + r.stdout + r.stderr
    for value in (NAME, SURNAME, "004417", PHONE, "Kelvar", "Dunmore"):
        assert value not in text, value


def test_no_over_propagation_of_common_words(tmp_path):
    inp = tmp_path / "in"
    build(inp)
    out = run_cli(inp, tmp_path / "out").out
    note = next((out / "sanitized" / "notes").iterdir()).read_text(encoding="utf-8")
    for keep in ("Om Sai", "Asha workers", "Rose water", "BP 120/80", "ki halat theek hai"):
        assert keep in note, keep


def test_renamed_file_is_declared_by_hash_and_records_point_to_it(tmp_path):
    inp = tmp_path / "in"
    build(inp)
    out = run_cli(inp, tmp_path / "out").out
    src = inp / "notes" / f"DS_{NAME}_{SURNAME}_TST-26-004417.txt"
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    entry = next(e for e in rep["files"] if e["input_sha256"] == sha)
    assert entry["output"] == "sanitized/notes/DS_NAME_MRN.txt"
    assert (out / entry["output"]).is_file()
    recs = [json.loads(x) for x in (out / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    note_rec = next(r for r in recs if r["file"] == entry["output"] and r["loc"] == "doc")
    reg_rec = next(r for r in recs if r["file"] == "sanitized/reg/master.csv" and r["loc"] == "row:0")
    assert note_rec["patient"] is not None and note_rec["patient"] == reg_rec["patient"]


def test_report_entities_and_detection_summary_are_counts_only(tmp_path):
    inp = tmp_path / "in"
    build(inp)
    out = run_cli(inp, tmp_path / "out").out
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert sum(rep["entities"].values()) == rep["counts"]["identifiers_detected"] > 0
    summary = json.loads((out / "logs" / "detection_summary.json").read_text(encoding="utf-8"))
    assert summary["redactions_applied"] == rep["counts"]["identifiers_detected"]
    assert summary["files_renamed"] >= 1
    blob = json.dumps(summary) + json.dumps(rep)
    assert NAME not in blob and "004417" not in blob and PHONE not in blob


def test_headers_and_keys_keep_their_structure(tmp_path):
    inp = tmp_path / "in"
    build(inp)
    out = run_cli(inp, tmp_path / "out").out
    grid = (out / "sanitized/misc/grid.csv").read_text(encoding="utf-8").splitlines()
    assert grid[0].startswith("time,") and len(grid[0].split(",")) == 2 and grid[1] == "06:00,120/80"
    data = json.loads((out / "sanitized/opd/export.json").read_text(encoding="utf-8"))
    assert list(data) == ["_meta", "by_patient", "visits"] and data["visits"][0]["visit_id"] == "V1"
    header = (out / "sanitized/reg/master.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "Hospital ID,Name of Patient,Contact#"  # schema labels are never redacted
