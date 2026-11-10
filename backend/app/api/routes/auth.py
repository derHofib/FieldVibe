import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.deps import AuthContext, get_current_user, get_current_user_mfa_einrichtung
from app.core.config import get_settings
from app.core import refresh_cookie
from app.core.rate_limit import (
    client_ip,
    login_account_limiter,
    login_ip_limiter,
    password_reset_ip_limiter,
)
from app.core.security import (
    TokenType,
    create_user_password_reset_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import (
    MIN_PASSWORT_LAENGE,
    CurrentUser,
    LoginRequest,
    LoginResponse,
    PasswortAendernRequest,
    PasswortVergessenRequest,
    PasswortZuruecksetzenRequest,
    UserRefreshRequest,
    RegistrierenRequest,
    TokenPair,
)
from app.schemas.user import BottomNavUpdate, OfficeNavUpdate
from app.services.audit_service import log_action
from app.services.auth_service import authenticate, token_paar_fuer
from app.services import mfa_service
from app.services.email_service import EmailNichtKonfiguriert, send_email
from app.services.token_widerruf_service import widerrufe_tokens
from app.services.einladung_service import als_angenommen_markieren, resolve_offene_einladung
from app.services import berechtigung_service
from app.services.berechtigung_service import effektive_rechte_gecacht
from app.services.organigramm_sync_service import besetzung_pflegen

router = APIRouter(prefix="/api/auth", tags=["auth"])
_settings = get_settings()
_logger = logging.getLogger("app.auth")


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    ip_key = client_ip(request)
    account_key = body.email.strip().lower()
    login_ip_limiter.check(ip_key)
    login_account_limiter.check(account_key)
    try:
        result = await authenticate(body.email, body.password)
    except HTTPException:
        login_ip_limiter.record_failure(ip_key)
        login_account_limiter.record_failure(account_key)
        raise
    # Bei aktiver MFA ist erst das Passwort geprueft: die Zaehler werden erst
    # nach dem zweiten Faktor geleert (mfa.verifizieren). Sonst koennte, wer
    # das Passwort kennt, die Code-Fehlversuche durch erneutes Anmelden
    # beliebig oft zuruecksetzen.
    if not result.mfa_erforderlich:
        login_ip_limiter.record_success(ip_key)
        login_account_limiter.record_success(account_key)
        paar = refresh_cookie.paar_mit_cookie(
            request,
            response,
            TokenPair(access_token=result.access_token, refresh_token=result.refresh_token),
        )
        return LoginResponse(access_token=paar.access_token, refresh_token=paar.refresh_token)
    return result


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: Request, response: Response, body: UserRefreshRequest | None = None
) -> TokenPair:
    # Body-Token nur in der Uebergangsfrist (alte PWA-Bundles); sonst Cookie,
    # und dann zusaetzlich Origin-Pruefung gegen CSRF.
    token = body.refresh_token if body and refresh_cookie.body_token_erlaubt() else None
    if token is None:
        token = request.cookies.get(refresh_cookie.COOKIE_NAME)
        if token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Refresh-Token")
        refresh_cookie.origin_pruefen(request)
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Refresh-Token"
        ) from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Refresh-Token"
        )

    async with system_session() as session:
        result = await session.execute(select(User).where(User.id == payload["sub"]))
        user = result.scalar_one_or_none()
        if user is None or not user.aktiv:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig"
            )
        # Fehlender Claim (Altbestand) gilt als 0, siehe token_version_gueltig.
        if payload.get("tv", 0) != user.token_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token widerrufen"
            )
        mandant = None
        if user.mandant_id is not None:
            mandant = await session.get(Mandant, user.mandant_id)
            if mandant is None or mandant.status != "aktiv":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Mandant ist nicht aktiv"
                )

        return refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user, mandant))


