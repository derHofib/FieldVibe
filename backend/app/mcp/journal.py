"""KI-Journal (ki_aktionen): jede schreibende Tool-Aktion wird mit Ziel, Vorher/Nachher und Rueckweg festgehalten.

Ablauf in einem Schreib-Tool:
    aktion = Aktion(z, tool="vorgang_speichern", aktionsart="vorgang.aendern", stufe=2)
    with aktion:                      # setzt die Journal-ID fuer den Header X-FieldVibe-KI-Aktion
        ... api_patch(...) ...
        aktion.ziel(...); aktion.aenderung(...); aktion.rueckweg_hinzu(...)
    return await aktion.fertig(zusammenfassung=..., link=...)

Das Journal laeuft in der tenant_session des Mandanten aus dem Token (kein system_session). Das Rueckgaengig
steht in app/services/ki_rueckgaengig.py."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.db.session import tenant_session
from app.mcp.anzeige import Namen, eintrag, feld_label, gleich
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.rest_client import aktion_id_var
from app.models.ki_aktion import KiAktion
from app.services import audit_service

logger = logging.getLogger(__name__)

RUECKGAENGIG_FRIST = timedelta(days=7)
RUECKGAENGIG_HINWEIS = "Rückgängig mit rueckgaengig(aktion_id) oder in FieldVibe unter KI-Aktivität."


def ref(typ: str, id_: Any, label: str) -> dict[str, str]:
    return {"typ": typ, "id": str(id_), "label": label}


def pruefung(
    pfad: str,
    feld: str,
    erwartet: Any,
    *,
    label: str,
    feld_label: str,
    erwartet_anzeige: str | None = None,
    anzeige_feld: str | None = None,
    params: dict[str, Any] | None = None,
    element: tuple[str, Any] | None = None,
) -> dict[str, Any]:
    """Bedingung, die vor dem Rueckgaengig gelten muss: `feld` der GET-Antwort auf `pfad` ist noch `erwartet`
    (feld "#anzahl": Laenge der Listenantwort). Label und Anzeigewerte stehen dabei, damit ein Konflikt
    verstaendlich gemeldet werden kann, ohne die Daten erneut aufzuloesen. `element` = (Feld, Wert): die Antwort
    ist eine Liste (z. B. Kontakte eines Kunden), geprueft wird der Eintrag mit diesem Feldwert."""
    return {
        "pfad": pfad,
        "params": params,
        "feld": feld,
        "erwartet": erwartet,
        "label": label,
        "feld_label": feld_label,
        "erwartet_anzeige": erwartet_anzeige,
        "anzeige_feld": anzeige_feld,
        "element": list(element) if element else None,
    }


def operation(methode: str, pfad: str, body: Any = None, pruefungen: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Die Pruefungen stehen bewusst als Liste: ein Rueckweg-PATCH setzt mehrere Felder zurueck und prueft jedes.
    return {"methode": methode, "pfad": pfad, "body": body, "pruefung": pruefungen or None}


@dataclass
class Aktion:
    zugriff: KiAccessToken
    tool: str
    aktionsart: str
    stufe: int
    id: UUID = field(default_factory=uuid4)
    ziele: list[dict[str, str]] = field(default_factory=list)
    aenderungen: list[dict[str, Any]] = field(default_factory=list)
    erzeugt: list[dict[str, str]] = field(default_factory=list)
    rueckweg: list[dict[str, Any]] = field(default_factory=list)
    _token: Any = None

    def __enter__(self) -> "Aktion":
        self._token = aktion_id_var.set(self.id)
        return self

    def __exit__(self, *_exc: object) -> None:
        aktion_id_var.reset(self._token)

    def ziel(self, typ: str, id_: Any, label: str) -> None:
        if not any(z["typ"] == typ and z["id"] == str(id_) for z in self.ziele):
            self.ziele.append(ref(typ, id_, label))

    def neu_erzeugt(self, typ: str, id_: Any, label: str) -> None:
        self.erzeugt.append(ref(typ, id_, label))
        self.ziel(typ, id_, label)

    async def vergleichen(
        self,
        namen: Namen,
        typ: str,
        id_: Any,
        label: str,
        vorher: dict[str, Any],
        nachher: dict[str, Any],
        felder: list[str],
    ) -> list[str]:
        """Traegt alle Felder, deren Wert sich geaendert hat, mit Roh- und Anzeigewert ein; liefert deren Namen."""
        geaendert = []
        for feld in felder:
            alt, neu = vorher.get(feld), nachher.get(feld)
            if gleich(alt, neu):
                continue
            geaendert.append(feld)
            self.aenderungen.append(
                {
                    "typ": typ,
                    "id": str(id_),
                    "label": label,
                    "feld": feld,
                    "feld_label": feld_label(typ, feld),
                    "vorher": eintrag(alt, await namen.anzeige(feld, alt, vorher)),
                    "nachher": eintrag(neu, await namen.anzeige(feld, neu, nachher)),
                }
            )
        return geaendert

    def rueckweg_hinzu(self, op: dict[str, Any]) -> None:
        self.rueckweg.append(op)

    async def fertig(
        self,
        zusammenfassung: str,
        *,
        link: str | None = None,
        fehler: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Schreibt den Journal-Eintrag und liefert die einheitliche Tool-Antwort (Karte im Chat und Text)."""
        jetzt = datetime.now(timezone.utc)
        bis = jetzt + RUECKGAENGIG_FRIST if self.rueckweg else None
        gespeichert = True
        try:
            await protokollieren(
                self.zugriff,
                tool=self.tool,
                aktionsart=self.aktionsart,
                stufe=self.stufe,
                zusammenfassung=zusammenfassung,
                ziele=self.ziele,
                aenderungen=self.aenderungen,
                erzeugt=self.erzeugt,
                rueckweg=self.rueckweg,
                fehler=fehler,
                aktion_id=self.id,
                jetzt=jetzt,
            )
        except Exception:  # die Aenderung ist schon passiert; ein Journal-Fehler darf sie nicht verdecken
            logger.exception("KI-Journal konnte nicht geschrieben werden (tool=%s)", self.tool)
            gespeichert = False
        antwort: dict[str, Any] = {
            "aktion_id": str(self.id),
            "zusammenfassung": zusammenfassung,
            "stufe": self.stufe,
            "ziele": self.ziele,
            "erzeugt": self.erzeugt,
            "aenderungen": [
                {
                    "typ": a["typ"],
                    "id": a["id"],
                    "label": a["label"],
                    "feld": a["feld"],
                    "feld_label": a["feld_label"],
                    "vorher": a["vorher"]["anzeige"],
                    "nachher": a["nachher"]["anzeige"],
                }
                for a in self.aenderungen
            ],
            "link": link,
            "rueckgaengig_bis": bis.isoformat() if bis else None,
        }
        if extra:
            antwort.update(extra)
        if fehler:
            antwort["fehler"] = fehler
        if not gespeichert:
            antwort["hinweis"] = (
                "Die Änderung wurde ausgeführt, konnte aber nicht im KI-Journal protokolliert werden; "
                "Rückgängig ist dafür nicht möglich."
            )
        elif bis:
            antwort["hinweis"] = RUECKGAENGIG_HINWEIS
        return antwort


