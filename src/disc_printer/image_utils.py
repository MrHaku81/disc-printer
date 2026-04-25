import io
from pathlib import Path

import cairo
from gi.repository import GdkPixbuf

from ._log import log
from .constants import _PRINT_SAT, _PRINT_CONTRAST

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def pixbuf_to_cairo(pixbuf: GdkPixbuf.Pixbuf) -> cairo.ImageSurface:
    ok, buf = pixbuf.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError("Pixbuf-PNG-Encodierung fehlgeschlagen")
    return cairo.ImageSurface.create_from_png(io.BytesIO(buf))


def is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"
    }


def boost_cairo_surface(surf: cairo.ImageSurface) -> cairo.ImageSurface:
    """Sättigungs- und Kontrast-geboostete Kopie von surf für den Druck."""
    if not _HAS_NUMPY:
        log.warning("numpy nicht verfügbar – Farbboost übersprungen")
        return surf
    w, h   = surf.get_width(), surf.get_height()
    stride = surf.get_stride()
    if stride != w * 4:
        log.warning(
            f"Unerwarteter Cairo-Stride {stride} != {w * 4} – Farbboost übersprungen"
        )
        return surf
    # Cairo FORMAT_RGB24 (little-endian): Byte-Reihenfolge pro Pixel ist B G R X
    arr = np.frombuffer(surf.get_data(), dtype=np.uint8).reshape(h, w, 4).copy()
    f   = arr[:, :, :3].astype(np.float32) / 255.0
    lum = (0.0722 * f[:, :, 0]   # B  \
         + 0.7152 * f[:, :, 1]   # G   > BT.709 Luminanz
         + 0.2126 * f[:, :, 2])  # R  /
    lum = lum[:, :, np.newaxis]
    f   = lum + (f - lum) * _PRINT_SAT
    f   = (f - 0.5) * _PRINT_CONTRAST + 0.5
    np.clip(f, 0.0, 1.0, out=f)
    arr[:, :, :3] = (f * 255.0).astype(np.uint8)
    tmp = cairo.ImageSurface.create_for_data(arr, surf.get_format(), w, h)
    out = cairo.ImageSurface(surf.get_format(), w, h)
    ctx = cairo.Context(out)
    ctx.set_source_surface(tmp, 0, 0)
    ctx.paint()
    return out


def write_print_png(surf: cairo.ImageSurface, path: str) -> None:
    """Speichert die Druckfläche als verlustfreies PNG.

    Mit Pillow + numpy: sRGB-ICC-Profil eingebettet, niedrige PNG-Kompression.
    Fallback: Cairo write_to_png.
    """
    if _HAS_PIL and _HAS_NUMPY:
        try:
            from PIL import ImageCms
            w, h = surf.get_width(), surf.get_height()
            arr  = np.frombuffer(surf.get_data(), dtype=np.uint8).reshape(h, w, 4)
            rgb  = arr[:, :, [2, 1, 0]].copy()   # BGRX → RGB
            img  = _PILImage.fromarray(rgb, "RGB")
            icc  = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            img.save(path, format="PNG", icc_profile=icc, compress_level=1)
            log.info(f"PNG mit sRGB-Profil gespeichert (Pillow): {path}")
            return
        except Exception as e:
            log.warning(f"Pillow-PNG-Export fehlgeschlagen: {e} – Fallback zu Cairo")
    surf.write_to_png(path)
    log.info(f"PNG gespeichert (Cairo, lossless): {path}")
