import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import AuthContext, get_current_user, get_current_user_mfa_einrichtung
from app.core import refresh_cookie
from app.core.rate_limit import client_ip, login_account_limiter, login_ip_limiter
from app.core.security import TokenType, decode_token, verify_password
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import TokenPair
from app.schemas.mfa import (
    MfaAktiviert,
    MfaCodeRequest,
    MfaEinrichtung,
    MfaPasswortCodeRequest,
    MfaStatus,
    MfaVerifizierenRequest,
    MfaWiederherstellungscodes,
)
from app.services import mfa_service
from app.services.audit_service import log_action, login_fehlschlag_protokollieren
from app.services.auth_service import token_paar_fuer
from app.services.mfa_service import MfaFehler
from app.services.token_widerruf_service import widerrufe_tokens

router = APIRouter(prefix="/api/auth/mfa", tags=["mfa"])

_CODE_UNGUELTIG = "Der Code ist ungültig oder abgelaufen."


def _fehler(exc: MfaFehler) -> HTTPException:
    # 400 statt 401/403: das Frontend behandelt 401 als abgelaufene Sitzung.
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _eigener_user(session, auth: AuthContext) -> User:
    """Zeile des Token-Subjects mit Zeilensperre (Replay-/Doppelverbrauch-
    Schutz). system_session wie bei /passwort-aendern: bei Impersonation waere
    die Zeile des Super-Admins unter der Mandanten-RLS unsichtbar -- und MFA-
    Aenderungen am echten Account sind waehrend der Impersonation ohnehin tabu."""
    if auth.impersonated_by is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Während der Impersonation nicht möglich"
        )
    user = (
        await session.execute(select(User).where(User.id == auth.user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None or not user.aktiv:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig")
    return user


def _limiter_pruefen(request: Request, user: User) -> tuple[str, str]:
    """Code-Versuche teilen sich Limiter und Account-Schluessel mit /login und
    /passwort-aendern: Fehlversuche aller drei zaehlen zusammen."""
    ip_key = client_ip(request)
    account_key = user.email.strip().lower()
    login_ip_limiter.check(ip_key)
    login_account_limiter.check(account_key)
    return ip_key, account_key


def _fehlversuch(ip_key: str, account_key: str) -> None:
    login_ip_limiter.record_failure(ip_key)
    login_account_limiter.record_failure(account_key)


def _erfolg(ip_key: str, account_key: str) -> None:
    login_ip_limiter.record_success(ip_key)
    login_account_limiter.record_success(account_key)


async def _mandant_von(session, user: User) -> Mandant | None:
    return await session.get(Mandant, user.mandant_id) if user.mandant_id is not None else None


@router.get("/status", response_model=MfaStatus)
async def mfa_status(auth: AuthContext = Depends(get_current_user_mfa_einrichtung)) -> MfaStatus:
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig")
        mandant = await _mandant_von(session, user)
        return MfaStatus(
            aktiv=user.mfa_aktiv,
            pflicht=mfa_service.mandant_verlangt_mfa(mandant),
            einrichtung_erforderlich=mfa_service.einrichtung_erforderlich(user, mandant),
            wiederherstellungscodes_uebrig=mfa_service.wiederherstellungscodes_uebrig(user),
            aktiviert_am=user.mfa_aktiviert_am,
        )


@router.post("/einrichten", response_model=MfaEinrichtung)
async def mfa_einrichten(auth: AuthContext = Depends(get_current_user_mfa_einrichtung)) -> MfaEinrichtung:
    """Startet die Einrichtung: erzeugt ein neues, noch unbestaetigtes Secret
    (ein frueheres unbestaetigtes wird ersetzt). Aktiv wird MFA erst mit
    /bestaetigen."""
    async with system_session() as session:
        user = await _eigener_user(session, auth)
        try:
            secret = mfa_service.einrichtung_beginnen(user)
        except MfaFehler as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        uri = mfa_service.otpauth_uri(secret, user.email)
        return MfaEinrichtung(
            secret=secret, otpauth_uri=uri, qr_svg_data_uri=mfa_service.qr_svg_data_uri(uri)
        )


@router.post("/bestaetigen", response_model=MfaAktiviert)
async def mfa_bestaetigen(
    body: MfaCodeRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_current_user_mfa_einrichtung),
) -> MfaAktiviert:
    """Schliesst die Einrichtung mit einem gueltigen Code ab. Alle bisherigen
    Tokens werden widerrufen (andere Geraete/gestohlene Sitzungen verlieren den
    Zugang); die aufrufende Sitzung bekommt direkt ein frisches Paar."""
    async with system_session() as session:
        user = await _eigener_user(session, auth)
        ip_key, account_key = _limiter_pruefen(request, user)
        try:
            codes = mfa_service.einrichtung_bestaetigen(user, body.code)
        except MfaFehler as exc:
            _fehlversuch(ip_key, account_key)
            raise _fehler(exc) from exc
        _erfolg(ip_key, account_key)
        await widerrufe_tokens(session, user)
        await log_action(
            session,
            aktion="mfa_aktiviert",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        paar = refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user))
        return MfaAktiviert(
            access_token=paar.access_token, refresh_token=paar.refresh_token, wiederherstellungscodes=codes
        )


async def _passwort_und_code_pruefen(
    session, request: Request, auth: AuthContext, body: MfaPasswortCodeRequest
) -> User:
    user = await _eigener_user(session, auth)
    ip_key, account_key = _limiter_pruefen(request, user)
    if not user.mfa_aktiv:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist nicht aktiv.")
    if not verify_password(body.password, user.password_hash):
        _fehlversuch(ip_key, account_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aktuelles Passwort ist falsch")
    if mfa_service.code_verbrauchen(user, body.code) is None:
        _fehlversuch(ip_key, account_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_CODE_UNGUELTIG)
    _erfolg(ip_key, account_key)
    return user


@router.post("/deaktivieren", response_model=TokenPair)
async def mfa_deaktivieren(
    body: MfaPasswortCodeRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_current_user),
) -> TokenPair:
    """Nur mit Passwort UND Code (bzw. Wiederherstellungscode). Ist MFA fuer den
    Mandanten Pflicht, bleibt sie an -- sonst stuende der Account sofort wieder
    vor der Einrichtung."""
    async with system_session() as session:
        user = await _passwort_und_code_pruefen(session, request, auth, body)
        if mfa_service.mandant_verlangt_mfa(await _mandant_von(session, user)) and user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ihr Betrieb schreibt MFA vor – sie kann nicht deaktiviert werden.",
            )
        mfa_service.zuruecksetzen(user)
        await widerrufe_tokens(session, user)
        await log_action(
            session,
            aktion="mfa_deaktiviert",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        return refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user))


