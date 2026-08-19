import html
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_einladung_token, decode_token
from app.models.account_typ import AccountTyp
from app.models.einladung import Einladung
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.partner_zugang import PartnerZugang
from app.models.user import User
from app.services.email_service import EmailNichtKonfiguriert, send_email

_settings = get_settings()
_logger = logging.getLogger("app.einladungen")

_REGISTRIERUNGS_PFAD = {
    "mitarbeiter": "/registrieren",
    "kunde": "/portal/registrieren",
    "partner": "/partnerportal/registrieren",
}

# Anzeigename je fest verdrahteter Rolle -- fuer die "Eingeladen von"/
# "Rolle"-Zeilen im Steckbrief der Einladungsmail (siehe _steckbrief_zeilen
# unten). "custom" hat keinen festen Namen mehr (siehe Migration 0037) --
# dessen Label wird stattdessen aus dem Account-Typ-Namen aufgeloest
# (siehe versende_einladung).
ROLLEN_LABEL = {
    "super_admin": "Super-Admin",
    "mandant_admin": "Mandanten-Admin",
}

# Wortmarke exakt wie auf den Login-Seiten (src/pages/LoginPage.tsx,
# src/pages/portal/PortalLoginPage.tsx): "FieldVibe" bzw. "Kundenportal"/
# "Partnerportal" mit Cyan-Akzent auf dem zweiten Wortteil.
_WORDMARK_HTML = {
    "mitarbeiter": "FieldVibe",
    "kunde": 'Kunden<span style="color:#22d3ee;">portal</span>',
    "partner": 'Partner<span style="color:#22d3ee;">portal</span>',
}


async def konto_existiert_bereits(session: AsyncSession, art: str, email: str) -> bool:
    if art == "mitarbeiter":
        stmt = select(User).where(func.lower(User.email) == email)
    elif art == "kunde":
        stmt = select(KundenportalZugang).where(func.lower(KundenportalZugang.email) == email)
    else:
        stmt = select(PartnerZugang).where(func.lower(PartnerZugang.email) == email)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def create_einladung(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    email: str,
    art: str,
    rolle: str | None = None,
    account_typ_id: UUID | None = None,
    kunde_id: UUID | None = None,
    partner_id: UUID | None = None,
    eingeladen_von: UUID | None,
) -> Einladung:
    if await konto_existiert_bereits(session, art, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse existiert bereits ein Account",
        )

    einladung = Einladung(
        mandant_id=mandant_id,
        email=email,
        art=art,
        rolle=rolle,
        account_typ_id=account_typ_id,
        kunde_id=kunde_id,
        partner_id=partner_id,
        eingeladen_von=eingeladen_von,
    )
    session.add(einladung)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse liegt bereits eine offene Einladung vor",
        ) from exc
    return einladung


def registrierungslink_erzeugen(einladung: Einladung) -> str:
    """Oeffentlich (kein Unterstrich-Praefix), weil die Routen den Link
    unabhaengig vom Mailversand fuer einen "Link kopieren"-Button brauchen
    (siehe versende_einladung) -- jeder Aufruf erzeugt ein frisches Token,
    mehrere gleichzeitig gueltige Links pro Einladung sind unproblematisch,
    da resolve_offene_einladung nur ueber die Einladungs-ID + status=="offen"
    prueft, nicht ueber ein bestimmtes Token."""
    token = create_einladung_token(einladung_id=einladung.id)
    pfad = _REGISTRIERUNGS_PFAD[einladung.art]
    return f"{_settings.frontend_base_url}{pfad}?token={token}"


def _steckbrief_zeilen(
    einladung: Einladung,
    *,
    absender_name: str,
    absender_rolle_label: str | None,
    mandant_name: str,
    eingeladen_rolle_label: str,
) -> list[tuple[str, str, str | None]]:
    """(Label, Wert, Zusatz) je Steckbrief-Zeile -- Zusatz erscheint als
    kleinere zweite Zeile unter dem Wert (Rolle des Einladenden, bzw.
    "als Nachunternehmer" bei Partnern)."""
    if einladung.art == "mitarbeiter":
        return [
            ("Eingeladen von", absender_name, absender_rolle_label),
            ("Betrieb", mandant_name, None),
            ("Rolle", eingeladen_rolle_label, None),
        ]
    if einladung.art == "kunde":
        return [
            ("Eingeladen von", absender_name, None),
            ("Betrieb", mandant_name, None),
            ("Zugang", "Kundenportal", None),
        ]
    return [
        ("Eingeladen von", absender_name, None),
        ("Betrieb", mandant_name, None),
        ("Zugang", "Partnerportal", "als Nachunternehmer"),
    ]


