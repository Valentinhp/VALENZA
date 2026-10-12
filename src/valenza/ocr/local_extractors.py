from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess


def fingerprint_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_pdf_text(path: Path) -> str:
    """Extrae texto nativo localmente; no ejecuta contenido del PDF."""
    try:
        import pymupdf
    except ImportError as error:
        raise RuntimeError(
            "PyMuPDF no esta instalado; instala la dependencia opcional .[ocr]"
        ) from error

    try:
        document = pymupdf.open(path)
        try:
            if document.needs_pass:
                raise ValueError('El PDF está protegido con contraseña; abre una copia sin protección para importarlo.')
            if not len(document):
                raise ValueError('El PDF no contiene páginas.')
            return "\n".join(page.get_text() for page in document)
        finally:
            document.close()
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"No se pudo leer el PDF local: {path.name}") from error


def run_tesseract(image_path: Path, *, executable: str = "tesseract") -> str:
    """Ejecuta Tesseract local; nunca realiza una solicitud de red."""
    resolved = str(Path(executable)) if Path(executable).is_file() else shutil.which(executable)
    if resolved is None:
        raise RuntimeError(
            "Tesseract no esta disponible en PATH; configure un ejecutable local"
        )
    try:
        completed = subprocess.run(
            [resolved, str(image_path), "stdout", "--dpi", "300"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Tesseract fallo durante la extraccion local") from error
    return completed.stdout


def read_image_text(image_path: Path, *, executable: str = "tesseract") -> str:
    """Extrae texto de una imagen mediante el binario Tesseract local."""
    if image_path.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        raise RuntimeError(f"Formato de imagen no soportado: {image_path.suffix}")
    if not image_path.is_file():
        raise RuntimeError(f"No existe la imagen local: {image_path}")
    return run_tesseract(image_path, executable=executable)