@router.post("/wiederherstellungscodes", response_model=MfaWiederherstellungscodes)
async def mfa_wiederherstellungscodes_erneuern(
    body: MfaPasswortCodeRequest, request: Request, auth: AuthContext = Depends(get_current_user)
) -> MfaWiederherstellungscodes:
    """Ersetzt alle Wiederherstellungscodes durch zehn neue (die alten werden
    ungueltig). Wie das Deaktivieren nur mit Passwort und Code."""
    async with system_session() as session:
        user = await _passwort_und_code_pruefen(session, request, auth, body)
        codes = mfa_service.neue_wiederherstellungscodes(user)
        await log_action(
            session,
            aktion="mfa_wiederherstellungscodes_erneuert",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        return MfaWiederherstellungscodes(wiederherstellungscodes=codes)


@router.post("/verifizieren", response_model=TokenPair)
async def mfa_verifizieren(body: MfaVerifizierenRequest, request: Request, response: Response) -> TokenPair:
    """Zweiter Login-Schritt: tauscht den MFA-Token aus /login plus Code (TOTP
    oder Wiederherstellungscode) gegen das Token-Paar."""
    ungueltig = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Anmeldung abgelaufen. Bitte erneut anmelden."
    )
    try:
        payload = decode_token(body.mfa_token)
    except jwt.PyJWTError as exc:
        raise ungueltig from exc
    if payload.get("type") != TokenType.USER_MFA.value:
        raise ungueltig

    fehlschlag: list[tuple] = []
    try:
        return await _mfa_verifizieren_pruefen(body, request, response, payload, fehlschlag)
    except HTTPException:
        if fehlschlag:
            await login_fehlschlag_protokollieren(
                mandant_id=fehlschlag[0][0], user_id=fehlschlag[0][1], grund="mfa_code_falsch"
            )
        raise


async def _mfa_verifizieren_pruefen(
    body: MfaVerifizierenRequest, request: Request, response: Response, payload: dict, fehlschlag: list
) -> TokenPair:
    ungueltig = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Anmeldung abgelaufen. Bitte erneut anmelden."
    )
    async with system_session() as session:
        user = (
            await session.execute(select(User).where(User.id == payload["sub"]).with_for_update())
        ).scalar_one_or_none()
        if (
            user is None
            or not user.aktiv
            or not user.mfa_aktiv
            or payload.get("tv", 0) != user.token_version
        ):
            raise ungueltig
        mandant = await _mandant_von(session, user)
        if user.mandant_id is not None and (mandant is None or mandant.status != "aktiv"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mandant ist nicht aktiv")

        ip_key, account_key = _limiter_pruefen(request, user)
        art = mfa_service.code_verbrauchen(user, body.code)
        if art is None:
            _fehlversuch(ip_key, account_key)
            # Erst nach dem Rollback protokollieren: die Zeile ist hier per FOR UPDATE
            # gesperrt, ein Eintrag in zweiter Transaktion (FK auf users) wuerde warten.
            fehlschlag.append((user.mandant_id, user.id))
            # Sonst nichts zu persistieren: die Transaktion wird mit der Exception verworfen;
            # 401 fuer ein falsches Passwort-Aequivalent, wie bei /login.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_CODE_UNGUELTIG)
        _erfolg(ip_key, account_key)
        await log_action(
            session,
            aktion="login",
            mandant_id=user.mandant_id,
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            payload={"mfa": art},
        )
        if art == "wiederherstellung":
            await log_action(
                session,
                aktion="mfa_wiederherstellungscode_verwendet",
                mandant_id=user.mandant_id,
                actor_user_id=user.id,
                entity_type="user",
                entity_id=user.id,
                payload={"codes_uebrig": mfa_service.wiederherstellungscodes_uebrig(user)},
            )
        return refresh_cookie.paar_mit_cookie(request, response, await token_paar_fuer(session, user, mandant))