def _inhalte(einladung: Einladung, *, absender_name: str, mandant_name: str) -> dict:
    if einladung.art == "mitarbeiter":
        return {
            "subject": f"{absender_name} lädt Sie zu {mandant_name} ein",
            "wordmark": _WORDMARK_HTML["mitarbeiter"],
            "kicker": "Team-Einladung",
            "message": (
                "Nach der Registrierung sehen Sie Ihre Aufträge, können Fotos hochladen "
                "und mit dem Team chatten – direkt vom Handy."
            ),
            "cta": "Einladung annehmen",
            "footer": f"FieldVibe · Auftragsverwaltung für {mandant_name}",
        }
    if einladung.art == "kunde":
        return {
            "subject": f"Einladung zum Kundenportal von {mandant_name}",
            "wordmark": _WORDMARK_HTML["kunde"],
            "kicker": f"Einladung von {mandant_name}",
            "message": (
                "Dort sehen Sie Angebote, Rechnungen und den Status Ihrer Aufträge – "
                "und können Angebote direkt online annehmen."
            ),
            "cta": "Kundenportal-Zugang einrichten",
            "footer": f"FieldVibe · Kundenportal von {mandant_name}",
        }
    return {
        "subject": f"Einladung zum Partnerportal von {mandant_name}",
        "wordmark": _WORDMARK_HTML["partner"],
        "kicker": f"Einladung von {mandant_name}",
        "message": (
            "Dort sehen Sie zugewiesene Aufträge, können sie annehmen oder ablehnen "
            "und den Status direkt aktualisieren."
        ),
        "cta": "Partnerportal-Zugang einrichten",
        "footer": f"FieldVibe · Partnerportal von {mandant_name}",
    }


def _render_html(
    *, wordmark: str, kicker: str, zeilen: list[tuple[str, str, str | None]], message: str,
    cta_label: str, link: str, footer: str, gueltig_tage: int,
) -> str:
    """Tabellenbasiertes, komplett inline gestyltes HTML (kein <style>-Block,
    kein Flexbox, kein backdrop-blur/Sternenhimmel) -- die "bulletproof"
    Bautechnik fuer E-Mail-Clients wie Outlook Desktop, das nur eine
    Teilmenge von CSS versteht. Verlauf/Glow sind reine Verschoenerung
    (background-image zusaetzlich zu bgcolor); Clients, die das ignorieren,
    zeigen einfach die flache Ersatzfarbe."""
    zeilen_html = "".join(
        f"""<tr>
          <td style="padding:4px 0;font-size:10.5px;color:#e8a445;font-weight:700;
              text-transform:uppercase;letter-spacing:.04em;width:112px;vertical-align:top;
              font-family:Arial,Helvetica,sans-serif;">{html.escape(label)}</td>
          <td style="padding:4px 0;font-size:12.5px;color:#f1f5f9;font-weight:600;
              font-family:Arial,Helvetica,sans-serif;">{html.escape(wert)}{
              f'<br><span style="color:#94a3b8;font-weight:400;font-size:11px;">{html.escape(zusatz)}</span>' if zusatz else ""
          }</td>
        </tr>"""
        for label, wert, zusatz in zeilen
    )
    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background-color:#020617;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#020617;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="460" cellpadding="0" cellspacing="0"
       style="max-width:460px;width:100%;background-color:#0f172a;border:1px solid #22415c;border-radius:14px;">
<tr><td style="padding:32px 32px 28px;font-family:Arial,Helvetica,sans-serif;">

<div style="font-size:20px;font-weight:800;letter-spacing:.02em;color:#ffffff;margin:0 0 4px;">{wordmark}</div>
<div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#67e8f9;font-weight:700;margin:0 0 20px;">{html.escape(kicker)}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background-color:#241d10;border-left:3px solid #e8a445;border-radius:0 8px 8px 0;margin:0 0 20px;">
<tr><td style="padding:11px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{zeilen_html}
</table>
</td></tr>
</table>

<div style="color:#e2e8f0;font-size:14px;margin:0 0 12px;font-family:Arial,Helvetica,sans-serif;">Hallo,</div>
<div style="color:#cbd5e1;font-size:14px;line-height:1.7;margin:0 0 22px;font-family:Arial,Helvetica,sans-serif;">{html.escape(message)}</div>

<table role="presentation" cellpadding="0" cellspacing="0" width="100%">
<tr><td align="center" bgcolor="#0891b2" style="background-color:#0891b2;background-image:linear-gradient(90deg,#06b6d4,#2563eb);border-radius:8px;">
<a href="{html.escape(link)}" style="display:block;padding:13px 20px;color:#ffffff;text-decoration:none;font-weight:700;font-size:14.5px;font-family:Arial,Helvetica,sans-serif;">{html.escape(cta_label)}</a>
</td></tr>
</table>

<div style="color:#7c8ba1;font-size:12px;line-height:1.6;margin:20px 0 0;font-family:Arial,Helvetica,sans-serif;">
Der Link ist {gueltig_tage} Tage gültig. Falls Sie das nicht erwartet haben, ignorieren Sie diese E-Mail.
</div>

<hr style="border:none;border-top:1px solid #334155;margin:20px 0 14px;">
<div style="color:#64748b;font-size:11px;text-align:center;font-family:Arial,Helvetica,sans-serif;">{html.escape(footer)}</div>

