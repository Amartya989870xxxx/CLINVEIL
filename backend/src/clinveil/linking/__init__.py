"""Cross-document patient identity resolution.

Target design (Phase 3): normalise evidence (names in both scripts, phones,
UHID/IPD digit cores, Aadhaar, ABHA, DOB, relative, village, age), block on strong
keys, score pairs with explicit evidence weights, and cluster *conservatively*:
strong-identifier edges merge; weak name-only edges never chain transitively;
conflicting strong evidence (different DOB/Aadhaar) vetoes a merge. Ambiguous
records stay ``null``, because a false merge costs more than a missed link (F0.5).
"""