@router.post("/ueberall-abmelden", status_code=status.HTTP_204_NO_CONTENT)
async def ueberall_abmelden(response: Response, auth: AuthContext = Depends(get_current_user)) -> None:
    """Entwertet alle Tokens des eigenen Accounts (alle Geraete, inkl. des
    aufrufenden). system_session wie bei /me: bei Impersonation ist die
    Zeile des Super-Admins unter der Mandanten-RLS nicht sichtbar -- dann
    trifft der Widerruf bewusst den Super-Admin-Account selbst."""
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig")
        await widerrufe_tokens(session, user)
        await log_action(
            session,
            aktion="logout_alle_geraete",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
    refresh_cookie.loesche_refresh_cookie(response)


@router.post("/abmelden", status_code=status.HTTP_204_NO_CONTENT)
async def abmelden(request: Request, response: Response) -> None:
    """Loescht nur das Refresh-Cookie dieses Browsers (keine Authentifizierung
    noetig: ohne Cookie ist nichts zu tun). Andere Geraete bleiben angemeldet,
    dafuer gibt es /ueberall-abmelden."""
    await _abmeldung_protokollieren(request)
    refresh_cookie.loesche_refresh_cookie(response)


async def _abmeldung_protokollieren(request: Request) -> None:
    """Den Nutzer nur aus einem gueltigen Refresh-Cookie ableiten; alles andere
    (kein Cookie, abgelaufen, fremd) ist kein protokollierbares Ereignis und
    darf das Abmelden nie verhindern."""
    token = request.cookies.get(refresh_cookie.COOKIE_NAME)
    if not token:
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != TokenType.REFRESH.value:
            return
        async with system_session() as session:
            user = await session.get(User, payload["sub"])
            if user is None or user.mandant_id is None:
                return
            await log_action(
                session,
                aktion="logout",
                mandant_id=user.mandant_id,
                actor_user_id=user.id,
                entity_type="user",
                entity_id=user.id,
            )
    except Exception:
        _logger.warning("Abmeldung konnte nicht protokolliert werden", exc_info=True)


@router.post("/passwort-vergessen", status_code=status.HTTP_202_ACCEPTED)
async def passwort_vergessen(body: PasswortVergessenRequest, request: Request) -> None:
    """Antwortet immer mit 202 (Enumeration-Schutz, Begruendung wie beim
    Kundenportal -- siehe kundenportal_auth.passwort_vergessen). Das Rate-
    Limit zaehlt deshalb jeden Aufruf pro IP, nicht nur Fehlschlaege."""
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)
    password_reset_ip_limiter.record_failure(ip_key)

    async with system_session() as session:
        result = await session.execute(select(User).where(func.lower(User.email) == body.email))
        user = result.scalar_one_or_none()
        if user is None or not user.aktiv:
            return None
        if user.mandant_id is not None:
            # Wie beim Login: fuer einen deaktivierten Mandanten gibt es kein
            # nutzbares Konto, also auch keinen Link.
            mandant = await session.get(Mandant, user.mandant_id)
            if mandant is None or mandant.status != "aktiv":
                return None

        token = create_user_password_reset_token(user_id=user.id, token_version=user.token_version)
        reset_link = f"{_settings.frontend_base_url}/passwort-zuruecksetzen?token={token}"
        try:
            await send_email(
                session,
                user.mandant_id,
                to=user.email,
                subject="Passwort zurücksetzen",
                body=(
                    f"Hallo {user.name},\n\n"
                    "für Ihr FieldVibe-Konto wurde ein Passwort-Reset angefordert. "
                    f"Falls Sie das waren, setzen Sie hier ein neues Passwort:\n{reset_link}\n\n"
                    f"Der Link ist {_settings.user_reset_token_expire_minutes} Minuten gültig und "
                    "kann nur einmal verwendet werden. "
                    "Falls Sie das nicht angefordert haben, ignorieren Sie diese E-Mail."
                ),
            )
        except EmailNichtKonfiguriert:
            # Weder Mandanten- noch Plattform-SMTP: ein Administrator muss das
            # Passwort direkt setzen. Kein Fehler nach aussen (Enumeration-Schutz).
            _logger.warning("Passwort-Reset angefordert, aber kein SMTP konfiguriert")
        except Exception:
            # Zustellungsfehler darf nie zu einem 500 werden, sonst waere die
            # Existenz des Kontos wieder ablesbar.
            _logger.exception("Passwort-Reset-Mail konnte nicht verschickt werden")

    return None


