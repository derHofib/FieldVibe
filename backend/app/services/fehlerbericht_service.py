import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import system_session
from app.models.fehlerbericht import FEHLERBERICHT_ERLEDIGT_STATUS, Fehlerbericht
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.fehlerbericht import FehlerberichtDetail, FehlerberichtListItem
from app.services import storage_service

logger = logging.getLogger(__name__)

ENTFERNT = "[entfernt]"
KONTEXT_MAX_BYTES = 1024 * 1024
SCREENSHOT_MAX_BYTES = 5 * 1024 * 1024
_MAX_TIEFE = 40

_HEADER_DENYLIST = frozenset(
    {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key", "x-auth-token"}
)
_KEY_TEILSTRINGE = (
    "password", "passwort", "kennwort", "token", "secret", "api_key", "apikey",
    "iban", "authorization", "cookie", "credential",
)
_JWT_RE = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
_PIN_TOKEN_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _schluessel_sensibel(schluessel: str) -> bool:
    klein = schluessel.lower()
    if klein in _HEADER_DENYLIST or any(t in klein for t in _KEY_TEILSTRINGE):
        return True
    # "pin" nur als eigenes Wort (pin, user_pin, userPin) -- als Teilstring
    # wuerde es "mapping", "shipping", "spinner" usw. mitschwaerzen.
    return "pin" in {t.lower() for t in _PIN_TOKEN_RE.findall(schluessel)}


def schwaerze(wert, _tiefe: int = 0):
    """Zweite Verteidigungslinie: das Frontend schwaerzt bereits, der Server
    verlaesst sich nicht darauf."""
    if _tiefe > _MAX_TIEFE:
        return ENTFERNT
    if isinstance(wert, str):
        return _JWT_RE.sub(ENTFERNT, wert)
    if isinstance(wert, dict):
        return {
            k: ENTFERNT if isinstance(k, str) and _schluessel_sensibel(k) else schwaerze(v, _tiefe + 1)
            for k, v in wert.items()
        }
    if isinstance(wert, list):
        # Header als Paarliste [["Authorization", "..."], ...]
        if (
            len(wert) == 2
            and isinstance(wert[0], str)
            and wert[0].lower() in _HEADER_DENYLIST
        ):
            return [wert[0], ENTFERNT]
        return [schwaerze(v, _tiefe + 1) for v in wert]
    return wert


# --- Fingerprint -----------------------------------------------------------

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_ZAHL_RE = re.compile(r"\d+")
_STACK_FRAME_RE = re.compile(r"^\s*(?:at\s+)?(?P<fn>[^\s(@]+)?\s*(?:[(@]\s*)?(?P<ort>\S+?)\)?\s*$")
_BUILD_HASH_RE = re.compile(r"-[A-Za-z0-9_]{6,}(?=\.[a-z]+$)")


def _normalisiere_text(text: str) -> str:
    text = _UUID_RE.sub(":id", text.lower())
    text = _ZAHL_RE.sub(":n", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


def normalisiere_route(route: str | None) -> str:
    if not route:
        return ""
    pfad = urlsplit(route).path or route
    pfad = _UUID_RE.sub(":id", pfad)
    return _ZAHL_RE.sub(":id", pfad)


def _stack_oberster_frame(stack) -> str:
    """Datei + Funktion ohne Zeilen/Spalten und ohne Build-Hash im Dateinamen,
    damit derselbe Fehler nach einem neuen Build/Zeilenverschiebung gleich bleibt."""
    if not isinstance(stack, str):
        return ""
    for zeile in stack.splitlines():
        zeile = zeile.strip()
        if not zeile or not (zeile.startswith("at ") or "@" in zeile):
            continue
        m = _STACK_FRAME_RE.match(zeile)
        if not m:
            continue
        ort = re.sub(r"(:\d+)+$", "", m.group("ort") or "")
        datei = _BUILD_HASH_RE.sub("", urlsplit(ort).path.rsplit("/", 1)[-1] or ort)
        return f"{m.group('fn') or ''}@{datei}"
    return ""


def _erste_fehlermeldung(kontext: dict) -> tuple[str, str] | None:
    konsole = kontext.get("konsole")
    if isinstance(konsole, list):
        for eintrag in konsole:
            if isinstance(eintrag, dict) and eintrag.get("level") == "error" and eintrag.get("nachricht"):
                return str(eintrag["nachricht"]), _stack_oberster_frame(eintrag.get("stack"))
    fehler = kontext.get("fehler")
    if isinstance(fehler, str) and fehler:
        return fehler, ""
    if isinstance(fehler, dict):
        nachricht = fehler.get("nachricht") or fehler.get("message")
        if nachricht:
            return str(nachricht), _stack_oberster_frame(fehler.get("stack"))
    return None


def berechne_fingerprint(kontext: dict, route: str | None) -> str | None:
    gefunden = _erste_fehlermeldung(kontext if isinstance(kontext, dict) else {})
    if gefunden is None:
        return None
    nachricht, frame = gefunden
    teile = [_normalisiere_text(nachricht), frame, normalisiere_route(route)]
    return hashlib.sha256("\n".join(teile).encode()).hexdigest()


async def finde_offenes_duplikat(
    session: AsyncSession, *, mandant_id: uuid.UUID, fingerprint: str | None
) -> uuid.UUID | None:
    if fingerprint is None:
        return None
    result = await session.execute(
        select(Fehlerbericht.id)
        .where(
            Fehlerbericht.mandant_id == mandant_id,
            Fehlerbericht.fingerprint == fingerprint,
            Fehlerbericht.erledigt_am.is_(None),
            Fehlerbericht.status.notin_(FEHLERBERICHT_ERLEDIGT_STATUS),
        )
        .order_by(Fehlerbericht.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


# --- Screenshots -----------------------------------------------------------

_ERLAUBTE_BILDTYPEN = {"image/png", "image/jpeg", "image/webp"}


def _magic_passt(data: bytes) -> bool:
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )


async def lese_screenshot(datei: UploadFile) -> tuple[bytes, str]:
    if datei.content_type not in _ERLAUBTE_BILDTYPEN:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Screenshot muss PNG, JPEG oder WebP sein",
        )
    data = await datei.read(SCREENSHOT_MAX_BYTES + 1)
    if len(data) > SCREENSHOT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Screenshot zu groß (max. 5 MB)"
        )
    if not _magic_passt(data):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Screenshot-Inhalt passt nicht zum Dateityp",
        )
    return data, datei.content_type


