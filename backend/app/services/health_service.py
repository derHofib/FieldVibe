"""Bereitschafts-Pruefungen (/health/ready) und Heartbeat-Auswertung
(/health/heartbeats, Watchdog). Die Ergebnisse tragen bewusst keine Hostnamen,
Zugangsdaten oder Roh-Exceptions -- Details sieht nur, wer sich ausweist
(siehe app/api/routes/health.py)."""
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.session import engine, system_session
from app.models.integration import MandantIntegration
from app.models.mail_account import MailAccount
from app.models.mail_outbox import MailOutbox
from app.services import storage_service
from app.services.job_state_service import lade_laeufe

logger = logging.getLogger("app.heartbeat")

PRUEFUNG_TIMEOUT_SEKUNDEN = 5
_BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass
class Pruefung:
    ok: bool
    detail: str = ""


@lru_cache
def alembic_head() -> str:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _kenne_revision(revision: str) -> bool:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    try:
        return ScriptDirectory.from_config(cfg).get_revision(revision) is not None
    except Exception:
        return False


async def pruefe_db() -> Pruefung:
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), PRUEFUNG_TIMEOUT_SEKUNDEN)
        return Pruefung(True)
    except Exception as exc:
        logger.warning("Health: Datenbank nicht erreichbar (%s)", type(exc).__name__)
        return Pruefung(False, "Datenbank nicht erreichbar")


async def pruefe_s3() -> Pruefung:
    # head_bucket statt ensure_bucket: ein Gesundheitscheck darf keinen Bucket anlegen.
    def _head() -> None:
        storage_service._internal_client.head_bucket(Bucket=storage_service.BUCKET)

    try:
        await asyncio.wait_for(asyncio.to_thread(_head), PRUEFUNG_TIMEOUT_SEKUNDEN)
        return Pruefung(True)
    except Exception as exc:
        logger.warning("Health: Objektspeicher nicht erreichbar (%s)", type(exc).__name__)
        return Pruefung(False, "Objektspeicher nicht erreichbar")


async def pruefe_migration() -> Pruefung:
    """DB-Stand muss dem Code-Head entsprechen. Ist die DB NEUER als der Code
    (Rollback auf ein altes Image nach einer Migration), bleibt die Instanz
    bereit -- sonst koennte ein Rollback nie gesund werden; der Hinweis steht
    in der Detailansicht."""
    try:
        async with engine.connect() as conn:
            zeilen = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    except Exception:
        return Pruefung(False, "alembic_version nicht lesbar (Migrationen nie ausgefuehrt?)")
    kopf = alembic_head()
    if list(zeilen) == [kopf]:
        return Pruefung(True, f"auf Stand {kopf}")
    if len(zeilen) == 1 and not _kenne_revision(zeilen[0]):
        return Pruefung(True, f"DB ({zeilen[0]}) neuer als Code ({kopf}) -- Rollback-Stand")
    return Pruefung(False, f"Migration ausstehend: DB {','.join(zeilen) or '-'} / Code {kopf}")


async def bereitschaft() -> dict[str, Pruefung]:
    db, s3, migration = await asyncio.gather(pruefe_db(), pruefe_s3(), pruefe_migration())
    if not db.ok:
        migration = Pruefung(False, "nicht pruefbar")
    return {"datenbank": db, "objektspeicher": s3, "migration": migration}


# --- Heartbeats --------------------------------------------------------------

def _eintrag(name: str, letzter: datetime | None, max_alter: int | None, jetzt: datetime, *, hinweis: str = "",
             fehlend_ist_fehler: bool = True) -> dict:
    alter = (jetzt - letzter).total_seconds() if letzter else None
    if letzter is None:
        status = "fehler" if fehlend_ist_fehler else "unbekannt"
        hinweis = hinweis or "noch nie gelaufen"
    elif max_alter is not None and alter > max_alter:
        status = "fehler"
        hinweis = hinweis or f"seit {int(alter // 60)} min ohne Lebenszeichen (Grenze {max_alter // 60} min)"
    else:
        status = "ok"
    return {
        "name": name,
        "status": status,
        "letzter_lauf": letzter.isoformat() if letzter else None,
        "alter_sekunden": round(alter) if alter is not None else None,
        "max_alter_sekunden": max_alter,
        "hinweis": hinweis or None,
    }


def _lese_backup_status(pfad: str) -> dict | None:
    try:
        return json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


