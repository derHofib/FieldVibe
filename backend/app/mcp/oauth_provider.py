"""OAuth-Authorization-Server fuer den MCP-Server (docs/MCP.md) ueber den
OAuthAuthorizationServerProvider des SDK.

Zustandslos soweit moeglich: Autorisierungsanfrage, Code, Access- und Refresh-Token
sind signierte JWTs mit mandant_id und tv im Payload. Der Token-Endpunkt braucht so
keinen mandantenuebergreifenden Lookup -- er oeffnet direkt tenant_session(mandant_id).
Serverseitiger Zustand (Einwilligung, Widerruf, Einmal-Einloesung, Refresh-Rotation)
liegt in ki_verbindungen."""
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select, update

from app.api.deps import token_version_gueltig
from app.core.config import get_settings
from app.core.security import (
    TokenType,
    create_mcp_access_token,
    create_mcp_anfrage_token,
    create_mcp_refresh_token,
    decode_token,
)
from app.db.session import tenant_session
from app.mcp.zugang import (
    ALLE_SCOPES,
    SCOPE_LESEN,
    SCOPE_SCHREIBEN,
    KiZugang,
    KiZugangAbgelehnt,
    pruefe_ki_zugang,
)
from app.models.ki_verbindung import KiClient, KiVerbindung

# zuletzt_genutzt_am nur einmal pro Minute schreiben, damit nicht jeder Aufruf eine Zeile aendert.
_NUTZUNG_TAKT_SEKUNDEN = 60


def resource_url() -> str:
    return get_settings().api_public_url.rstrip("/") + "/mcp"


class KiAuthorizationCode(AuthorizationCode):
    user_id: UUID
    mandant_id: UUID
    kv: UUID


class KiRefreshToken(RefreshToken):
    user_id: UUID
    mandant_id: UUID
    kv: UUID
    jti: str


class KiAccessToken(AccessToken):
    user_id: UUID
    mandant_id: UUID
    role: str
    account_typ_id: UUID | None = None
    tv: int
    kv: UUID


def anfrage_pruefen(anfrage: str) -> dict:
    """Gepruefte Claims der signierten Autorisierungsanfrage; ValueError bei ungueltig/abgelaufen."""
    try:
        payload = decode_token(anfrage)
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Die Anfrage ist abgelaufen. Bitte die Verbindung im KI-Assistenten neu starten.") from exc
    except jwt.PyJWTError as exc:
        raise ValueError("Ungültige Anfrage.") from exc
    if payload.get("type") != TokenType.MCP_ANFRAGE.value:
        raise ValueError("Ungültige Anfrage.")
    return payload


def _scopes_aus(payload: dict) -> list[str]:
    return [s for s in str(payload.get("scope", "")).split(" ") if s]


