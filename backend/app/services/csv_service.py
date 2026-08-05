import csv
import io

from fastapi import Response


def csv_response(header: list[str], rows: list[list], filename: str) -> Response:
    """Baut eine CSV-Download-Antwort -- Semikolon statt Komma als Trenner,
    weil das deutsche Excel beim CSV-Import genau das erwartet (Komma ist
    dort das Dezimaltrennzeichen). utf-8-sig (mit BOM) statt reinem utf-8,
    damit Excel unter Windows Umlaute automatisch korrekt erkennt statt sie
    als Mojibake darzustellen."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
