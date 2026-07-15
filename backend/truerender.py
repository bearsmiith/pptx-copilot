"""Fidelity check: render the real .pptx to PNGs via LibreOffice headless.

This is the 'B' half of the hybrid approach — the browser SVG is fast but
approximate; this shows what the actual PowerPoint file looks like.
Degrades gracefully if LibreOffice is not installed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def libreoffice_bin() -> str | None:
    for name in ("libreoffice", "soffice"):
        p = shutil.which(name)
        if p:
            return p
    return None


def pptx_to_pngs(pptx_bytes: bytes) -> list[bytes]:
    """Return one PNG per slide. Raises RuntimeError if LibreOffice missing."""
    bin_ = libreoffice_bin()
    if not bin_:
        raise RuntimeError("LibreOffice not installed")

    with tempfile.TemporaryDirectory() as d:
        pptx_path = os.path.join(d, "deck.pptx")
        with open(pptx_path, "wb") as f:
            f.write(pptx_bytes)
        # pptx -> pdf, then pdf -> png pages (most reliable multi-slide path)
        subprocess.run(
            [bin_, "--headless", "--convert-to", "pdf", "--outdir", d, pptx_path],
            check=True, capture_output=True, timeout=120,
        )
        pdf_path = os.path.join(d, "deck.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("LibreOffice failed to produce PDF")
        if not shutil.which("pdftoppm"):
            # return the PDF bytes flagged by caller if no rasterizer
            raise RuntimeError("pdftoppm (poppler-utils) not installed")
        subprocess.run(
            ["pdftoppm", "-png", "-r", "110", pdf_path, os.path.join(d, "slide")],
            check=True, capture_output=True, timeout=120,
        )
        pngs = sorted(f for f in os.listdir(d) if f.endswith(".png"))
        return [open(os.path.join(d, p), "rb").read() for p in pngs]