async def heartbeats(jetzt: datetime | None = None) -> list[dict]:
    s = get_settings()
    jetzt = jetzt or datetime.now(timezone.utc)
    ergebnis: list[dict] = []

    async with system_session() as session:
        worker = (await lade_laeufe(session, "worker_tick")).get(None)
        ergebnis.append(_eintrag(
            "worker_tick", worker.letzter_lauf_am if worker else None, s.heartbeat_worker_max_alter_sekunden, jetzt,
        ))

        aktive_konten = (await session.execute(
            select(MailAccount.mandant_id, func.count(), func.min(func.coalesce(MailAccount.letzter_sync_am, MailAccount.created_at)))
            .where(MailAccount.aktiv.is_(True)).group_by(MailAccount.mandant_id)
        )).all()
        sync = (await lade_laeufe(session, "mail_sync")).get(None)
        if aktive_konten:
            ergebnis.append(_eintrag(
                "mail_sync", sync.letzter_lauf_am if sync else None, s.heartbeat_mail_sync_max_alter_sekunden, jetzt,
            ))
        else:
            ergebnis.append({**_eintrag("mail_sync", None, None, jetzt, fehlend_ist_fehler=False), "status": "aus",
                             "hinweis": "keine aktiven Postfaecher"})

        grenze = jetzt - timedelta(minutes=s.heartbeat_mail_konto_max_alter_minuten)
        veraltet = (await session.execute(
            select(MailAccount.mandant_id, func.count())
            .where(MailAccount.aktiv.is_(True), func.coalesce(MailAccount.letzter_sync_am, MailAccount.created_at) < grenze)
            .group_by(MailAccount.mandant_id)
        )).all()
        ergebnis.append({
            "name": "mail_konten",
            "status": "warnung" if veraltet else "ok",
            "konten_aktiv": sum(n for _, n, _ in aktive_konten),
            "konten_veraltet": sum(n for _, n in veraltet),
            "mandanten_betroffen": [str(m) for m, _ in veraltet],
            "max_alter_sekunden": s.heartbeat_mail_konto_max_alter_minuten * 60,
            "hinweis": None,
        })

        imap_aktiv = (await session.execute(
            select(func.count()).select_from(MandantIntegration)
            .where(MandantIntegration.typ == "imap", MandantIntegration.aktiv.is_(True))
        )).scalar_one()
        ingest = (await lade_laeufe(session, "email_ingest")).get(None)
        if imap_aktiv:
            ergebnis.append(_eintrag(
                "email_ingest", ingest.letzter_lauf_am if ingest else None, s.heartbeat_email_ingest_max_alter_sekunden, jetzt,
            ))

        outbox = (await session.execute(
            select(MailOutbox.status, func.count(), func.min(MailOutbox.naechster_versuch_am))
            .where(MailOutbox.status.in_(("pending", "sending", "failed"))).group_by(MailOutbox.status)
        )).all()
        zaehler = {st: (n, aelteste) for st, n, aelteste in outbox}
        ueberfaellig = (await session.execute(
            select(func.count()).select_from(MailOutbox)
            .where(MailOutbox.status == "pending", MailOutbox.naechster_versuch_am < jetzt - timedelta(minutes=10))
        )).scalar_one()
        ergebnis.append({
            "name": "mail_outbox",
            "status": "fehler" if zaehler.get("failed") or ueberfaellig else "ok",
            "pending": zaehler.get("pending", (0, None))[0],
            "sending": zaehler.get("sending", (0, None))[0],
            "failed": zaehler.get("failed", (0, None))[0],
            "pending_ueberfaellig": ueberfaellig,
            "hinweis": "Mails haengen oder sind endgueltig fehlgeschlagen" if zaehler.get("failed") or ueberfaellig else None,
        })

    if s.backup_status_datei:
        daten = _lese_backup_status(s.backup_status_datei)
        if daten is None:
            ergebnis.append({"name": "backup", "status": "fehler", "hinweis": "letzter-lauf.json nicht lesbar"})
        else:
            try:
                zeitpunkt = datetime.fromisoformat(daten["zeitpunkt"])
            except (KeyError, ValueError):
                zeitpunkt = None
            eintrag = _eintrag("backup", zeitpunkt, s.backup_max_alter_stunden * 3600, jetzt)
            if daten.get("status") != "ok":
                eintrag["status"] = "fehler"
                eintrag["hinweis"] = "letztes Backup fehlgeschlagen"
            ergebnis.append(eintrag)
    return ergebnis


def gesamtstatus(eintraege: list[dict]) -> str:
    stati = {e["status"] for e in eintraege}
    if "fehler" in stati:
        return "fehler"
    if "warnung" in stati:
        return "warnung"
    return "ok"


_letzter_alarmstand: dict[str, str] = {}


def protokolliere_alarme(eintraege: list[dict]) -> None:
    """Loggt Zustandswechsel (nicht jeden Durchlauf): WARNING bei warnung, ERROR bei
    fehler, INFO bei Entwarnung. Greift im Backend-Prozess, auch wenn der Worker tot ist."""
    for e in eintraege:
        alt = _letzter_alarmstand.get(e["name"], "ok")
        neu = e["status"] if e["status"] in ("warnung", "fehler") else "ok"
        if neu == alt:
            continue
        _letzter_alarmstand[e["name"]] = neu
        extra = {"event": "heartbeat_alarm"}
        if neu == "ok":
            logger.info("Heartbeat %s wieder in Ordnung", e["name"], extra=extra)
        else:
            logger.log(
                logging.ERROR if neu == "fehler" else logging.WARNING,
                "Heartbeat-Alarm %s: %s", e["name"], e.get("hinweis") or neu, extra=extra,
            )


async def watchdog_schleife(intervall_sekunden: int = 300) -> None:
    while True:
        await asyncio.sleep(intervall_sekunden)
        try:
            protokolliere_alarme(await heartbeats())
        except Exception:
            logger.exception("Heartbeat-Auswertung fehlgeschlagen")
