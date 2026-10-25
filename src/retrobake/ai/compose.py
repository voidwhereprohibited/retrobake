"""Turn validated AI image bytes into RetroBake cover art.

Steps: security.validate_image (header, size) -> decode with Qt's QImage (a decode failure is
OutputRejected) -> centre-crop to the box shape -> shrink + chunky upscale + posterize for a retro
look -> our own PNG. Re-encoding drops all metadata the AI service embedded (it puts the prompt in
EXIF). Qt is only used to decode; it needs no QApplication.
"""

from __future__ import annotations

from retrobake.security import OutputRejected, validate_image

from .raster import Canvas

CHUNK = 4  # AI art keeps more detail than offline art: 4x4 "retro pixels"


def decode_art(data: bytes, width: int, height: int) -> Canvas:
    """Validated, re-encoded art at exactly ``width`` x ``height``. Raises OutputRejected."""
    validate_image(data)
    try:
        from PySide6.QtCore import QByteArray, Qt
        from PySide6.QtGui import QImage
    except ImportError as exc:  # pragma: no cover - PySide6 is a hard dependency
        raise OutputRejected("image decoder unavailable") from exc

    img = QImage()
    if not img.loadFromData(QByteArray(bytes(data))) or img.isNull():
        raise OutputRejected("image could not be decoded")
    iw, ih = img.width(), img.height()
    target = width / height
    if iw / ih > target:
        cw, ch = int(ih * target), ih
    else:
        cw, ch = iw, int(iw / target)
    img = img.copy((iw - cw) // 2, (ih - ch) // 2, cw, ch)
    small = img.scaled(
        width // CHUNK,
        height // CHUNK,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    small = small.convertToFormat(QImage.Format.Format_RGB888)
    sw, sh, bpl = small.width(), small.height(), small.bytesPerLine()
    raw = bytes(small.constBits())
    rows = b"".join(raw[y * bpl : y * bpl + sw * 3] for y in range(sh))
    canvas = Canvas.from_rgb(sw, sh, rows)
    canvas.posterize(4)
    return canvas.scaled(CHUNK)
