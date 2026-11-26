"""Generalisation to unseen-style data: renamed headers, invented names, new ID/phone formats,
PII moved into alternate channels (see ``synth.py``). Runs the real CLI end to end."""

import pytest
from synth import evaluate, generate

from conftest import run_cli


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_unseen_style_dataset_leaks_nothing_and_keeps_clinical_values(tmp_path, seed):
    files, truth = generate(seed)
    inp = tmp_path / "in"
    for rel, data in files.items():
        (inp / rel).parent.mkdir(parents=True, exist_ok=True)
        (inp / rel).write_bytes(data)
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    res = evaluate(tmp_path / "out", truth)
    assert res["pii_leaked"] == 0, res["leaked_kinds"]
    assert res["clinical_kept"] == res["clinical_total"]


def test_generator_is_deterministic_and_avoids_gazetteer_names():
    from clinveil.detection.lexicon import GIVEN_NAMES, SURNAMES

    a, b = generate(7), generate(7)
    assert a[0] == b[0]
    names = [v.lower() for k, v in a[1].pii if k == "name" and v.isascii()]
    assert names and not set(names) & (GIVEN_NAMES | SURNAMES)
