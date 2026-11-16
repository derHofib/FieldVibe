from fastapi import APIRouter, HTTPException, status
from app.schemas.public_rechtliches import RechtlichesAnbieter, RechtlichesRead, ist_http_url
from app.services import system_lookups
from app.services.system_lookups import MandantRechtliches

router = APIRouter(prefix="/api/public", tags=["public"])


def _text(wert: object) -> str | None:
    if not isinstance(wert, str):
        return None
    wert = wert.strip()
    return wert or None


def _url(wert: object) -> str | None:
    text = _text(wert)
    return text if text is not None and ist_http_url(text) else None


def _to_read_model(mandant: MandantRechtliches) -> RechtlichesRead:
    fd = mandant.firmendaten or {}
    adresse = fd.get("adresse")
    if not isinstance(adresse, dict):
        adresse = {}
    return RechtlichesRead(
        impressum_url=_url(fd.get("impressum_url")),
        datenschutz_url=_url(fd.get("datenschutz_url")),
        barrierefreiheit_url=_url(fd.get("barrierefreiheit_url")),
        barrierefreiheit_kontakt_email=_text(fd.get("barrierefreiheit_kontakt_email")),
        barrierefreiheit_stand=_text(fd.get("barrierefreiheit_stand")),
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
    """Oeffentliche Angaben fuer die Platzhalter-Seiten /impressum,
    /datenschutz und /barrierefreiheit. Mit gueltigem portal_slug der Mandant
    dieses Kunden, sonst nur bei genau einem aktiven Mandanten dieser -- bei
    mehreren ohne Kontext bewusst keine Firmenangaben, damit die Route keine
    Mandanten aufzaehlt."""
    if portal_slug:
        # Gleiches Verhalten wie kundenportal_auth.link_info: unbekannter
        # Slug oder nicht aktiver Mandant -> 404.
        mandant = await system_lookups.rechtliches_per_portal_slug(portal_slug)
        if mandant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link ungültig")
        return _to_read_model(mandant)

    mandant = await system_lookups.einziger_aktiver_mandant_rechtliches()
    return _to_read_model(mandant) if mandant is not None else RechtlichesRead()
