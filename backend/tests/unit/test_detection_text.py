"""Unicode handling, offsets, scripts and cross-script name keys (synthetic strings only)."""

import pytest

from clinveil.detection.text import digits_only, language_of, normalize_token, script_of, tokenize
from clinveil.detection.translit import name_key, romanize


def test_token_offsets_index_the_original_string():
    text = "नाम: वसुधा  Mob ९८७६५"
    for t in tokenize(text):
        assert text[t.start : t.end] == t.text


def test_devanagari_word_with_matras_viramas_and_nukta_is_one_token():
    (t,) = tokenize("सिद्दीक़ी")
    assert t.text == "सिद्दीक़ी"


def test_precomposed_and_decomposed_nukta_share_a_key_but_keep_their_own_offsets():
    precomposed = "\u0958ासिम"  # क़ as one code point
    decomposed = "\u0915\u093cासिम"  # क + nukta
    assert len(decomposed) == len(precomposed) + 1
    (a,), (b,) = tokenize(precomposed), tokenize(decomposed)
    assert a.key == b.key == normalize_token("कासिम")
    assert (b.start, b.end) == (0, len(decomposed))


def test_zero_width_characters():
    assert [t.key for t in tokenize("Vasu\u200bdha")] == ["vasu", "dha"]  # ZWSP separates
    (t,) = tokenize("वसु\u200dधा")  # ZWJ stays inside a Devanagari word …
    assert t.key == normalize_token("वसुधा")  # … but is ignored for matching


def test_devanagari_digits_normalise_in_keys():
    (t,) = tokenize("९८७६५४३२१०")
    assert t.key == "9876543210"
    assert digits_only("मो. ९८७६५-४३२१०") == "9876543210"


@pytest.mark.parametrize(
    "a, b",
    [
        ("Mohammad", "मोहम्मद"),
        ("Md", "Mohd"),
        ("Mohammed", "Muhammad"),
        ("Seeta", "Sita"),
        ("Seeta", "सीता"),
        ("Lakshmi", "Laxmi"),
        ("Tripathi", "Tripathy"),
        ("Tripathi", "त्रिपाठी"),
        ("Farooqui", "फ़ारूक़ी"),
        ("Rehana", "Rihana"),
        ("Deepa", "Dipa"),
    ],
)
def test_spelling_and_script_variants_share_a_name_key(a, b):
    assert name_key(a) == name_key(b)


@pytest.mark.parametrize("a, b", [("Rakesh", "Raghav"), ("Seeta", "Lakshmi"), ("Tripathi", "Farooqui")])
def test_distinct_names_keep_distinct_keys(a, b):
    assert name_key(a) != name_key(b)


def test_romanize_approximates_devanagari():
    assert romanize("मोहम्मद") == "mohammad"
    assert romanize("सीता") == "seetaa"


@pytest.mark.parametrize(
    "text, script, lang",
    [
        ("Patient is stable", "latin", "latin"),
        ("Patient ko fever hai aur kal se bukhar", "latin", "hinglish"),
        ("मरीज़ को बुखार है", "deva", "deva"),
        ("दवा BD x 5 days", "mixed", "deva"),
        ("120/80", "none", "none"),
    ],
)
def test_script_and_language_cues(text, script, lang):
    assert script_of(text) == script
    assert language_of(text) == lang
