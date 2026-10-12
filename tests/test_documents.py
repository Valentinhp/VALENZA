from pathlib import Path

import pytest
from PIL import Image

from valenza.ocr.local_extractors import read_image_text, read_pdf_text
from valenza.ocr.models import DocumentKind, MovementKind
from valenza.ocr.pipeline import analyze_text


FIXTURES = Path(__file__).parent / "fixtures_synthetic"
TESSERACT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def test_digital_pdf_extraction_is_local_and_proposed():
    text = read_pdf_text(FIXTURES / "mercado_pago_receipt.pdf")
    result = analyze_text(text, source_platform="mercado_pago", source_kind="pdf_native")
    assert result.document_type is DocumentKind.MP_RECEIPT
    assert result.movements[0].amount_cents == 12999
    assert result.movements[0].movement_type is MovementKind.CHARGE
    assert result.movements[0].status == "proposed"


def test_ocr_png_extracts_synthetic_wallet_receipt():
    if not TESSERACT.is_file():
        pytest.skip("Tesseract no esta instalado en la ruta esperada")
    text = read_image_text(
        FIXTURES / "mercado_pago_receipt.png",
        executable=str(TESSERACT),
    )
    result = analyze_text(text, source_platform="mercado_pago", source_kind="image_ocr")
    assert result.movements[0].amount_cents == 12999
    assert result.movements[0].payment_instrument == "WALLET_BALANCE"
    assert result.review_status == "proposed"


def test_ocr_jpeg_preserves_repeated_charges():
    if not TESSERACT.is_file():
        pytest.skip("Tesseract no esta instalado en la ruta esperada")
    text = read_image_text(
        FIXTURES / "nu_transactions.jpg",
        executable=str(TESSERACT),
    )
    result = analyze_text(text, source_platform="nu", source_kind="image_ocr")
    repeated = [
        movement
        for movement in result.movements
        if movement.amount_cents == 10000
    ]
    assert len(repeated) == 3
    assert all(movement.status == "proposed" for movement in result.movements)


def test_corrupt_pdf_reports_local_read_error(tmp_path: Path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a PDF")
    with pytest.raises(RuntimeError, match="No se pudo leer"):
        read_pdf_text(broken)


def test_unreadable_image_reports_missing_file(tmp_path: Path):
    with pytest.raises(RuntimeError, match="No existe"):
        read_image_text(tmp_path / "missing.png", executable=str(TESSERACT))


def test_unsupported_image_extension_is_rejected(tmp_path: Path):
    path = tmp_path / "document.txt"
    path.write_text("synthetic", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Formato"):
        read_image_text(path, executable=str(TESSERACT))


def test_blank_image_is_unclassified_and_remains_proposed(tmp_path: Path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (800, 400), "white").save(blank)
    if not TESSERACT.is_file():
        pytest.skip("Tesseract no esta instalado en la ruta esperada")
    text = read_image_text(blank, executable=str(TESSERACT))
    result = analyze_text(text, source_platform="unknown", source_kind="image_ocr")
    assert result.document_type is DocumentKind.UNKNOWN
    assert result.review_status == "proposed"


def test_missing_tesseract_reports_configuration_error(tmp_path: Path):
    image = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "white").save(image)
    with pytest.raises(RuntimeError, match="Tesseract no esta disponible"):
        read_image_text(image, executable="C:/missing/tesseract.exe")
