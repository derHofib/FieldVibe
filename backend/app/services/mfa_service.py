"""TOTP-Zwei-Faktor-Anmeldung fuer Mitarbeiter (RFC 6238, 30 s / 6 Stellen).

Die Funktionen mutieren nur das uebergebene User-Objekt; Sitzung, Zeilensperre
(SELECT ... FOR UPDATE), Rate-Limit und Token-Widerruf liegen bei den Routen
(app/api/routes/mfa.py). Ohne Zeilensperre koennten zwei gleichzeitige Anfragen
denselben Code oder denselben Wiederherstellungscode beide akzeptieren.
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

import pyotp
import segno

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.mandant import Mandant
from app.models.user import User

ISSUER = "FieldVibe"
SCHRITT_SEKUNDEN = 30
# +-1 Schritt: Uhrabweichung zwischen Handy und Server.
FENSTER = 1
ANZAHL_WIEDERHERSTELLUNGSCODES = 10


class MfaFehler(Exception):
    """Fachlicher Fehler mit nutzerlesbarer Meldung; die Route wandelt ihn in
    eine HTTP-Antwort um."""


def neues_secret() -> str:
    return pyotp.random_base32()


def otpauth_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg_data_uri(uri: str) -> str:
    # Lokal erzeugt, damit das Secret nie an einen QR-Dienst geht. Heller
    # Hintergrund explizit: transparent waere im Dark Mode nicht scanbar.
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#000000", light="#ffffff")


def _normalisiere_totp(code: str) -> str | None:
    kompakt = code.replace(" ", "").replace("-", "")
    return kompakt if len(kompakt) == 6 and kompakt.isascii() and kompakt.isdigit() else None


def pruefe_totp(secret: str, code: str, letzter_schritt: int | None, jetzt: float | None = None) -> int | None:
    """Zeitschritt des akzeptierten Codes oder None. Ein Schritt, der nicht
    nach dem zuletzt akzeptierten liegt, wird abgelehnt (Replay)."""
    kompakt = _normalisiere_totp(code)
    if kompakt is None:
        return None
    totp = pyotp.TOTP(secret, interval=SCHRITT_SEKUNDEN)
    aktuell = int((time.time() if jetzt is None else jetzt) // SCHRITT_SEKUNDEN)
    treffer: int | None = None
    # Alle Fenster-Schritte immer durchrechnen und vergleichen: kein
    # vorzeitiger Abbruch, der Treffer-Position per Timing verraet.
    for schritt in range(max(aktuell - FENSTER, 0), aktuell + FENSTER + 1):
        if hmac.compare_digest(totp.at(schritt * SCHRITT_SEKUNDEN), kompakt):
            treffer = schritt
    if treffer is None or (letzter_schritt is not None and treffer <= letzter_schritt):
        return None
    return treffer


# --- Wiederherstellungscodes -----------------------------------------------
def _hmac_schluessel() -> bytes:
    material = (get_settings().integration_secret_key or get_settings().jwt_secret).encode()
    return hashlib.sha256(b"fieldvibe-mfa-wiederherstellung:" + material).digest()


def _normalisiere_wiederherstellung(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()


def hash_wiederherstellungscode(user_id, code: str) -> str:
    # HMAC mit Serverschluessel statt blossem SHA-256: auch ein Datenbankabzug
    # allein erlaubt kein Offline-Raten. Die Codes tragen 80 Bit Entropie.
    nachricht = f"{user_id}:{_normalisiere_wiederherstellung(code)}".encode()
    return hmac.new(_hmac_schluessel(), nachricht, hashlib.sha256).hexdigest()


def _neue_wiederherstellungscodes() -> list[str]:
    codes = []
    for _ in range(ANZAHL_WIEDERHERSTELLUNGSCODES):
        roh = base64.b32encode(secrets.token_bytes(10)).decode()
        codes.append("-".join(roh[i : i + 4] for i in range(0, 16, 4)))
    return codes


def _wiederherstellungscodes_setzen(user: User) -> list[str]:
    codes = _neue_wiederherstellungscodes()
    user.mfa_wiederherstellung = [hash_wiederherstellungscode(user.id, c) for c in codes]
    return codes


def wiederherstellungscodes_uebrig(user: User) -> int:
    return len(user.mfa_wiederherstellung or [])


def _wiederherstellungscode_verbrauchen(user: User, code: str) -> bool:
    kandidat = hash_wiederherstellungscode(user.id, code)
    uebrig = list(user.mfa_wiederherstellung or [])
    treffer = None
    for gespeichert in uebrig:
        if hmac.compare_digest(gespeichert, kandidat):
            treffer = gespeichert
    if treffer is None:
        return False
    uebrig.remove(treffer)
    # Neue Liste statt In-place-Aenderung: JSONB-Spalten ohne MutableList
    # erkennen Mutationen nicht.
    user.mfa_wiederherstellung = uebrig
    return True


# --- Zustandswechsel -------------------------------------------------------
def einrichtung_beginnen(user: User) -> str:
    if user.mfa_aktiv:
        raise MfaFehler("MFA ist bereits aktiv. Zum Neu-Einrichten zuerst deaktivieren.")
    secret = neues_secret()
    user.mfa_secret_enc = encrypt_secret(secret)
    user.mfa_letzter_schritt = None
    return secret


def secret_von(user: User) -> str | None:
    return decrypt_secret(user.mfa_secret_enc) if user.mfa_secret_enc else None


def einrichtung_bestaetigen(user: User, code: str) -> list[str]:
    """Aktiviert MFA, wenn der Code zum ausstehenden Secret passt; liefert die
    Wiederherstellungscodes im Klartext (einzige Gelegenheit, sie zu sehen)."""
    if user.mfa_aktiv:
        raise MfaFehler("MFA ist bereits aktiv.")
    secret = secret_von(user)
    if secret is None:
        raise MfaFehler("Es wurde keine Einrichtung gestartet.")
    schritt = pruefe_totp(secret, code, None)
    if schritt is None:
        raise MfaFehler("Der Code ist ungültig oder abgelaufen.")
    user.mfa_aktiv = True
    user.mfa_letzter_schritt = schritt
    user.mfa_aktiviert_am = datetime.now(timezone.utc)
    return _wiederherstellungscodes_setzen(user)


def code_verbrauchen(user: User, code: str) -> str | None:
    """Prueft TOTP-Code oder Wiederherstellungscode eines aktiven Accounts und
    markiert ihn als verbraucht. Liefert "totp"/"wiederherstellung" bei Erfolg,
    sonst None."""
    if not user.mfa_aktiv:
        return None
    secret = secret_von(user)
    if _normalisiere_totp(code) is not None:
        if secret is None:
            return None
        schritt = pruefe_totp(secret, code, user.mfa_letzter_schritt)
        if schritt is None:
            return None
        user.mfa_letzter_schritt = schritt
        return "totp"
    return "wiederherstellung" if _wiederherstellungscode_verbrauchen(user, code) else None


def neue_wiederherstellungscodes(user: User) -> list[str]:
    return _wiederherstellungscodes_setzen(user)


def zuruecksetzen(user: User) -> None:
    user.mfa_aktiv = False
    user.mfa_secret_enc = None
    user.mfa_wiederherstellung = None
    user.mfa_letzter_schritt = None
    user.mfa_aktiviert_am = None


# --- Pflicht-MFA je Mandant ------------------------------------------------
def mandant_verlangt_mfa(mandant: Mandant | None) -> bool:
    return mandant is not None and (mandant.firmendaten or {}).get("mfa_pflicht") is True


def einrichtung_erforderlich(user: User, mandant: Mandant | None) -> bool:
    """super_admin und Plattformkonten ohne Mandant sind ausgenommen (die
    Pflicht ist eine Mandanteneinstellung)."""
    return (
        user.mandant_id is not None
        and user.role != "super_admin"
        and not user.mfa_aktiv
        and mandant_verlangt_mfa(mandant)
    )