class FieldVibeOAuthProvider:
    # --- Client-Registrierung (Dynamic Client Registration) -------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with tenant_session(mandant_id=None) as session:
            zeile = await session.get(KiClient, client_id)
        return OAuthClientInformationFull.model_validate(zeile.client_info) if zeile else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.redirect_uris:
            raise RegistrationError(error="invalid_redirect_uri", error_description="redirect_uris fehlt")
        # Das SDK setzt ohne Angabe nur den Default-Scope; ein Client, der nichts angibt, soll
        # beide Scopes anfragen duerfen. Erteilt wird ohnehin nur, was der Nutzer ankreuzt.
        if not client_info.scope or client_info.scope.split(" ") == [SCOPE_LESEN]:
            client_info.scope = " ".join(ALLE_SCOPES)
        async with tenant_session(mandant_id=None) as session:
            session.add(
                KiClient(
                    client_id=client_info.client_id,
                    client_info=client_info.model_dump(mode="json", exclude_none=True),
                )
            )

    # --- Autorisierung: Browser-Login und Einwilligung im Frontend ------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        scopes = params.scopes or [SCOPE_LESEN]
        unbekannt = [s for s in scopes if s not in ALLE_SCOPES]
        if unbekannt:
            raise AuthorizeError(error="invalid_scope", error_description=f"Unbekannter Scope: {unbekannt[0]}")
        anfrage = create_mcp_anfrage_token(
            anfrage={
                "cid": client.client_id,
                "cn": client.client_name or client.client_id,
                "ru": str(params.redirect_uri),
                "rue": params.redirect_uri_provided_explicitly,
                "cc": params.code_challenge,
                "st": params.state,
                "sc": scopes,
            }
        )
        basis = get_settings().frontend_base_url.rstrip("/")
        return f"{basis}/ki-verbinden?anfrage={anfrage}"

    # --- Authorization Code ----------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> KiAuthorizationCode | None:
        try:
            p = decode_token(authorization_code)
            if p.get("type") != TokenType.MCP_CODE.value or p.get("cid") != client.client_id:
                return None
            return KiAuthorizationCode(
                code=authorization_code,
                scopes=_scopes_aus(p),
                expires_at=float(p["exp"]),
                client_id=p["cid"],
                code_challenge=p["cc"],
                redirect_uri=p["ru"],
                redirect_uri_provided_explicitly=bool(p.get("rue")),
                resource=resource_url(),
                subject=p["sub"],
                user_id=UUID(p["sub"]),
                mandant_id=UUID(p["mandant_id"]),
                kv=UUID(p["kv"]),
            )
        except (jwt.PyJWTError, KeyError, ValueError):
            return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: KiAuthorizationCode
    ) -> OAuthToken:
        mandant_id, kv = authorization_code.mandant_id, authorization_code.kv
        async with tenant_session(mandant_id=mandant_id) as session:
            # Atomar: nur der erste Aufruf loest den Code ein.
            eingeloest = await session.scalar(
                update(KiVerbindung)
                .where(
                    KiVerbindung.id == kv,
                    KiVerbindung.code_eingeloest_am.is_(None),
                    KiVerbindung.widerrufen_am.is_(None),
                    KiVerbindung.client_id == client.client_id,
                )
                .values(code_eingeloest_am=datetime.now(timezone.utc))
                .returning(KiVerbindung.id)
            )
            if eingeloest is not None:
                try:
                    await self._tv_pruefen(authorization_code.user_id, mandant_id, authorization_code.code)
                    zugang = await pruefe_ki_zugang(
                        session, user_id=authorization_code.user_id, mandant_id=mandant_id
                    )
                except (KiZugangAbgelehnt, TokenError) as exc:
                    await self._widerrufen_in(session, kv)
                    ablehnung = exc
                else:
                    verbindung = await session.get(KiVerbindung, kv)
                    return self._ausstellen(zugang, verbindung)
        if eingeloest is None:
            # Mehrfach eingeloester Code: ein Angreifer koennte den Code abgefangen haben,
            # also die daraus entstandene Verbindung vorsorglich sperren (RFC 6749 §4.1.2).
            await self._widerrufen(mandant_id, kv)
            raise TokenError(error="invalid_grant", error_description="authorization code already used")
        raise TokenError(error="invalid_grant", error_description=_beschreibung(ablehnung))

    # --- Refresh ---------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> KiRefreshToken | None:
        try:
            p = decode_token(refresh_token)
            if p.get("type") != TokenType.MCP_REFRESH.value or p.get("cid") != client.client_id:
                return None
            return KiRefreshToken(
                token=refresh_token,
                client_id=p["cid"],
                scopes=_scopes_aus(p),
                expires_at=int(p["exp"]),
                resource=resource_url(),
                subject=p["sub"],
                user_id=UUID(p["sub"]),
                mandant_id=UUID(p["mandant_id"]),
                kv=UUID(p["kv"]),
                jti=p["jti"],
            )
        except (jwt.PyJWTError, KeyError, ValueError):
            return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: KiRefreshToken, scopes: list[str]
    ) -> OAuthToken:
        mandant_id, kv = refresh_token.mandant_id, refresh_token.kv
        replay = False
        async with tenant_session(mandant_id=mandant_id) as session:
            # FOR UPDATE: zwei gleichzeitige Refreshs desselben Tokens duerfen nicht beide gelingen.
            verbindung = await session.scalar(
                select(KiVerbindung).where(KiVerbindung.id == kv).with_for_update()
            )
            if (
                verbindung is None
                or verbindung.widerrufen_am is not None
                or verbindung.user_id != refresh_token.user_id
            ):
                raise TokenError(error="invalid_grant", error_description="refresh token revoked")
            if verbindung.refresh_jti != refresh_token.jti:
                replay = True
                await self._widerrufen_in(session, kv)
            else:
                try:
                    await self._tv_pruefen(refresh_token.user_id, mandant_id, refresh_token.token)
                    zugang = await pruefe_ki_zugang(session, user_id=refresh_token.user_id, mandant_id=mandant_id)
                except (KiZugangAbgelehnt, TokenError) as exc:
                    await self._widerrufen_in(session, kv)
                    ablehnung = exc
                else:
                    gewaehrt = [s for s in verbindung.scopes if s in scopes]
                    if SCOPE_LESEN not in gewaehrt:
                        gewaehrt.insert(0, SCOPE_LESEN)
                    return self._ausstellen(zugang, verbindung, gewaehrt)
        if replay:
            raise TokenError(error="invalid_grant", error_description="refresh token already used")
        raise TokenError(error="invalid_grant", error_description=_beschreibung(ablehnung))

    # --- Access-Token pruefen (jeder MCP-Aufruf) --------------------------------

    async def load_access_token(self, token: str) -> KiAccessToken | None:
        try:
            p = decode_token(token)
            if p.get("type") != TokenType.MCP.value:
                return None
            user_id, mandant_id, kv = UUID(p["sub"]), UUID(p["mandant_id"]), UUID(p["kv"])
            tv = p["tv"]
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            return None
        try:
            await token_version_gueltig("user", user_id, p, mandant_id=mandant_id, tv_pflicht=True)
        except HTTPException:
            return None

        async with tenant_session(mandant_id=mandant_id) as session:
            verbindung = await session.get(KiVerbindung, kv)
            if verbindung is None or verbindung.widerrufen_am is not None or verbindung.user_id != user_id:
                return None
            try:
                zugang = await pruefe_ki_zugang(session, user_id=user_id, mandant_id=mandant_id)
            except KiZugangAbgelehnt:
                return None
            # Nie mehr als eingewilligt, und Schreiben nur, solange das Recht noch besteht.
            scopes = [s for s in _scopes_aus(p) if s in verbindung.scopes]
            if not zugang.schreiben_erlaubt:
                scopes = [s for s in scopes if s != SCOPE_SCHREIBEN]
            if SCOPE_LESEN not in scopes:
                return None
            jetzt = datetime.now(timezone.utc)
            letzte = verbindung.zuletzt_genutzt_am
            if letzte is None or (jetzt - letzte).total_seconds() >= _NUTZUNG_TAKT_SEKUNDEN:
                verbindung.zuletzt_genutzt_am = jetzt
            user = zugang.user
            return KiAccessToken(
                token=token,
                client_id=verbindung.client_id,
                scopes=scopes,
                expires_at=int(p["exp"]),
                resource=resource_url(),
                subject=str(user_id),
                user_id=user_id,
                mandant_id=mandant_id,
                role=user.role,
                account_typ_id=user.account_typ_id,
                tv=tv,
                kv=kv,
            )

    # --- Widerruf ----------------------------------------------------------------

    async def revoke_token(self, token: KiAccessToken | KiRefreshToken) -> None:
        await self._widerrufen(token.mandant_id, token.kv)

    # --- Helfer ------------------------------------------------------------------

    async def _tv_pruefen(self, user_id: UUID, mandant_id: UUID, token: str) -> None:
        """Code und Refresh-Token tragen tv; ein Widerruf des Kontos (Abmelden ueberall,
        Passwortwechsel, Sperre) macht sie ungueltig."""
        try:
            await token_version_gueltig("user", user_id, decode_token(token), mandant_id=mandant_id, tv_pflicht=True)
        except HTTPException as exc:
            raise TokenError(error="invalid_grant", error_description="token revoked") from exc

    def _ausstellen(
        self, zugang: KiZugang, verbindung: KiVerbindung, scopes: list[str] | None = None
    ) -> OAuthToken:
        user = zugang.user
        scopes = scopes if scopes is not None else list(verbindung.scopes)
        if not zugang.schreiben_erlaubt:
            scopes = [s for s in scopes if s != SCOPE_SCHREIBEN]
        jti = uuid4().hex
        verbindung.refresh_jti = jti
        zugriff, sekunden = create_mcp_access_token(
            subject=user.id,
            role=user.role,
            mandant_id=verbindung.mandant_id,
            token_version=user.token_version,
            account_typ_id=user.account_typ_id,
            ki_verbindung_id=verbindung.id,
            scopes=scopes,
        )
        refresh = create_mcp_refresh_token(
            subject=user.id,
            role=user.role,
            mandant_id=verbindung.mandant_id,
            token_version=user.token_version,
            account_typ_id=user.account_typ_id,
            ki_verbindung_id=verbindung.id,
            scopes=scopes,
            client_id=verbindung.client_id,
            jti=jti,
        )
        return OAuthToken(
            access_token=zugriff,
            expires_in=sekunden,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def _widerrufen_in(self, session, kv: UUID) -> None:
        await session.execute(
            update(KiVerbindung)
            .where(KiVerbindung.id == kv, KiVerbindung.widerrufen_am.is_(None))
            .values(widerrufen_am=datetime.now(timezone.utc))
        )

    async def _widerrufen(self, mandant_id: UUID, kv: UUID) -> None:
        async with tenant_session(mandant_id=mandant_id) as session:
            await self._widerrufen_in(session, kv)


def _beschreibung(ausnahme: Exception) -> str:
    if isinstance(ausnahme, TokenError):
        return ausnahme.error_description or "invalid grant"
    return getattr(ausnahme, "detail", "access denied")
