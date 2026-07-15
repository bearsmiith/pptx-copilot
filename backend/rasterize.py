"""Rasterize an SVG string to PNG via headless Chrome.

Used to turn a generated diagram (our own SVG) into an image asset for the
slide composer (python-pptx cannot embed SVG). Not a hot path — called once
per diagram at attach time.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid

CHROME = (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
          or "/usr/bin/google-chrome")


def svg_to_png(svg: str, out_path: str, width: int = 1280, height: int = 720):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(f'<!doctype html><html><body style="margin:0">{svg}</body></html>')
        html = f.name
    udir = os.path.join(tempfile.gettempdir(), "chrome-" + uuid.uuid4().hex[:8])
    try:
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
             f"--user-data-dir={udir}", f"--screenshot={out_path}",
             f"--window-size={width},{height}", "--hide-scrollbars",
             # let foreignObject labels/shapes finish painting before capture
             "--virtual-time-budget=4000", "--run-all-compositor-stages-before-draw",
             f"file://{html}"],
            check=True, capture_output=True, timeout=60)
    finally:
        try:
            os.unlink(html)
        except OSError:
            pass
        shutil.rmtree(udir, ignore_errors=True)
    return width, height