</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _render_text(
    *, zeilen: list[tuple[str, str, str | None]], message: str, link: str, footer: str, gueltig_tage: int,
) -> str:
    breite = max(len(label) for label, _, _ in zeilen) + 1
    zeilen_text = "\n".join(
        f"  {(label + ':').ljust(breite + 1)}{wert}" + (f" ({zusatz})" if zusatz else "")
        for label, wert, zusatz in zeilen
    )
    return (
        f"Hallo,\n\n"
        f"Sie wurden zu FieldVibe eingeladen:\n\n"
        f"{zeilen_text}\n\n"
        f"{message}\n\n"
        f"Registrieren Sie sich hier:\n{link}\n\n"
        f"Der Link ist {gueltig_tage} Tage gültig. Falls Sie das nicht erwartet haben, "
        "ignorieren Sie diese E-Mail.\n\n"
        f"{footer}"
    )


async def versende_einladung(
    session: AsyncSession, einladung: Einladung, *, absender_name: str, absender_rolle: str | None = None
) -> bool:
    """Verschickt die Einladungsmail (Steckbrief-Design im FieldVibe-Look).
    Gibt zurueck, ob der Versand geglueckt ist -- der Registrierungslink
    selbst kommt unabhaengig davon immer per registrierungslink_erzeugen()
    zum Aufrufer zurueck (auch bei erfolgreichem Mailversand), damit ein
    Mitarbeiter den Link zusaetzlich manuell teilen kann, z.B. wenn die
    Einladungsmail im Spam landet."""
    link = registrierungslink_erzeugen(einladung)
    mandant = await session.get(Mandant, einladung.mandant_id)
    mandant_name = mandant.name if mandant else ""
    gueltig_tage = _settings.einladung_token_expire_minutes // (60 * 24)

    eingeladen_rolle_label = ROLLEN_LABEL.get(einladung.rolle or "", einladung.rolle or "")
    if einladung.rolle == "custom" and einladung.account_typ_id is not None:
        account_typ = await session.get(AccountTyp, einladung.account_typ_id)
        if account_typ is not None:
            eingeladen_rolle_label = account_typ.name

    zeilen = _steckbrief_zeilen(
        einladung,
        absender_name=absender_name,
        absender_rolle_label=ROLLEN_LABEL.get(absender_rolle or "", absender_rolle),
        mandant_name=mandant_name,
        eingeladen_rolle_label=eingeladen_rolle_label,
    )
    inhalte = _inhalte(einladung, absender_name=absender_name, mandant_name=mandant_name)

    html_body = _render_html(
        wordmark=inhalte["wordmark"], kicker=inhalte["kicker"], zeilen=zeilen, message=inhalte["message"],
        cta_label=inhalte["cta"], link=link, footer=inhalte["footer"], gueltig_tage=gueltig_tage,
    )
    text_body = _render_text(
        zeilen=zeilen, message=inhalte["message"], link=link, footer=inhalte["footer"], gueltig_tage=gueltig_tage,
    )

    try:
        await send_email(
            session,
            einladung.mandant_id,
            to=einladung.email,
            subject=inhalte["subject"],
            body=text_body,
            html_body=html_body,
        )
        return True
    except EmailNichtKonfiguriert:
        return False
    except Exception:
        _logger.exception("Einladungsmail konnte nicht verschickt werden (Einladung %s)", einladung.id)
        return False


def einladung_ist_abgelaufen(einladung: Einladung) -> bool:
    grenze = einladung.created_at + timedelta(minutes=_settings.einladung_token_expire_minutes)
    return datetime.now(timezone.utc) >= grenze


def to_read_model(einladung: Einladung, *, registrierungslink: str | None = None) -> dict:
    return {
        "id": einladung.id,
        "email": einladung.email,
        "art": einladung.art,
        "rolle": einladung.rolle,
        "account_typ_id": einladung.account_typ_id,
        "kunde_id": einladung.kunde_id,
        "partner_id": einladung.partner_id,
        "status": einladung.status,
        "abgelaufen": einladung.status == "offen" and einladung_ist_abgelaufen(einladung),
        "created_at": einladung.created_at,
        "angenommen_am": einladung.angenommen_am,
        "registrierungslink": registrierungslink,
    }


async def resolve_offene_einladung(session: AsyncSession, token: str, *, erwartete_art: str) -> Einladung:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Einladungslink ist ungültig oder abgelaufen",
        ) from exc

    if payload.get("type") != "einladung":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Einladungslink")

    einladung = await session.get(Einladung, payload["sub"])
    if einladung is None or einladung.art != erwartete_art or einladung.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Einladung ist nicht mehr gültig",
        )
    if await konto_existiert_bereits(session, einladung.art, einladung.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse existiert bereits ein Account",
        )
    return einladung


async def als_angenommen_markieren(session: AsyncSession, einladung: Einladung) -> None:
    einladung.status = "angenommen"
    einladung.angenommen_am = datetime.now(timezone.utc)
    await session.flush()
