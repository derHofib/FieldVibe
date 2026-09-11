import io

from PIL import Image, ImageDraw, ImageOps
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


def _compose_foto_plan_sync(foto_bytes: bytes, markierungen: list[dict], symbol_bytes_je_id: dict[str, bytes]) -> bytes:
    """Malt die gespeicherten Markierungen (Symbole + Leitungslinien, in
    relativen 0..1-Koordinaten wie im Frontend-Overlay, siehe
    FotoPlanBild.tsx) fest auf das Hintergrundfoto -- fuer den PDF-Export
    gibt es dort keinen SVG-Overlay, nur ein flaches Bild pro Feld."""
    basis = ImageOps.exif_transpose(Image.open(io.BytesIO(foto_bytes))).convert("RGBA")
    breite, hoehe = basis.size

    zeichnung = ImageDraw.Draw(basis)
    for m in markierungen:
        if m.get("art") != "linie":
            continue
        punkte = [(p["x"] * breite, p["y"] * hoehe) for p in m.get("punkte", [])]
        if len(punkte) >= 2:
            zeichnung.line(punkte, fill=m.get("farbe") or "#dc2626", width=max(2, breite // 300))

    symbol_groesse = max(24, int(breite * 0.06))
    for m in markierungen:
        if m.get("art") != "symbol":
            continue
        symbol_bytes = symbol_bytes_je_id.get(m.get("symbol_id"))
        if not symbol_bytes:
            continue
        symbol = Image.open(io.BytesIO(symbol_bytes)).convert("RGBA")
        symbol.thumbnail((symbol_groesse, symbol_groesse))
        winkel = m.get("winkel") or 0
        if winkel:
            # CSS rotate() dreht im Uhrzeigersinn, Image.rotate() gegen den
            # Uhrzeigersinn -- Vorzeichen umkehren, damit das PDF dieselbe
            # Ausrichtung wie die Erfassung/Summary-Ansicht zeigt.
            symbol = symbol.rotate(-winkel, expand=True, resample=Image.BICUBIC)
        x = int(m.get("x", 0) * breite - symbol.width / 2)
        y = int(m.get("y", 0) * hoehe - symbol.height / 2)
        basis.paste(symbol, (x, y), symbol)

    buffer = io.BytesIO()
    basis.convert("RGB").save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


async def compose_foto_plan_bild(foto_bytes: bytes, markierungen: list[dict], symbol_bytes_je_id: dict[str, bytes]) -> bytes:
    return await run_in_threadpool(_compose_foto_plan_sync, foto_bytes, markierungen, symbol_bytes_je_id)
