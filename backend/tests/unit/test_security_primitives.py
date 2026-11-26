import pickle
from pathlib import Path

import pytest

from clinveil.ingestion.discovery import InputFile
from clinveil.models.findings import Action, Channel, EntityType, Finding, Method
from clinveil.security.errors import QuarantineError, safe_reason
from clinveil.security.paths import PathEscapeError, safe_join
from clinveil.security.secrets import MissingSecretError, ReleaseSecret


def test_secret_never_renders():
    s = ReleaseSecret(b"super-secret-value")
    for rendered in (repr(s), str(s), f"{s}", f"{s!r}", "%s" % s):  # noqa: UP031 - % formatting is one of the paths under test
        assert "super-secret-value" not in rendered
    with pytest.raises(TypeError):
        pickle.dumps(s)


def test_missing_or_empty_secret_is_rejected():
    with pytest.raises(MissingSecretError):
        ReleaseSecret.from_env({})
    with pytest.raises(MissingSecretError):
        ReleaseSecret.from_env({"RAKSHA_SECRET": ""})


def test_finding_repr_hides_surface():
    f = Finding(
        EntityType.PATIENT_NAME,
        Channel.CONTENT,
        "row:0",
        None,
        0.9,
        Method.LABEL,
        Action.REDACT,
        surface="Harendra Vexpal",
    )
    assert "Harendra" not in repr(f)
    with pytest.raises(ValueError):
        Finding(EntityType.PHONE, Channel.CONTENT, "doc", None, 1.5, Method.REGEX, Action.REDACT, surface="x")


def test_input_file_repr_hides_filename():
    f = InputFile(Path("/x/Discharge_Harendra_Vexpal.txt"), "Discharge_Harendra_Vexpal.txt", 10, False, False)
    assert "Harendra" not in repr(f)


def test_safe_reason_never_uses_messages():
    assert safe_reason(QuarantineError("empty_file")) == "empty_file"
    assert safe_reason(ValueError("Harendra")) == "ValueError"  # starter would have written "Harendra"
    with pytest.raises(ValueError):
        QuarantineError("Harendra")


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "a/../../b", ""])
def test_safe_join_rejects_escapes(tmp_path, bad):
    with pytest.raises(PathEscapeError):
        safe_join(tmp_path, bad)


def test_safe_join_rejects_symlinked_dir_escape(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscapeError):
        safe_join(root, "link/file.txt")
    assert safe_join(root, "a/b.txt") == root / "a" / "b.txt"
