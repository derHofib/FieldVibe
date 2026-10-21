import hashlib
import uuid
from datetime import date, datetime, time, timedelta, timezone

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

_settings = get_settings()

_BOTO_CONFIG = BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"})


def _make_client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=_settings.s3_access_key,
        aws_secret_access_key=_settings.s3_secret_key,
        region_name=_settings.s3_region,
        config=_BOTO_CONFIG,
    )


# Two clients against the same MinIO instance, deliberately configured with
# different hosts: _internal_client talks to the Docker-network hostname
# ("minio") for server-side PUT/HEAD calls, _public_client signs URLs
# against whatever host the *browser* can actually reach (localhost in
# dev, the real domain behind Caddy once deployed per Abschnitt 15) --
# presigned URLs are worthless if signed for a hostname only the backend
# container can resolve.
_internal_client = _make_client(_settings.s3_endpoint_url)
_public_client = _make_client(_settings.s3_public_url_base)

BUCKET = _settings.s3_bucket_fotos


async def ensure_bucket() -> None:
    def _ensure() -> None:
        try:
            _internal_client.head_bucket(Bucket=BUCKET)
        except ClientError:
            # Object Lock laesst sich nur beim Anlegen des Buckets einschalten
            # (das aktiviert zugleich die Versionierung). Ein bestehender Bucket
            # bleibt unveraendert -- siehe docs/gobd/OBJECT_LOCK.md.
            if _settings.s3_object_lock:
                _internal_client.create_bucket(Bucket=BUCKET, ObjectLockEnabledForBucket=True)
            else:
                _internal_client.create_bucket(Bucket=BUCKET)

    await run_in_threadpool(_ensure)


def mandant_prefix(mandant_id: uuid.UUID) -> str:
    return f"mandanten/{mandant_id}/"


def key_gehoert_zu_mandant(key: str, mandant_id: uuid.UUID) -> bool | None:
    """True/False fuer Schluessel im Mandanten-Schema (mandanten/<id>/...). None bei
    Altobjekten (vorgaenge/<id>/..., rechnungen/<id>/... ohne Mandantenpraefix): deren
    Zuordnung steht nur in der Datenbank (unter RLS), nicht im Schluessel. Altobjekte
    werden bewusst nicht umgezogen."""
    if key.startswith("mandanten/"):
        return key.startswith(mandant_prefix(mandant_id))
    return None