def pruefe_kontext_groesse(kontext: dict) -> None:
    if len(json.dumps(kontext, ensure_ascii=False).encode()) > KONTEXT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Kontext zu groß (max. 1 MB)"
        )


async def loesche_screenshots(keys: list[str | None]) -> None:
    for key in keys:
        if not key:
            continue
        try:
            await storage_service.delete_object(key)
        except Exception:
            # Verwaiste Objekte sind ein Schoenheitsfehler, kein Grund, das
            # Loeschen/den Job abzubrechen.
            logger.exception("Fehlerbericht-Screenshot %s konnte nicht gelöscht werden", key)


# --- Lesen / Aktualisieren -------------------------------------------------


async def namen_laden(
    session: AsyncSession, berichte: list[Fehlerbericht]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """(mandant_id -> Name, user_id -> Name) -- bewusst nur Namen, keine E-Mail."""
    mandant_ids = {b.mandant_id for b in berichte}
    user_ids = {b.user_id for b in berichte if b.user_id}
    mandanten: dict[uuid.UUID, str] = {}
    users: dict[uuid.UUID, str] = {}
    if mandant_ids:
        rows = await session.execute(select(Mandant.id, Mandant.name).where(Mandant.id.in_(mandant_ids)))
        mandanten = {i: n for i, n in rows.all()}
    if user_ids:
        rows = await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        users = {i: n for i, n in rows.all()}
    return mandanten, users


def _list_felder(b: Fehlerbericht, mandanten: dict, users: dict) -> dict:
    return dict(
        id=b.id,
        mandant_id=b.mandant_id,
        mandant_name=mandanten.get(b.mandant_id),
        melder_name=users.get(b.user_id) if b.user_id else None,
        titel=b.titel,
        schweregrad=b.schweregrad,
        status=b.status,
        route=b.route,
        app_version=b.app_version,
        commit_sha=b.commit_sha,
        duplikat_von_id=b.duplikat_von_id,
        hat_screenshot=bool(b.screenshot_original_key or b.screenshot_annotiert_key),
        erledigt_am=b.erledigt_am,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def zu_list_item(b: Fehlerbericht, mandanten: dict, users: dict) -> FehlerberichtListItem:
    return FehlerberichtListItem(**_list_felder(b, mandanten, users))


def zu_detail(b: Fehlerbericht, mandanten: dict, users: dict) -> FehlerberichtDetail:
    return FehlerberichtDetail(
        **_list_felder(b, mandanten, users),
        beschreibung=b.beschreibung,
        erwartet=b.erwartet,
        schritte=b.schritte,
        kontext=b.kontext or {},
        screenshot_original_url=_url(b.screenshot_original_key),
        screenshot_annotiert_url=_url(b.screenshot_annotiert_key),
        loesungsnotiz=b.loesungsnotiz,
        fix_commit=b.fix_commit,
        fix_pr_url=b.fix_pr_url,
    )


def _url(key: str | None) -> str | None:
    return storage_service.presigned_get_url(key, 3600) if key else None


def wende_update_an(bericht: Fehlerbericht, daten: dict) -> None:
    """`daten` enthaelt nur tatsaechlich gesendete Felder (model_dump(exclude_unset))."""
    for feld, wert in daten.items():
        if feld == "status" and wert is None:
            continue
        setattr(bericht, feld, wert)
    if "status" in daten and daten["status"] is not None:
        bericht.erledigt_am = (
            datetime.now(timezone.utc) if daten["status"] in FEHLERBERICHT_ERLEDIGT_STATUS else None
        )


# --- Loeschjob -------------------------------------------------------------


async def loesche_abgelaufene_fehlerberichte(jetzt: datetime | None = None) -> int:
    """Alle Mandanten (system_session); loescht Berichte samt S3-Objekten, die
    aelter als die Aufbewahrungsfrist sind."""
    jetzt = jetzt or datetime.now(timezone.utc)
    grenze = jetzt - timedelta(days=get_settings().fehlerbericht_aufbewahrung_tage)
    async with system_session() as session:
        rows = await session.execute(
            select(
                Fehlerbericht.id,
                Fehlerbericht.screenshot_original_key,
                Fehlerbericht.screenshot_annotiert_key,
            ).where(Fehlerbericht.created_at < grenze)
        )
        treffer = rows.all()
        if not treffer:
            return 0
        await session.execute(delete(Fehlerbericht).where(Fehlerbericht.id.in_([t[0] for t in treffer])))
    # Erst nach dem Commit: scheitert die DB-Transaktion, bleiben die Objekte
    # sonst nicht ohne Bericht zurueck.
    await loesche_screenshots([k for t in treffer for k in (t[1], t[2])])
    return len(treffer)


async def zaehler_je_status(session: AsyncSession, mandant_id: uuid.UUID | None) -> dict[str, int]:
    stmt = select(Fehlerbericht.status, func.count()).group_by(Fehlerbericht.status)
    if mandant_id is not None:
        stmt = stmt.where(Fehlerbericht.mandant_id == mandant_id)
    rows = await session.execute(stmt)
    return {s: n for s, n in rows.all()}


# --- AI-Bundle -------------------------------------------------------------

_BODY_MAX = 2000


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _liste(x) -> list:
    return [e for e in x if isinstance(e, dict)] if isinstance(x, list) else []


def _int(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _text(x, grenze: int | None = None) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        try:
            x = json.dumps(x, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            x = str(x)
    if grenze is not None and len(x) > grenze:
        x = x[:grenze] + f"… [gekürzt, {len(x)} Zeichen]"
    return x


def _block(inhalt: str, sprache: str = "") -> str:
    inhalt = inhalt.replace("```", "``\u200b`")
    return f"```{sprache}\n{inhalt}\n```"


def _zelle(x, grenze: int = 100) -> str:
    t = _text(x).replace("|", "\\|").replace("\n", " ")
    return t if len(t) <= grenze else t[: grenze - 1] + "…"


def _body_block(titel: str, wert) -> list[str]:
    if wert in (None, "", {}, []):
        return []
    text = _text(wert, _BODY_MAX)
    sprache = "json" if text.lstrip().startswith(("{", "[")) else ""
    return [f"{titel}:", _block(text, sprache)]


def ai_bundle_markdown(bericht: Fehlerbericht) -> str:
    kontext = _dict(bericht.kontext)
    netzwerk = _liste(kontext.get("netzwerk"))
    konsole = _liste(kontext.get("konsole"))
    breadcrumbs = _liste(kontext.get("breadcrumbs"))
    gemeldet = bericht.created_at.isoformat() if bericht.created_at else "unbekannt"

    z: list[str] = [f"# Fehlerbericht: {bericht.titel}", ""]
    z += [
        f"- **ID:** {bericht.id}",
        f"- **Mandant-ID:** {bericht.mandant_id}",
        f"- **Status:** {bericht.status}",
        f"- **Schweregrad:** {bericht.schweregrad}",
        f"- **Gemeldet am:** {gemeldet}",
        f"- **Route:** {bericht.route or 'unbekannt'}",
        f"- **App-Version:** {bericht.app_version or 'unbekannt'}",
        f"- **Commit:** {bericht.commit_sha or 'unbekannt'}",
        "",
        "## Beschreibung",
        bericht.beschreibung or "",
        "",
    ]
    if bericht.erwartet:
        z += ["## Erwartetes Verhalten", bericht.erwartet, ""]
    if bericht.schritte:
        z += ["## Schritte laut Melder", bericht.schritte, ""]

    z += ["## Reproduktion aus Klickpfad"]
    if breadcrumbs:
        for i, b in enumerate(breadcrumbs, 1):
            text = f" -- {_text(b.get('text'), 80)}" if b.get("text") else ""
            z.append(f"{i}. [{_text(b.get('zeit'))}] {_text(b.get('typ'))}: {_text(b.get('ziel'))}{text}")
    else:
        z.append("_Kein Klickpfad aufgezeichnet._")
    z.append("")

    fehlgeschlagen = [
        n for n in netzwerk if (_int(n.get("status")) or 0) >= 400 or n.get("fehler")
    ]
    z += [f"## Fehlgeschlagene Requests ({len(fehlgeschlagen)})"]
    if fehlgeschlagen:
        for n in fehlgeschlagen:
            status_txt = n.get("status") if n.get("status") is not None else "kein Status"
            z.append(f"### {_text(n.get('methode'))} {_text(n.get('url'))} -> {status_txt}")
            z.append(f"- Zeit: {_text(n.get('zeit'))}, Dauer: {_text(n.get('dauer_ms'))} ms")
            if n.get("fehler"):
                z.append(f"- Fehler: {_text(n.get('fehler'), 500)}")
            z += _body_block("Request-Body", n.get("request_body"))
            z += _body_block("Response-Body", n.get("response_body"))
            z.append("")
    else:
        z += ["_Keine._", ""]

    z += [f"## Alle Requests ({len(netzwerk)})"]
    if netzwerk:
        z += ["| Zeit | Methode | URL | Status | Dauer (ms) |", "|---|---|---|---|---|"]
        for n in netzwerk:
            z.append(
                f"| {_zelle(n.get('zeit'))} | {_zelle(n.get('methode'))} | {_zelle(n.get('url'), 120)} "
                f"| {_zelle(n.get('status') if n.get('fehler') is None else n.get('fehler'))} "
                f"| {_zelle(n.get('dauer_ms'))} |"
            )
    else:
        z.append("_Keine._")
    z.append("")

    fehler_konsole = [k for k in konsole if k.get("level") == "error"]
    z += [f"## Konsolenfehler ({len(fehler_konsole)})"]
    if fehler_konsole:
        for k in fehler_konsole:
            z.append(f"- [{_text(k.get('zeit'))}] {_text(k.get('nachricht'), 500)}")
            if k.get("stack"):
                z.append(_block(_text(k.get("stack"), _BODY_MAX)))
    else:
        z.append("_Keine._")
    z.append("")

    for titel, schluessel in (("Umgebung", "umgebung"), ("Sitzung", "sitzung"), ("App-State", "app_state")):
        z += [f"## {titel}"]
        wert = kontext.get(schluessel)
        z.append(_block(_text(wert, 4000), "json") if wert else "_Keine Angaben._")
        z.append("")

    z += ["## Screenshots"]
    original = _url(bericht.screenshot_original_key)
    annotiert = _url(bericht.screenshot_annotiert_key)
    if original or annotiert:
        if annotiert:
            z.append(f"- Annotiert (1 h gültig): {annotiert}")
        if original:
            z.append(f"- Original (1 h gültig): {original}")
    else:
        z.append("_Keine._")
    z.append("")
    return "\n".join(z)
