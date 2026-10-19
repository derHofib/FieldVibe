from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db.session import system_session
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.schemas.public_rechtliches import RechtlichesAnbieter, RechtlichesRead, ist_http_url

router = APIRouter(prefix="/api/public", tags=["public"])


def _text(wert: object) -> str | None:
    if not isinstance(wert, str):
        return None
    wert = wert.strip()
    return wert or None


def _url(wert: object) -> str | None:
    text = _text(wert)
    return text if text is not None and ist_http_url(text) else None


def _to_read_model(mandant: Mandant) -> RechtlichesRead:
    fd = mandant.firmendaten or {}
    adresse = fd.get("adresse")
    if not isinstance(adresse, dict):
        adresse = {}
    return RechtlichesRead(
        impressum_url=_url(fd.get("impressum_url")),
        datenschutz_url=_url(fd.get("datenschutz_url")),
        anbieter=RechtlichesAnbieter(
            name=mandant.name,
            strasse=_text(adresse.get("strasse")),
            plz=_text(adresse.get("plz")),
            ort=_text(adresse.get("ort")),
            land=_text(adresse.get("land")),
            telefon=_text(fd.get("telefon")),
            email=_text(fd.get("email")),
            website=_text(fd.get("website")),
            geschaeftsfuehrung=_text(fd.get("geschaeftsfuehrung")),
            handelsregister=_text(fd.get("handelsregister")),
            ust_idnr=_text(fd.get("ust_idnr")),
        ),
    )


@router.get("/rechtliches", response_model=RechtlichesRead)
async def get_rechtliches(portal_slug: str | None = None) -> RechtlichesRead:
    """Oeffentliche Angaben fuer die Platzhalter-Seiten /impressum und
    /datenschutz. Mit gueltigem portal_slug der Mandant dieses Kunden, sonst
    nur bei genau einem aktiven Mandanten dieser -- bei mehreren ohne Kontext
    bewusst keine Firmenangaben, damit die Route keine Mandanten aufzaehlt."""
    async with system_session() as session:
        if portal_slug:
            # Gleiches Verhalten wie kundenportal_auth.link_info: unbekannter
            # Slug oder nicht aktiver Mandant -> 404.
            kunde = (
                await session.execute(select(Kunde).where(Kunde.portal_slug == portal_slug))
            ).scalar_one_or_none()
            mandant = await session.get(Mandant, kunde.mandant_id) if kunde else None
            if mandant is None or mandant.status != "aktiv":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link ungültig")
            return _to_read_model(mandant)

        aktive = (
            (await session.execute(select(Mandant).where(Mandant.status == "aktiv").limit(2)))
            .scalars()
            .all()
        )
        if len(aktive) == 1:
            return _to_read_model(aktive[0])
        return RechtlichesRead()