@router.post("/passwort-zuruecksetzen", status_code=status.HTTP_204_NO_CONTENT)
async def passwort_zuruecksetzen(body: PasswortZuruecksetzenRequest, request: Request) -> None:
    ip_key = client_ip(request)
    password_reset_ip_limiter.check(ip_key)

    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError as exc:
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Reset-Link ist ungültig oder abgelaufen"
        ) from exc

    if payload.get("type") != TokenType.USER_PASSWORD_RESET.value:
        password_reset_ip_limiter.record_failure(ip_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Reset-Token")

    async with system_session() as session:
        user = await session.get(User, payload["sub"])
        # Einmalverwendung: der Link traegt die token_version von seiner
        # Ausstellung; jeder Widerruf (auch dieser Reset selbst) macht ihn ungueltig.
        if user is None or not user.aktiv or payload.get("tv") != user.token_version:
            password_reset_ip_limiter.record_failure(ip_key)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Reset-Link ist ungültig oder abgelaufen"
            )
        user.password_hash = hash_password(body.new_password)
        await widerrufe_tokens(session, user)
        await log_action(
            session,
            aktion="passwort_zurueckgesetzt",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
    password_reset_ip_limiter.record_success(ip_key)
    return None


@router.post("/passwort-aendern", response_model=TokenPair)
async def passwort_aendern(
    body: PasswortAendernRequest, request: Request, response: Response, auth: AuthContext = Depends(get_current_user)
) -> TokenPair:
    """Alle bisherigen Tokens werden widerrufen (andere Geraete sind damit
    abgemeldet); die aufrufende Sitzung bekommt direkt ein frisches Paar, so
    dass sie ohne erneute Anmeldung weiterlaeuft -- deshalb 200 + TokenPair
    statt 204."""
    if auth.impersonated_by is not None:
        # sub ist hier der echte Super-Admin; sein Passwort darf ueber ein
        # Impersonation-Token nicht geaendert werden.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Während der Impersonation nicht möglich"
        )
    ip_key = client_ip(request)
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None or not user.aktiv:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig")

        # Dieselben Limiter und derselbe Account-Schluessel wie /login: ein
        # gestohlenes Zugriffstoken taugt so nicht zum Durchprobieren des
        # alten Passworts, und Login-/Aendern-Fehlversuche zaehlen zusammen.
        account_key = user.email.strip().lower()
        login_ip_limiter.check(ip_key)
        login_account_limiter.check(account_key)
        if not verify_password(body.old_password, user.password_hash):
            login_ip_limiter.record_failure(ip_key)
            login_account_limiter.record_failure(account_key)
            # 400 statt 401/403: das Frontend behandelt 401 als abgelaufene
            # Sitzung, und das Token selbst ist ja gueltig.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Aktuelles Passwort ist falsch"
            )
        login_ip_limiter.record_success(ip_key)
        login_account_limiter.record_success(account_key)
        if body.new_password == body.old_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Das neue Passwort muss sich vom aktuellen unterscheiden",
            )

        user.password_hash = hash_password(body.new_password)
        await widerrufe_tokens(session, user)
        await log_action(
            session,
            aktion="passwort_geaendert",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        return refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user))


@router.post("/registrieren", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def registrieren(body: RegistrierenRequest, request: Request, response: Response) -> TokenPair:
    """Schliesst eine Mitarbeiter-Einladung ab: legt den User-Account mit
    dem selbst gewaehlten Passwort an und loggt direkt ein."""
    if len(body.password) < MIN_PASSWORT_LAENGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen haben",
        )
    async with system_session() as session:
        einladung = await resolve_offene_einladung(session, body.token, erwartete_art="mitarbeiter")

        user = User(
            mandant_id=einladung.mandant_id,
            email=einladung.email,
            password_hash=hash_password(body.password),
            role=einladung.rolle,
            account_typ_id=einladung.account_typ_id,
            name=body.name,
        )
        session.add(user)
        await session.flush()
        await besetzung_pflegen(session, user, neu=True)
        await als_angenommen_markieren(session, einladung)

        return refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user))


