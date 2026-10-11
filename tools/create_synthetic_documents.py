from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures_synthetic"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def make_image(filename: str, lines: list[str]) -> Path:
    image = Image.new("RGB", (1800, 1100), "white")
    draw = ImageDraw.Draw(image)
    y = 70
    for line in lines:
        draw.text((80, y), line, fill="black", font=font(48))
        y += 105
    path = OUTPUT / filename
    image.save(path, quality=95)
    return path


def make_pdf(filename: str, lines: list[str]) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    y = 80
    for line in lines:
        page.insert_text((60, y), line, fontsize=20, color=(0, 0, 0))
        y += 42
    path = OUTPUT / filename
    document.save(path)
    document.close()
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    mp_lines = [
        "Mercado Pago - Comprobante de pago",
        "03/10/2026 19:41",
        "Producto sintetico - 1 unidad",
        "Total $129.99",
        "Medio de pago: Dinero en Mercado Pago",
    ]
    nu_lines = [
        "NU - Resumen de transacciones",
        "Tus gastos actuales en la tarjeta $6,587.41",
        "08/10/2026 CFE $100.00",
        "08/10/2026 CFE $100.00",
        "08/10/2026 CFE $100.00",
        "09/10/2026 Compra sintetica -$21.30",
        "Captura parcial - revisar antes de confirmar",
    ]
    make_image("mercado_pago_receipt.png", mp_lines)
    make_image("nu_transactions.jpg", nu_lines)
    make_pdf("mercado_pago_receipt.pdf", mp_lines)
    make_pdf("nu_transactions.pdf", nu_lines)


if __name__ == "__main__":
    main()
