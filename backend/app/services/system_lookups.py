"""Alle mandantenuebergreifenden Lookups an einer Stelle.

system_session umgeht die RLS komplett. Jede Funktion hier oeffnet sie nur
fuer genau eine schmale Abfrage und gibt unveraenderliche Werte statt ORM-
Objekten zurueck; alles Weitere (Schreiben, Audit, Token-Rotation) laeuft
danach in tenant_session(mandant_id=<aus dem Lookup>). Bewusst keine
SECURITY-DEFINER-Funktionen: unter FORCE RLS unterlaege auch deren Owner der
Policy, braeuchte also eine BYPASSRLS-Rolle oder wieder die Session-Variable.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import system_session, tenant_session
from app.models.einladung import Einladung
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.partner_zugang import PartnerZugang
from app.models.user import User


def _normalisiert(email: str) -> str:
    # func.lower() auf beiden Seiten statt dem Aufrufer zu trauen: so bleibt der
    # Login auch dann case-insensitiv, wenn Seed-Skript oder direkter DB-Insert
    # die App-seitige Normalisierung beim Anlegen umgangen haben.
    return email.strip().lower()


# --- Mitarbeiter-Konten ------------------------------------------------------


@dataclass(frozen=True)
class UserLogin:
    id: UUID
    mandant_id: UUID | None
    passwort_hash: str
    aktiv: bool


@dataclass(frozen=True)
class UserKern:
    id: UUID
    mandant_id: UUID | None
    email: str
    name: str
    rolle: str
    aktiv: bool
    token_version: int
    mfa_aktiv: bool


@dataclass(frozen=True)
class UserProfil:
    name: str
    email: str
    mfa_aktiv: bool
    bottom_nav_items: Any
    office_nav_items: Any


_KERN_SPALTEN = (
    User.id,
    User.mandant_id,
    User.email,
    User.name,
    User.role,
    User.aktiv,
    User.token_version,
    User.mfa_aktiv,
)


def _kern(zeile) -> UserKern:
    return UserKern(
        id=zeile.id,
        mandant_id=zeile.mandant_id,
        email=zeile.email,
        name=zeile.name,
        rolle=zeile.role,
        aktiv=zeile.aktiv,
        token_version=zeile.token_version,
        mfa_aktiv=zeile.mfa_aktiv,
    )


async def user_lookup_by_email(email: str) -> UserLogin | None:
    # Die Adresse ist plattformweit eindeutig, der Mandant vor dem Login also noch unbekannt.
    async with system_session(grund="login: user-lookup per email") as session:
        zeile = (
            await session.execute(
                select(User.id, User.mandant_id, User.password_hash, User.aktiv).where(
                    func.lower(User.email) == _normalisiert(email)
                )
            )
        ).one_or_none()
    if zeile is None:
        return None
    return UserLogin(
        id=zeile.id, mandant_id=zeile.mandant_id, passwort_hash=zeile.password_hash, aktiv=zeile.aktiv
    )


async def user_kern_by_email(email: str) -> UserKern | None:
    async with system_session(grund="login: passwort vergessen lookup") as session:
        zeile = (
            await session.execute(
                select(*_KERN_SPALTEN).where(func.lower(User.email) == _normalisiert(email))
            )
        ).one_or_none()
    return _kern(zeile) if zeile is not None else None


async def user_kern_by_id(user_id: UUID | str, *, grund: str) -> UserKern | None:
    """Fuer Token-Einloesung (Refresh, Reset-Link, MFA-Token): das Token nennt nur
    die User-ID, der Mandant steht erst in der Zeile."""
    async with system_session(grund=grund) as session:
        zeile = (
            await session.execute(select(*_KERN_SPALTEN).where(User.id == user_id))
        ).one_or_none()
    return _kern(zeile) if zeile is not None else None


async def user_profil_by_id(user_id: UUID) -> UserProfil | None:
    """/me: bei Impersonation ist sub der Super-Admin, dessen Zeile (mandant_id
    NULL) unter der Mandanten-RLS nicht sichtbar waere."""
    async with system_session(grund="auth: me (auch super_admin/impersonation)") as session:
        zeile = (
            await session.execute(
                select(
                    User.name, User.email, User.mfa_aktiv, User.bottom_nav_items, User.office_nav_items
                ).where(User.id == user_id)
            )
        ).one_or_none()
    if zeile is None:
        return None
    return UserProfil(
        name=zeile.name,
        email=zeile.email,
        mfa_aktiv=zeile.mfa_aktiv,
        bottom_nav_items=zeile.bottom_nav_items,
        office_nav_items=zeile.office_nav_items,
    )


@dataclass(frozen=True)
class TokenStatus:
    token_version: int
    aktiv: bool


async def user_token_status(user_id: UUID) -> TokenStatus | None:
    """Stream-Tickets tragen den Mandanten, bei Impersonation aber den Super-Admin
    als sub (mandant_id NULL) -- daher ohne Mandanten-Scope."""
    async with system_session(
        grund="stream: ticket token-version pruefen", drosselung_s=300
    ) as session:
        zeile = (
            await session.execute(
                select(User.token_version, User.aktiv).where(User.id == user_id)
            )
        ).one_or_none()
    return TokenStatus(zeile.token_version, zeile.aktiv) if zeile is not None else None


async def konto_existiert_plattformweit(art: str, email: str) -> bool:
    """Einladungsannahme: die E-Mail ist je Identitaetsraum plattformweit eindeutig,
    unter der Mandanten-RLS waeren fremde Konten unsichtbar."""
    modell = {"mitarbeiter": User, "kunde": KundenportalZugang}.get(art, PartnerZugang)
    async with system_session(grund="einladung: konto-duplikat pruefen") as session:
        treffer = await session.scalar(
            select(modell.id).where(func.lower(modell.email) == _normalisiert(email))
        )
    return treffer is not None


async def einladung_mandant_id(einladung_id: UUID | str) -> UUID | None:
    async with system_session(grund="einladung: mandant per token") as session:
        return await session.scalar(select(Einladung.mandant_id).where(Einladung.id == einladung_id))


@asynccontextmanager
async def konto_session(mandant_id: UUID | None, *, grund: str) -> AsyncIterator[AsyncSession]:
    """Session fuer Schreibzugriffe auf das eigene Konto. Mit Mandant ist das eine
    normale tenant_session; nur Konten ohne Mandant (super_admin) liegen ausserhalb
    jeder Mandanten-RLS-Sicht (users-Policy verlangt mandant_id = Kontext) und
    brauchen den Bypass -- dann auch fuer das zugehoerige Audit mit mandant_id NULL."""
    if mandant_id is not None:
        async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
            yield session
        return
    async with system_session(grund=grund) as session:
        yield session


# --- Token-Version (Widerruf) -------------------------------------------------

_TOKEN_MODELLE = {"user": User, "kunde": KundenportalZugang, "partner": PartnerZugang}


async def token_version_lookup(
    typ: Literal["user", "kunde", "partner"], account_id: UUID, mandant_id: UUID | None
) -> int | None:
    """Mit Mandant (signierter Claim) unter dessen RLS, ohne nur fuer Konten ausserhalb
    davon (super_admin, Impersonation: sub ist der Super-Admin). Gelesen wird
    ausschliesslich der Zaehler des Token-Subjects."""
    modell = _TOKEN_MODELLE[typ]
    stmt = select(modell.token_version).where(modell.id == account_id)
    if mandant_id is not None:
        async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
            return await session.scalar(stmt)
    async with system_session(grund="auth-request: token-version pruefen", drosselung_s=300) as session:
        return await session.scalar(stmt)


# --- Portal-Zugaenge (Kunde/Partner) -------------------------------------------


@dataclass(frozen=True)
class PortalZugang:
    id: UUID
    mandant_id: UUID
    email: str
    name: str
    passwort_hash: str
    aktiv: bool
    token_version: int
    kunde_id: UUID | None = None
    partner_id: UUID | None = None


async def _portal_zugang(modell, bezug: str, *, grund: str, email: str | None = None, zugang_id=None):
    stmt = select(
        modell.id,
        modell.mandant_id,
        modell.email,
        modell.name,
        modell.password_hash,
        modell.aktiv,
        modell.token_version,
        getattr(modell, bezug),
    )
    stmt = (
        stmt.where(func.lower(modell.email) == _normalisiert(email))
        if email is not None
        else stmt.where(modell.id == zugang_id)
    )
    async with system_session(grund=grund) as session:
        zeile = (await session.execute(stmt)).one_or_none()
    if zeile is None:
        return None
    return PortalZugang(
        id=zeile.id,
        mandant_id=zeile.mandant_id,
        email=zeile.email,
        name=zeile.name,
        passwort_hash=zeile.password_hash,
        aktiv=zeile.aktiv,
        token_version=zeile.token_version,
        **{bezug: zeile[7]},
    )


async def kundenzugang_by_email(email: str, *, grund: str = "portal-auth: kunden-lookup per email") -> PortalZugang | None:
    return await _portal_zugang(KundenportalZugang, "kunde_id", grund=grund, email=email)


async def kundenzugang_by_id(zugang_id: UUID | str, *, grund: str) -> PortalZugang | None:
    return await _portal_zugang(KundenportalZugang, "kunde_id", grund=grund, zugang_id=zugang_id)


async def partnerzugang_by_email(email: str, *, grund: str = "partner-auth: lookup per email") -> PortalZugang | None:
    return await _portal_zugang(PartnerZugang, "partner_id", grund=grund, email=email)


async def partnerzugang_by_id(zugang_id: UUID | str, *, grund: str) -> PortalZugang | None:
    return await _portal_zugang(PartnerZugang, "partner_id", grund=grund, zugang_id=zugang_id)


@dataclass(frozen=True)
class KundeLink:
    kunde_name: str
    logo_object_key: str | None
    mandant_name: str
    mandant_aktiv: bool


async def kunde_link_lookup(portal_slug: str, *, grund: str) -> KundeLink | None:
    async with system_session(grund=grund) as session:
        zeile = (
            await session.execute(
                select(Kunde.name, Kunde.logo_object_key, Mandant.name, Mandant.status)
                .join(Mandant, Mandant.id == Kunde.mandant_id)
                .where(Kunde.portal_slug == portal_slug)
            )
        ).one_or_none()
    if zeile is None:
        return None
    return KundeLink(
        kunde_name=zeile[0],
        logo_object_key=zeile[1],
        mandant_name=zeile[2],
        mandant_aktiv=zeile[3] == "aktiv",
    )


# --- Oeffentliche Rechtstexte --------------------------------------------------


@dataclass(frozen=True)
class MandantRechtliches:
    name: str
    firmendaten: dict


async def rechtliches_per_portal_slug(portal_slug: str) -> MandantRechtliches | None:
    """None bei unbekanntem Slug oder nicht aktivem Mandanten."""
    async with system_session(grund="public: rechtstexte per portal-slug") as session:
        zeile = (
            await session.execute(
                select(Mandant.name, Mandant.firmendaten, Mandant.status)
                .join(Kunde, Kunde.mandant_id == Mandant.id)
                .where(Kunde.portal_slug == portal_slug)
            )
        ).one_or_none()
    if zeile is None or zeile.status != "aktiv":
        return None
    return MandantRechtliches(name=zeile.name, firmendaten=zeile.firmendaten or {})


async def einziger_aktiver_mandant_rechtliches() -> MandantRechtliches | None:
    """None, sobald es nicht genau einen aktiven Mandanten gibt (keine Aufzaehlung)."""
    async with system_session(grund="public: rechtstexte ohne slug") as session:
        zeilen = (
            await session.execute(
                select(Mandant.name, Mandant.firmendaten).where(Mandant.status == "aktiv").limit(2)
            )
        ).all()
    if len(zeilen) != 1:
        return None
    return MandantRechtliches(name=zeilen[0].name, firmendaten=zeilen[0].firmendaten or {})


# --- Impersonation / Service-API -----------------------------------------------


@dataclass(frozen=True)
class MandantKern:
    id: UUID
    name: str


async def mandant_kern_lookup(mandant_id: UUID) -> MandantKern | None:
    async with system_session(grund="impersonation: mandant laden") as session:
        zeile = (
            await session.execute(select(Mandant.id, Mandant.name).where(Mandant.id == mandant_id))
        ).one_or_none()
    return MandantKern(id=zeile.id, name=zeile.name) if zeile is not None else None


@asynccontextmanager
async def fehlerbericht_service_session() -> AsyncIterator[AsyncSession]:
    """Die Service-API (Bearer-Token, kein Nutzerkontext) liest Fehlerberichte
    ueber alle Mandanten -- das ist fachlich mandantenuebergreifend, nicht
    auf einen Mandanten zu reduzieren."""
    async with system_session(grund="fehlerberichte: service-token-schnittstelle") as session:
        yield session
