import csv
import io
import re

from fastapi import Response


_FORMEL_ANFAENGE = ("=", "+", "-", "@", "\t", "\r")


def formel_sicher(wert):
    """Schuetzt vor CSV-/Formel-Injection: Excel wertet Zellen, die mit = + - @ beginnen,
    als Formel aus. Ein vorangestelltes Apostroph macht sie zu Text."""
    if isinstance(wert, str) and wert.startswith(_FORMEL_ANFAENGE):
        return "'" + wert
    return wert


# Reine Zahlen (auch deutsch formatiert, auch negativ) sind keine Formel und
# muessen Zahlen bleiben -- die Exporte reichen Betraege als Text durch.
_ZAHL = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?)$")


def _zelle_schuetzen(wert):
    if isinstance(wert, str) and _ZAHL.match(wert):
        return wert
    return formel_sicher(wert)


def csv_bytes(header: list[str], rows: list[list], *, formelschutz: bool = False) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    schutz = formel_sicher if formelschutz else (lambda wert: wert)
    writer.writerow([schutz(h) for h in header])
    writer.writerows([[schutz(z) for z in zeile] for zeile in rows])
    return buffer.getvalue().encode("utf-8-sig")


def csv_response(header: list[str], rows: list[list], filename: str) -> Response:
    """Baut eine CSV-Download-Antwort -- Semikolon statt Komma als Trenner,
    weil das deutsche Excel beim CSV-Import genau das erwartet (Komma ist
    dort das Dezimaltrennzeichen). utf-8-sig (mit BOM) statt reinem utf-8,
    damit Excel unter Windows Umlaute automatisch korrekt erkennt statt sie
    als Mojibake darzustellen. Textzellen laufen durch den Formelschutz."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([_zelle_schuetzen(h) for h in header])
    writer.writerows([[_zelle_schuetzen(z) for z in zeile] for zeile in rows])
    content = buffer.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
