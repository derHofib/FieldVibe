from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.core.security import decrypt_secret, encrypt_secret
from app.models.mail_account import MailAccount
from app.schemas.mail_account import (
    MailAccountCreate,
    MailAccountRead,
    MailAccountUpdate,
    MailAccountVerbindungTest,
)
from app.services.mail_service import (
    ImapZugang,
    MailVerbindungFehler,
    SmtpZugang,
    pruefe_imap_verbindung,
    pruefe_smtp_verbindung,
)

router = APIRouter(
    prefix="/api/mail-accounts",
    tags=["mail-accounts"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_module("postfach")),
    ],
)


async def _pruefe_verbindung(
    *,
    imap_host: str,
    imap_port: int,
    imap_verschluesselung: str,
    imap_benutzername: str,
    smtp_host: str,
    smtp_port: int,
    smtp_verschluesselung: str,
    smtp_benutzername: str,
    passwort: str,
) -> None:
    await anyio.to_thread.run_sync(
        pruefe_imap_verbindung,
        ImapZugang(
            host=imap_host,
            port=imap_port,
            verschluesselung=imap_verschluesselung,
            benutzername=imap_benutzername,
            passwort=passwort,
        ),
    )
    await anyio.to_thread.run_sync(
        pruefe_smtp_verbindung,
        SmtpZugang(
            host=smtp_host,
            port=smtp_port,
            verschluesselung=smtp_verschluesselung,
            benutzername=smtp_benutzername,
            passwort=passwort,
        ),
    )


@router.post("/test-verbindung", status_code=status.HTTP_204_NO_CONTENT)
async def test_verbindung(body: MailAccountVerbindungTest) -> None:
    try:
        await _pruefe_verbindung(
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            imap_verschluesselung=body.imap_verschluesselung,
            imap_benutzername=body.imap_benutzername,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_verschluesselung=body.smtp_verschluesselung,
            smtp_benutzername=body.smtp_benutzername,
            passwort=body.passwort,
        )
    except MailVerbindungFehler as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[MailAccountRead])
async def list_mail_accounts(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MailAccount]:
    result = await session.execute(
        select(MailAccount).where(MailAccount.user_id == auth.user_id).order_by(MailAccount.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=MailAccountRead, status_code=status.HTTP_201_CREATED)
async def create_mail_account(
    body: MailAccountCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailAccount:
    try:
        await _pruefe_verbindung(
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            imap_verschluesselung=body.imap_verschluesselung,
            imap_benutzername=body.imap_benutzername,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_verschluesselung=body.smtp_verschluesselung,
            smtp_benutzername=body.smtp_benutzername,
            passwort=body.passwort,
        )
    except MailVerbindungFehler as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    account = MailAccount(
        mandant_id=auth.mandant_id,
        user_id=auth.user_id,
        name=body.name,
        email_adresse=body.email_adresse,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        imap_verschluesselung=body.imap_verschluesselung,
        imap_benutzername=body.imap_benutzername,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_verschluesselung=body.smtp_verschluesselung,
        smtp_benutzername=body.smtp_benutzername,
        passwort_verschluesselt=encrypt_secret(body.passwort),
        signatur=body.signatur,
        aktiv=body.aktiv,
    )
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse ist bereits ein Postfach hinterlegt",
        ) from exc
    await session.refresh(account)
    return account


async def _get_own_account(session: AsyncSession, auth: AuthContext, account_id: UUID) -> MailAccount:
    account = await session.get(MailAccount, account_id)
    if account is None or account.user_id != auth.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postfach nicht gefunden")
    return account


@router.patch("/{account_id}", response_model=MailAccountRead)
async def update_mail_account(
    account_id: UUID,
    body: MailAccountUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MailAccount:
    account = await _get_own_account(session, auth, account_id)

    changes = body.model_dump(exclude_unset=True, exclude={"passwort"})

    # Ein evtl. mitgeschicktes neues Passwort erst pruefen, bevor irgendwas
    # gespeichert wird -- inklusive der bereits gespeicherten Werte fuer
    # Felder, die in diesem Update nicht mitgeschickt wurden.
    if body.passwort is not None:
        try:
            await _pruefe_verbindung(
                imap_host=changes.get("imap_host", account.imap_host),
                imap_port=changes.get("imap_port", account.imap_port),
                imap_verschluesselung=changes.get("imap_verschluesselung", account.imap_verschluesselung),
                imap_benutzername=changes.get("imap_benutzername", account.imap_benutzername),
                smtp_host=changes.get("smtp_host", account.smtp_host),
                smtp_port=changes.get("smtp_port", account.smtp_port),
                smtp_verschluesselung=changes.get("smtp_verschluesselung", account.smtp_verschluesselung),
                smtp_benutzername=changes.get("smtp_benutzername", account.smtp_benutzername),
                passwort=body.passwort,
            )
        except MailVerbindungFehler as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        account.passwort_verschluesselt = encrypt_secret(body.passwort)

    for field, value in changes.items():
        setattr(account, field, value)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diese E-Mail-Adresse ist bereits ein Postfach hinterlegt",
        ) from exc
    await session.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mail_account(
    account_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_own_account(session, auth, account_id)
    await session.delete(account)
    await session.flush()
