import io

from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

# "Reduzierte Aufloesung" (Abschnitt 6) is generated server-side once on
# upload rather than left to the client, so every consumer (Feed-Thumbnail,
# Offline-Cache in der PWA) gets the same small file instead of each
# re-deriving it from the full-resolution original.
THUMBNAIL_MAX_DIMENSION = 800
THUMBNAIL_QUALITY = 80


def _make_thumbnail_sync(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data))
    # Handyfotos speichern Hochkant-Aufnahmen haeufig als physisch
    # querformatige Pixel mit einem EXIF-Orientation-Tag statt gedrehter
    # Pixel -- ohne exif_transpose() uebernimmt Pillow die Pixel 1:1 und das
    # Tag geht beim Neuspeichern verloren, das Thumbnail landet dauerhaft im
    # falschen Seitenverhaeltnis.
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((THUMBNAIL_MAX_DIMENSION, THUMBNAIL_MAX_DIMENSION))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=THUMBNAIL_QUALITY)
    return buffer.getvalue()


async def make_thumbnail(data: bytes) -> bytes:
    return await run_in_threadpool(_make_thumbnail_sync, data)