async def protokollieren(
    zugriff: KiAccessToken,
    *,
    tool: str,
    aktionsart: str,
    stufe: int,
    zusammenfassung: str,
    ziele: list[dict[str, Any]],
    aenderungen: list[dict[str, Any]],
    erzeugt: list[dict[str, Any]],
    rueckweg: list[dict[str, Any]],
    fehler: str | None = None,
    aktion_id: UUID | None = None,
    jetzt: datetime | None = None,
) -> UUID:
    """Schreibt eine ki_aktionen-Zeile (Status "ausgefuehrt"; bei Teilerfolg mit `fehler`) und liefert ihre ID.
    Das Rueckgaengig ist 7 Tage moeglich, wenn es einen Rueckweg gibt. Nur aufrufen, wenn mindestens eine
    Wirkung eingetreten ist."""
    jetzt = jetzt or datetime.now(timezone.utc)
    bis = jetzt + RUECKGAENGIG_FRIST if rueckweg else None
    aktion_id = aktion_id or uuid4()
    async with tenant_session(mandant_id=zugriff.mandant_id) as session:
        session.add(
            KiAktion(
                id=aktion_id,
                mandant_id=zugriff.mandant_id,
                user_id=zugriff.user_id,
                ki_verbindung_id=zugriff.kv,
                tool=tool,
                aktionsart=aktionsart,
                stufe=stufe,
                status="ausgefuehrt",
                zusammenfassung=zusammenfassung,
                ziele=ziele,
                aenderungen=aenderungen,
                erzeugt=erzeugt,
                rueckweg=rueckweg,
                rueckgaengig_bis=bis,
                fehler=fehler,
                request_id=audit_service.aktuelle_request_id(),
            )
        )
    return aktion_id
