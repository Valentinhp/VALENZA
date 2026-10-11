from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures_synthetic"
TESSERACT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def measure(label: str, code: str) -> dict[str, float | str]:
    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    monitor = psutil.Process(process.pid)
    peak_rss = 0
    while process.poll() is None:
        try:
            peak_rss = max(peak_rss, monitor.memory_info().rss)
        except psutil.Error:
            break
        time.sleep(0.01)
    stdout, stderr = process.communicate()
    elapsed_ms = (time.perf_counter() - started) * 1000
    if process.returncode != 0:
        raise RuntimeError(f"{label} fallo: {stderr.strip()}")
    return {
        "case": label,
        "elapsed_ms": round(elapsed_ms, 2),
        "peak_rss_mb": round(peak_rss / 1024 / 1024, 2),
        "output_chars": len(stdout),
    }


def main() -> None:
    cases = [
        (
            "pdf_native_mp",
            "from pathlib import Path; "
            "from sgccc.ocr.local_extractors import read_pdf_text; "
            f"print(len(read_pdf_text(Path(r'{FIXTURES / 'mercado_pago_receipt.pdf'}'))))",
        ),
        (
            "png_ocr_mp",
            "from pathlib import Path; "
            "from sgccc.ocr.local_extractors import read_image_text; "
            f"print(len(read_image_text(Path(r'{FIXTURES / 'mercado_pago_receipt.png'}'), "
            f"executable=r'{TESSERACT}')))",
        ),
        (
            "jpeg_ocr_nu",
            "from pathlib import Path; "
            "from sgccc.ocr.local_extractors import read_image_text; "
            f"print(len(read_image_text(Path(r'{FIXTURES / 'nu_transactions.jpg'}'), "
            f"executable=r'{TESSERACT}')))",
        ),
    ]
    print(json.dumps([measure(label, code) for label, code in cases], indent=2))


if __name__ == "__main__":
    main()