def _endung(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"


def new_object_key(mandant_id: uuid.UUID, vorgang_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}vorgaenge/{vorgang_id}/{uuid.uuid4()}.{_endung(filename)}"


def new_kunde_logo_key(mandant_id: uuid.UUID, kunde_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}kunden/{kunde_id}/logo/{uuid.uuid4()}.{_endung(filename)}"


def new_mandant_logo_key(mandant_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}logo/{uuid.uuid4()}.{_endung(filename)}"


def new_board_hintergrund_key(mandant_id: uuid.UUID, board_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}boards/{board_id}/hintergrund/{uuid.uuid4()}.{_endung(filename)}"


def new_board_anhang_key(mandant_id: uuid.UUID, board_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}boards/{board_id}/anhang/{uuid.uuid4()}.{_endung(filename)}"


def new_rechnung_pdf_key(mandant_id: uuid.UUID, rechnung_id: uuid.UUID) -> str:
    return f"{mandant_prefix(mandant_id)}rechnungen/{rechnung_id}/versendet-{uuid.uuid4()}.pdf"


def new_rechnung_xml_key(mandant_id: uuid.UUID, rechnung_id: uuid.UUID) -> str:
    return f"{mandant_prefix(mandant_id)}rechnungen/{rechnung_id}/versendet-{uuid.uuid4()}.xml"


def new_eingangsrechnung_beleg_key(mandant_id: uuid.UUID, eingangsrechnung_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}eingangsrechnungen/{eingangsrechnung_id}/beleg/{uuid.uuid4()}.{_endung(filename)}"


def new_eingangsrechnung_xml_key(mandant_id: uuid.UUID, eingangsrechnung_id: uuid.UUID) -> str:
    return f"{mandant_prefix(mandant_id)}eingangsrechnungen/{eingangsrechnung_id}/xml/{uuid.uuid4()}.xml"


def new_mail_attachment_key(mandant_id: uuid.UUID, message_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}mail-nachrichten/{message_id}/{uuid.uuid4()}.{_endung(filename)}"


def new_dsgvo_dokument_key(typ: str, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"dsgvo/{typ}/{uuid.uuid4()}.{suffix}"


def new_partner_nachweis_key(mandant_id: uuid.UUID, partner_id: uuid.UUID, filename: str) -> str:
    return f"{mandant_prefix(mandant_id)}partner-nachweise/{partner_id}/{uuid.uuid4()}.{_endung(filename)}"


def new_plan_symbol_key(mandant_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"mandanten/{mandant_id}/plan-symbole/{uuid.uuid4()}.{suffix}"


def new_fehlerbericht_screenshot_key(mandant_id: uuid.UUID, bericht_id: uuid.UUID, art: str) -> str:
    return f"mandanten/{mandant_id}/fehlerberichte/{bericht_id}/{art}-{uuid.uuid4()}"


def new_import_quelle_key(mandant_id: uuid.UUID, lauf_id: uuid.UUID) -> str:
    # Bewusst ohne Dateiname/Endung: der Name stammt vom Nutzer und darf nie Teil des Keys werden.
    return f"mandanten/{mandant_id}/datenimport/{lauf_id}/quelle-{uuid.uuid4()}.bin"


def new_import_fehlerbericht_key(mandant_id: uuid.UUID, lauf_id: uuid.UUID) -> str:
    return f"mandanten/{mandant_id}/datenimport/{lauf_id}/fehlerbericht-{uuid.uuid4()}.csv"


async def upload_bytes(
    key: str, data: bytes, content_type: str, *, aufbewahren_bis: date | None = None
) -> None:
    # SSE-S3 (serverseitig, MinIO-verwalteter Schluessel) verschluesselt
    # Kundenfotos/Unterschriften/Rechnungs-PDFs/Belege "at rest" auf der
    # Festplatte. Braucht trotzdem einen statischen Master-Key auf MinIO-
    # Seite (MINIO_KMS_SECRET_KEY, siehe .env.example/docker-compose.yml) --
    # ohne den lehnt MinIO JEDEN Upload mit "KMS is not configured" ab.
    zusatz: dict = {}
    modus = _settings.s3_rechnungen_retention
    if aufbewahren_bis is not None and modus != "off":
        # Objekt-Aufbewahrung (WORM) bis Ende des Fristtags; nur mit Object-Lock-Bucket moeglich.
        zusatz = {
            "ObjectLockMode": modus.upper(),
            "ObjectLockRetainUntilDate": datetime.combine(
                aufbewahren_bis + timedelta(days=1), time.min, tzinfo=timezone.utc
            ),
        }
    await run_in_threadpool(
        _internal_client.put_object,
        Bucket=BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
        **zusatz,
    )


async def upload_file(key: str, fileobj, content_type: str) -> None:
    """Grosse Dateien (Export-ZIP): Multipart-Upload aus einer Datei, ohne sie in den Speicher zu laden."""
    await run_in_threadpool(
        _internal_client.upload_fileobj,
        fileobj,
        BUCKET,
        key,
        ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
    )


async def download_bytes(key: str) -> bytes:
    def _get() -> bytes:
        obj = _internal_client.get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read()

    return await run_in_threadpool(_get)


def _sha256_stream(key: str) -> str:
    obj = _internal_client.get_object(Bucket=BUCKET, Key=key)
    digest = hashlib.sha256()
    for chunk in obj["Body"].iter_chunks(chunk_size=1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


async def sha256_object(key: str) -> str:
    """SHA-256 eines Objekts, gestreamt (kein Komplett-Download in den Speicher)."""
    return await run_in_threadpool(_sha256_stream, key)


async def delete_object(key: str) -> None:
    await run_in_threadpool(_internal_client.delete_object, Bucket=BUCKET, Key=key)


def _loesche_ziele(ziele: list[dict]) -> None:
    for i in range(0, len(ziele), 1000):
        antwort = _internal_client.delete_objects(Bucket=BUCKET, Delete={"Objects": ziele[i : i + 1000], "Quiet": True})
        if antwort.get("Errors"):
            erster = antwort["Errors"][0]
            raise RuntimeError(f"{len(antwort['Errors'])} Objekt(e) nicht geloescht: {erster.get('Code')} {erster.get('Key')}")


def _delete_prefix(prefix: str) -> int:
    # Versionen und Loeschmarker einzeln entfernen: in einem versionierten (Object-Lock-)Bucket legt
    # ein einfaches DELETE nur einen Marker an, das Objekt bliebe liegen.
    anzahl = 0
    try:
        paginator = _internal_client.get_paginator("list_object_versions")
        for seite in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            ziele = []
            for eintrag in [*seite.get("Versions", []), *seite.get("DeleteMarkers", [])]:
                ziel = {"Key": eintrag["Key"]}
                if eintrag.get("VersionId") not in (None, "null"):
                    ziel["VersionId"] = eintrag["VersionId"]
                ziele.append(ziel)
            _loesche_ziele(ziele)
            anzahl += len(ziele)
        return anzahl
    except ClientError as exc:
        # Aeltere Service-Accounts duerfen Versionen nicht auflisten (nur ListBucket/DeleteObject, siehe
        # scripts/minio-service-account.sh): dann gilt der unversionierte Weg.
        if exc.response.get("Error", {}).get("Code") not in ("AccessDenied", "NotImplemented"):
            raise
    anzahl = 0
    for seite in _internal_client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        ziele = [{"Key": o["Key"]} for o in seite.get("Contents", [])]
        _loesche_ziele(ziele)
        anzahl += len(ziele)
    return anzahl


async def delete_prefix(prefix: str) -> int:
    """Loescht alle Objekte unterhalb von prefix. Verweigert zu allgemeine Praefixe
    (mindestens zwei Pfadebenen, Schraegstrich am Ende): ein Fehler in der
    Praefixbildung darf nie einen ganzen Bereich leeren."""
    if not prefix.endswith("/") or prefix.count("/") < 2 or prefix.startswith("/"):
        raise ValueError(f"Unzulaessiger Praefix fuer das Loeschen: {prefix!r}")
    return await run_in_threadpool(_delete_prefix, prefix)


def presigned_get_url(key: str, expires_seconds: int = 3600, *, dateiname: str | None = None) -> str:
    # Pure signing computation, no network I/O -- safe to call directly
    # from an async route without a threadpool hop.
    params = {"Bucket": BUCKET, "Key": key}
    if dateiname:
        params["ResponseContentDisposition"] = f'attachment; filename="{dateiname}"'
    return _public_client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_seconds)
