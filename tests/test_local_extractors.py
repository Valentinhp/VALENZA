from pathlib import Path

from valenza.ocr.local_extractors import fingerprint_file


def test_fingerprint_is_stable_and_does_not_expose_filename(tmp_path: Path):
    document = tmp_path / "private-document.png"
    document.write_bytes(b"synthetic fixture")
    fingerprint = fingerprint_file(document)
    assert len(fingerprint) == 64
    assert "private-document" not in fingerprint