@router.get("/me", response_model=CurrentUser)
async def me(auth: AuthContext = Depends(get_current_user_mfa_einrichtung)) -> CurrentUser:
    # Looked up via system_session deliberately: during impersonation the
    # token's `sub` is the real super_admin's user id, whose own row has
    # mandant_id = NULL and would be invisible under the impersonated
    # tenant's RLS scope. This lookup is read-only, keyed by the token's own
    # verified subject, and never returns another account's data.
    async with system_session() as session:
        result = await session.execute(select(User).where(User.id == auth.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
            )

        mandant_name: str | None = None
        deaktivierte_module: list[str] = []
        mandant = None
        if auth.mandant_id is not None:
            mandant = await session.get(Mandant, auth.mandant_id)
            if mandant is not None:
                mandant_name = mandant.name
                deaktivierte_module = mandant.deaktivierte_module

        account_typ_name: str | None = None
        if auth.account_typ_id is not None:
            account_typ = await session.get(AccountTyp, auth.account_typ_id)
            if account_typ is not None:
                account_typ_name = account_typ.name

        # Alles aus der Rechte-Engine (aktive Besetzungen), ein Aufloesungslauf.
        effektiv = await effektive_rechte_gecacht(session, user_id=auth.user_id, rolle=auth.role)
        nur_zugewiesene_kunden = await berechtigung_service.ist_auf_zugewiesene_kunden_beschraenkt(
            session, user_id=auth.user_id, rolle=auth.role
        )
        selbst_uebernehmen = effektiv.flag(berechtigung_service.FLAG_SELBST_UEBERNEHMEN)
        zeiten_buchen = effektiv.flag(berechtigung_service.FLAG_ZEITEN_BUCHEN)
        abwesenheiten_verwalten = effektiv.flag(berechtigung_service.FLAG_ABWESENHEITEN_VERWALTEN)
        # mandant_admin/super_admin/loesch_* haben alle Rechte (kommen an
        # require_recht() immer vorbei, siehe app/api/deps.py) -- die Matrix
        # spiegelt das 1:1, damit das Frontend nicht nach der Rolle unterscheiden muss.
        rechte = effektiv.als_matrix()
        rechte_scopes = effektiv.als_scopes()

        # Defensiv statt user.bottom_nav_items direkt durchzureichen: falls
        # dort noch ein Wert aus der frueheren, flachen Listen-Form steckt
        # (vor der Aufteilung in links/rotunde), wuerde die Validierung sonst
        # fehlschlagen und /me fuer diesen Nutzer komplett blockieren --
        # stattdessen faellt das Frontend dann einfach auf die Standardauswahl
        # zurueck, statt den Login zu verhindern.
        bottom_nav_items: BottomNavUpdate | None = None
        if isinstance(user.bottom_nav_items, dict):
            try:
                bottom_nav_items = BottomNavUpdate.model_validate(user.bottom_nav_items)
            except ValidationError:
                bottom_nav_items = None

        office_nav_items: OfficeNavUpdate | None = None
        if isinstance(user.office_nav_items, list):
            office_nav_items = OfficeNavUpdate(items=user.office_nav_items)

        return CurrentUser(
            id=user.id,
            mandant_id=auth.mandant_id,
            role=auth.role,
            account_typ_id=auth.account_typ_id,
            account_typ_name=account_typ_name,
            nur_zugewiesene_kunden=nur_zugewiesene_kunden,
            darf_vorgaenge_selbst_uebernehmen=selbst_uebernehmen,
            darf_zeiten_buchen=zeiten_buchen,
            darf_abwesenheiten_verwalten=abwesenheiten_verwalten,
            name=user.name,
            email=user.email,
            impersonated_by=auth.impersonated_by,
            mfa_aktiv=user.mfa_aktiv,
            mfa_pflicht=mfa_service.mandant_verlangt_mfa(mandant),
            mfa_einrichtung_erforderlich=auth.mfa_einrichtung,
            mandant_name=mandant_name,
            deaktivierte_module=deaktivierte_module,
            bottom_nav_items=bottom_nav_items,
            office_nav_items=office_nav_items,
            rechte=rechte,
            rechte_scopes=rechte_scopes,
        )
