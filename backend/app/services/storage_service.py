import uuid

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
            _internal_client.create_bucket(Bucket=BUCKET)

    await run_in_threadpool(_ensure)


def new_object_key(vorgang_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"vorgaenge/{vorgang_id}/{uuid.uuid4()}.{suffix}"


def new_kunde_logo_key(kunde_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"kunden/{kunde_id}/logo/{uuid.uuid4()}.{suffix}"


def new_mandant_logo_key(mandant_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"mandanten/{mandant_id}/logo/{uuid.uuid4()}.{suffix}"


def new_rechnung_pdf_key(rechnung_id: uuid.UUID) -> str:
    return f"rechnungen/{rechnung_id}/versendet-{uuid.uuid4()}.pdf"


def new_rechnung_xml_key(rechnung_id: uuid.UUID) -> str:
    return f"rechnungen/{rechnung_id}/versendet-{uuid.uuid4()}.xml"


def new_eingangsrechnung_beleg_key(eingangsrechnung_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"eingangsrechnungen/{eingangsrechnung_id}/beleg/{uuid.uuid4()}.{suffix}"


def new_mail_attachment_key(message_id: uuid.UUID, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"mail-nachrichten/{message_id}/{uuid.uuid4()}.{suffix}"


def new_dsgvo_dokument_key(typ: str, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"dsgvo/{typ}/{uuid.uuid4()}.{suffix}"


async def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    # SSE-S3 (serverseitig, MinIO-verwalteter Schluessel) -- kein KMS/eigenes
    # Schluesselmanagement noetig, verschluesselt aber Kundenfotos/
    # Unterschriften/Rechnungs-PDFs/Belege "at rest" auf der Festplatte.
    await run_in_threadpool(
        _internal_client.put_object,
        Bucket=BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )


async def download_bytes(key: str) -> bytes:
    def _get() -> bytes:
        obj = _internal_client.get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read()

    return await run_in_threadpool(_get)


async def delete_object(key: str) -> None:
    await run_in_threadpool(_internal_client.delete_object, Bucket=BUCKET, Key=key)


def presigned_get_url(key: str, expires_seconds: int = 3600) -> str:
    # Pure signing computation, no network I/O -- safe to call directly
    # from an async route without a threadpool hop.
    return _public_client.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=expires_seconds
    )
