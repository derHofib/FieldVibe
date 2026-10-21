from datetime import date
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Nur diese Werte von ENVIRONMENT gelten als bewusst unsichere Umgebung
# (lokale Entwicklung, pytest) -- alles andere, auch ein vergessener Eintrag,
# wird wie Produktion behandelt.
DEV_UMGEBUNGEN = frozenset({"development", "dev", "test", "testing", "local"})

# Mindestlaenge fuer JWT_SECRET (HS256): `openssl rand -base64 48` liefert 64.
MIN_JWT_SECRET_LAENGE = 32


class UnsichereKonfigurationError(RuntimeError):
    """Bewusst keine ValueError-Ableitung: pydantic wuerde sie sonst in einen
    ValidationError mit Feld-Rauschen einpacken, der die Handlungsanweisung
    verschluckt."""


def _ist_platzhalter(wert: str | None) -> bool:
    if not wert:
        return True
    klein = wert.strip().lower()
    return "changeme" in klein or "change-me" in klein


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fail-closed: ohne ENVIRONMENT gilt Produktion. Dev/Test muessen es
    # ausdruecklich setzen (.env.example, tests/conftest.py), siehe
    # DEV_UMGEBUNGEN und die Startpruefung unten.
    environment: str = "production"

    # Log-Format: "json" (eine Zeile pro Eintrag, fuer Log-Sammler) oder "text".
    # Leer = json ausser in Dev/Test (siehe log_format_aktiv).
    log_format: str | None = None
    log_level: str = "INFO"

    # --- Health/Heartbeats (docs/BETRIEB.md) -------------------------------
    # Bearer-Token fuer die Details von /health/ready und /health/heartbeats
    # (externes Monitoring). Leer = nur Plattform-Admins (JWT) sehen sie;
    # /health und der nackte Status von /health/ready sind immer offen.
    health_token: str | None = None
    # Takt des Worker-Lebenszeichens (Datei fuer den Docker-Healthcheck + Zeile in
    # job_laeufe) und Obergrenzen, ab denen ein Heartbeat als veraltet gilt.
    worker_heartbeat_datei: str = "/tmp/fieldvibe-worker-heartbeat"
    heartbeat_intervall_sekunden: int = 30
    heartbeat_worker_max_alter_sekunden: int = 180
    heartbeat_mail_sync_max_alter_sekunden: int = 900
    heartbeat_email_ingest_max_alter_sekunden: int = 3 * 3600 + 900
    # Ein aktives Postfach ohne erfolgreichen Sync seit so vielen Minuten gilt als veraltet.
    heartbeat_mail_konto_max_alter_minuten: int = 60
    # letzter-lauf.json des Backup-Skripts (scripts/backup.sh); Compose haengt das
    # Backup-Verzeichnis dafuer schreibgeschuetzt ins Backend ein. Leer = Backup-Alter
    # wird nicht geprueft.
    backup_status_datei: str | None = None
    backup_max_alter_stunden: int = 36
    # healthchecks.io-kompatibler Ping des Workers (GET <url>); leer = kein Netzverkehr.
    heartbeat_ping_url: str | None = None
    heartbeat_ping_intervall_sekunden: int = 60

    # --- Error-Tracking (Sentry-kompatibel, z. B. GlitchTip; docs/BETRIEB.md) -----
    # Leer = aus: das SDK wird nicht einmal initialisiert, es fliesst kein Byte.
    # Nur EU-gehostet oder selbst betrieben verwenden und AVV abschliessen.
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_release: str | None = None
    # Anteil der Fehler-Events, die gesendet werden (0..1).
    sentry_sample_rate: float = 1.0
    # Performance-Traces sind standardmaessig aus (Datenschutz, Kosten).
    sentry_traces_sample_rate: float = 0.0

    # Betriebs-Zeitzone fuer Tagesgrenzen (Zeiterfassung: Tages-/Wochenfilter,
    # Wochenzettel); siehe app/core/zeit.py. Mandanten haben kein eigenes Feld.
    zeitzone: str = Field(default="Europe/Berlin", validation_alias="FIELDVIBE_ZEITZONE")

    # Notausgang fuer die Startpruefung der DB-Rolle (app/db/rollen_pruefung.py):
    # nur setzen, wenn bewusst eine Superuser-/BYPASSRLS-Rolle genutzt wird und
    # die Mandantentrennung per RLS damit ausser Kraft ist.
    erlaube_rls_bypass_rolle: bool = Field(
        default=False, validation_alias="FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE"
    )

    # Start verweigern, wenn die App-Rolle Eigentuemerin der RLS-Tabellen ist
    # (app/db/rollen_pruefung.py). Aus, solange Migrationen ueber dieselbe Rolle
    # laufen; an, sobald eine getrennte Owner-Rolle eingerichtet ist.
    db_besitz_verboten: bool = Field(
        default=False, validation_alias="FIELDVIBE_DB_BESITZ_VERBOTEN"
    )

    database_url: str = (
        "postgresql+asyncpg://fieldvibe:fieldvibe@localhost:5432/fieldvibe"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://fieldvibe:fieldvibe@localhost:5432/fieldvibe"
    )

    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 14
    impersonation_token_expire_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]

    first_super_admin_email: str | None = None

    # --- Objektspeicher (MinIO/S3), siehe Abschnitt 2 & 15.4 -------------
    # s3_endpoint_url: server-zu-server (Docker-Netzwerk-Hostname "minio").
    # s3_public_url_base: womit der Browser tatsächlich reden kann -- für
    # presigned URLs. Beide zeigen auf dieselbe MinIO-Instanz, nur unter
    # unterschiedlichen, für den jeweiligen Aufrufer erreichbaren Hosts.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_url_base: str = "http://localhost:9000"
    s3_access_key: str = "fieldvibe"
    s3_secret_key: str = "changeme"
    s3_region: str = "us-east-1"
    s3_bucket_fotos: str = "fieldvibe-fotos"
    # Optionaler WORM-Schutz fuer archivierte Rechnungen (docs/gobd/OBJECT_LOCK.md).
    # s3_object_lock: Bucket beim ANLEGEN mit Object Lock erzeugen (MinIO/S3 erlauben das
    # nur bei der Erstellung). s3_rechnungen_retention: "off" | "governance" | "compliance" --
    # Archiv-PDF/-XML bekommen eine Objekt-Aufbewahrung bis zum Fristende der Rechnung
    # (siehe aufbewahrung_service). Beides standardmaessig aus; ungeprueft gegen echtes MinIO.
    s3_object_lock: bool = Field(default=False, validation_alias="S3_OBJECT_LOCK")
    s3_rechnungen_retention: Literal["off", "governance", "compliance"] = Field(
        default="off", validation_alias="S3_RECHNUNGEN_RETENTION"
    )

    # --- Dispo (Abschnitt 4.5): Fahrzeit-Heuristik per Luftlinie ---------
    # Kein Routendienst -- eine grobe Schaetzung (Haversine-Distanz durch
    # eine angenommene Durchschnittsgeschwindigkeit) reicht, um Techniker
    # vor offensichtlich zu knapp geplanten Terminen zu warnen (Warnung,
    # kein Hard-Block).
    dispo_puffer_minuten: int = 30
    dispo_geschwindigkeit_kmh: float = 40.0

    # --- Pruefzyklen-Scheduler (Abschnitt 4.5/12, Phase 5) ---------------
    pruefzyklus_vorlauf_tage: int = 30
    # Default-Uhrzeit (UTC) fuer Mandanten ohne eigene
    # scheduler_stunde_utc-Konfiguration in ihren mandant_integrationen
    # (siehe app/services/scheduler_service.py, Phase-8-Nacharbeit).
    scheduler_default_stunde_utc: int = 3
    # Default-Frist (Tage) fuer die Wiedervorlage bei status="wartet_kunde"
    # (siehe app/api/routes/vorgaenge.py), ueberschreibbar pro Mandant via
    # Mandant.wiedervorlage_standard_tage.
    wiedervorlage_default_tage: int = 14

    # --- Mandant-Integrationen (Abschnitt 7.4, Phase-1-Slot) -------------
    # Verschluesselt secret_ref app-seitig (Fernet) statt im Klartext zu
    # speichern -- kein Ersatz fuer echtes Vault/KMS, aber besser als
    # Klartext-Secrets in der DB, solange keine echte Integration eine
    # produktive Vault-Anbindung braucht. In Produktion unbedingt einen
    # eigenen, von JWT_SECRET verschiedenen Wert setzen.
    integration_secret_key: str | None = None

    # --- Globaler Plattform-Mailversand (Fallback ohne Mandanten-SMTP) ---
    # Greift, wenn ein Mandant (noch) keine eigene smtp-Integration
    # hinterlegt hat (siehe app/services/email_service.py) -- sonst kaeme
    # keine Mail raus, bevor der Mandant erstmal SMTP eingerichtet hat
    # (Henne-Ei-Problem beim Onboarding). Ein Mandant mit eigener
    # smtp-Integration ueberschreibt das automatisch, keine Umschaltung
    # noetig. "account@..." statt z.B. "einladung@...", weil dieselbe
    # Adresse auch fuer Passwort-Reset-Mails (Kundenportal/Partnerportal)
    # verwendet wird, nicht nur fuer Einladungen.
    global_smtp_host: str | None = None
    global_smtp_port: int = 587
    global_smtp_user: str | None = None
    global_smtp_password: str | None = None
    global_smtp_from_address: str = "account@fieldvibe.de"

    # --- Mail-Postfaecher: Schutz vor SSRF (app/services/mail_netz.py) ------
    # Nur fuer lokale Entwicklung/Tests (z.B. MailHog auf localhost): hebt die
    # Sperre fuer private/Loopback-/Link-local-Ziele auf und erlaubt
    # ausserdem unverschluesselte Verbindungen (Verschluesselung "keine",
    # Klartext-Login) fuer Mail-Konten. In Produktion aus.
    mail_erlaube_private_hosts: bool = Field(
        default=False, validation_alias="FIELDVIBE_MAIL_ERLAUBE_PRIVATE_HOSTS"
    )
    # Komma-getrennt statt Liste, weil pydantic-settings Listen aus ENV nur
    # als JSON liest.
    mail_erlaubte_imap_ports: str = Field(
        default="143,993", validation_alias="FIELDVIBE_MAIL_ERLAUBTE_IMAP_PORTS"
    )
    mail_erlaubte_smtp_ports: str = Field(
        default="25,465,587,2525", validation_alias="FIELDVIBE_MAIL_ERLAUBTE_SMTP_PORTS"
    )

    # --- Kundenportal Passwort-Reset (Phase-8-Nacharbeit) ----------------
    # Basis-URL des Frontends fuer den Reset-Link in der Mail; produktiv
    # https://<DOMAIN_APP> (siehe docs/DEPLOYMENT.md).
    frontend_base_url: str = "http://localhost:5173"
    kundenportal_reset_token_expire_minutes: int = 30
    user_reset_token_expire_minutes: int = 30
    # Gueltigkeit des Zwischen-Tokens zwischen Passwort und zweitem Faktor.
    mfa_token_expire_minutes: int = 5
    partner_reset_token_expire_minutes: int = 30
    einladung_token_expire_minutes: int = 60 * 24 * 14

    # --- Mahnwesen (Nacharbeit): Tage nach Faelligkeit bis zur jeweiligen
    # Mahnstufe. Drei Stufen statt eines konfigurierbaren Katalogs -- fuer
    # den abgedeckten Anwendungsfall (Handwerksbetrieb, keine komplexen
    # Inkasso-Prozesse) ausreichend, ohne eine eigene Konfigurations-UI zu
    # brauchen.
    mahnstufe_1_tage: int = 14
    mahnstufe_2_tage: int = 28
    mahnstufe_3_tage: int = 42

    # Basiszinssatz nach §247 BGB, halbjaehrlich von der Bundesbank
    # festgesetzt (Stand 1.7.2026: 1,52%) -- fuer die Verzugszinsen-
    # Berechnung nach §288 BGB auf automatisch versendeten Mahnungen. Muss
    # bei jeder Bundesbank-Anpassung per ENV aktualisiert werden, da es
    # keine automatisierte Anbindung dafuer gibt.
    basiszinssatz_prozent: float = 1.52

    # --- Angebote: nach so vielen Tagen ohne Antwort (seit dem Versand) erinnert
    # der Worker den Ersteller einmalig ans Nachfassen (siehe
    # scheduler_service.run_angebot_nachfassen). Zusaetzlich unabhaengig davon,
    # wenn die Gueltigkeit in den naechsten 2 Tagen ablaeuft.
    angebot_nachfass_tage: int = 7

    # --- Kreditorenbuchhaltung: Vorlaufzeit in Tagen fuer die interne
    # Faelligkeits-/Skonto-Erinnerung (siehe kreditorenbuchhaltung_service.py)
    # -- gleiches Prinzip wie bei den Mahnstufen: feste, env-konfigurierbare
    # Werte statt einer eigenen Konfigurations-UI.
    kreditoren_faelligkeit_erinnerung_tage: int = 3
    kreditoren_skonto_erinnerung_tage: int = 2

    # --- Kartenansicht (Modul "karten"): Mapbox-Access-Token fuer die
    # server-seitige Geocoding-API (Adresse -> geo_lat/geo_lng auf Anlage/
    # Standort). Derselbe Token kann als VITE_MAPBOX_TOKEN auch fuers
    # Kartenrendering im Frontend verwendet werden -- ein einzelner "default
    # public token" (pk...) aus dem Mapbox-Account reicht fuer beides, ein
    # separates Secret-Token ist nicht erforderlich. None = Geocoding wird
    # ueberall uebersprungen (kein Fehler, Anlage/Standort bleiben ohne
    # Koordinaten), auch wenn ein Mandant das Modul aktiviert hat.
    mapbox_access_token: str | None = None

    # --- In-App-Fehlerberichte (app/services/fehlerbericht_service.py) ------
    # Berichte enthalten Netzwerk-/Konsolenkontext -- deshalb nach X Tagen
    # automatisch loeschen (inkl. Screenshots), Standard 90.
    fehlerbericht_aufbewahrung_tage: int = Field(
        default=90, validation_alias="FIELDVIBE_FEHLERBERICHT_AUFBEWAHRUNG_TAGE"
    )
    # sha256-Hex des Bearer-Tokens fuer die Service-API (/api/service/
    # fehlerberichte, fuer Claude). None = Service-API komplett aus (404).
    # Erzeugen: python -m app.cli fehlerbericht-token
    fehlerbericht_service_token_hash: str | None = Field(
        default=None, validation_alias="FIELDVIBE_FEHLERBERICHT_TOKEN_HASH"
    )

    # --- Datenimport (app/services/datenimport/, docs/konzepte/DATENIMPORT.md) --
    # Obergrenzen gegen zu grosse oder praeparierte Dateien; der Import laeuft
    # synchron im Request, die Zeilengrenze haelt ihn im Sekundenbereich.
    import_max_bytes: int = Field(default=10 * 1024 * 1024, validation_alias="FIELDVIBE_IMPORT_MAX_BYTES")
    import_max_zeilen: int = Field(default=20_000, validation_alias="FIELDVIBE_IMPORT_MAX_ZEILEN")
    import_max_spalten: int = Field(default=100, validation_alias="FIELDVIBE_IMPORT_MAX_SPALTEN")
    import_max_zellenlaenge: int = Field(default=5000, validation_alias="FIELDVIBE_IMPORT_MAX_ZELLENLAENGE")
    # Entpackte Groesse einer XLSX-Datei (Schutz vor Zip-Bomben).
    import_max_entpackt_bytes: int = Field(
        default=100 * 1024 * 1024, validation_alias="FIELDVIBE_IMPORT_MAX_ENTPACKT_BYTES"
    )
    import_zeitlimit_sekunden: float = Field(default=60.0, validation_alias="FIELDVIBE_IMPORT_ZEITLIMIT_SEKUNDEN")
    # Hochgeladene Quelldatei: spaetestens nach so vielen Stunden aus dem Objektspeicher entfernen.
    import_zwischenspeicher_stunden: int = Field(
        default=24, validation_alias="FIELDVIBE_IMPORT_ZWISCHENSPEICHER_STUNDEN"
    )
    # Fehlerbericht-CSV (enthaelt Zeilen der Quelldatei) wird so viele Tage nach Abschluss geloescht.
    import_fehlerbericht_tage: int = Field(default=7, validation_alias="FIELDVIBE_IMPORT_FEHLERBERICHT_TAGE")

    # --- Update-Anzeige im Super-Admin-Bereich (rein informativ, kein
    # automatisches Ausfuehren von Updates aus der Web-App heraus -- siehe
    # app/services/version_service.py). git_commit wird beim Docker-Build
    # per --build-arg GIT_COMMIT gesetzt (siehe docker-compose.yml/
    # scripts/deploy.sh), bleibt sonst "unknown".
    git_commit: str = "unknown"
    github_repo: str = "derHofib/FieldVibe"
    # TODO: nach dem Mergen dieses Branches in main hier "main" eintragen
    # (oder GITHUB_BRANCH in der .env setzen) -- siehe README.
    github_branch: str = "claude/multi-tenant-crm-social-feed-vea1l3"

    # /docs, /redoc und /openapi.json: legt die komplette API-Oberflaeche offen
    # (und Swagger-UI laedt Skripte von einem CDN). Default: nur in Dev/Test.
    api_docs: bool | None = Field(default=None, validation_alias="FIELDVIBE_API_DOCS")

    # Refresh-Token als HttpOnly-Cookie (siehe app/core/refresh_cookie.py).
    # Secure-Flag: Default an ausser in Dev/Test; im IP-Betrieb ohne TLS muss
    # es aus sein, sonst verwirft der Browser das Cookie (docker-compose.ip.yml).
    refresh_cookie_secure: bool | None = Field(
        default=None, validation_alias="FIELDVIBE_REFRESH_COOKIE_SECURE"
    )
    # Uebergangsfrist fuer alte Clients (PWA-Bundle im Cache): bis einschliesslich
    # diesem Datum wird das Refresh-Token noch im Body ausgeliefert und
    # angenommen. Danach nur noch Cookie. Leer/"none" = sofort beendet.
    refresh_body_bis: date | None = Field(
        default=date(2026, 12, 31), validation_alias="FIELDVIBE_REFRESH_BODY_BIS"
    )

    @property
    def refresh_cookie_secure_aktiv(self) -> bool:
        return (not self.ist_dev_umgebung) if self.refresh_cookie_secure is None else self.refresh_cookie_secure

    @property
    def ist_dev_umgebung(self) -> bool:
        return self.environment.strip().lower() in DEV_UMGEBUNGEN

    @property
    def log_format_aktiv(self) -> str:
        if self.log_format and self.log_format.strip().lower() in ("json", "text"):
            return self.log_format.strip().lower()
        return "text" if self.ist_dev_umgebung else "json"

    @property
    def api_docs_aktiv(self) -> bool:
        return self.ist_dev_umgebung if self.api_docs is None else self.api_docs

    @model_validator(mode="after")
    def _pruefe_sichere_konfiguration(self) -> "Settings":
        """Startabbruch bei Default-/Platzhalter-Secrets ausserhalb einer
        Dev-Umgebung. Laeuft bei jedem Settings() und damit auch fuer Worker,
        Alembic und CLI, nicht nur fuer den Webprozess."""
        if self.ist_dev_umgebung:
            return self

        probleme: list[str] = []
        if _ist_platzhalter(self.jwt_secret) or len(self.jwt_secret) < MIN_JWT_SECRET_LAENGE:
            probleme.append(
                f"JWT_SECRET ist ein Platzhalter/Default oder kuerzer als {MIN_JWT_SECRET_LAENGE} "
                "Zeichen (Erzeugen: openssl rand -base64 48)"
            )
        # None bleibt erlaubt (Fallback auf JWT_SECRET): ein Bestand mit schon
        # verschluesselten Integrations-Secrets liesse sich sonst nach einem
        # Update nicht mehr entschluesseln. Ein gesetzter Platzhalter ist dagegen
        # eindeutig ein vergessener Eintrag.
        if self.integration_secret_key is not None and _ist_platzhalter(self.integration_secret_key):
            probleme.append("INTEGRATION_SECRET_KEY ist ein Platzhalter (Erzeugen: openssl rand -base64 48)")
        if _ist_platzhalter(self.s3_secret_key):
            probleme.append("S3_SECRET_KEY (= MINIO_ROOT_PASSWORD bzw. Service-Account-Secret) ist ein Platzhalter/Default")
        for name, url in (("DATABASE_URL", self.database_url), ("DATABASE_URL_SYNC", self.database_url_sync)):
            passwort = urlsplit(url).password
            if _ist_platzhalter(passwort) or passwort in {"fieldvibe", "fieldvibe_app"}:
                probleme.append(f"{name} enthaelt ein Platzhalter-/Default-Passwort")

        if probleme:
            zeilen = "\n".join(f"  - {p}" for p in probleme)
            raise UnsichereKonfigurationError(
                f"Unsichere Konfiguration (ENVIRONMENT={self.environment!r}), Start abgebrochen:\n"
                f"{zeilen}\n"
                "Werte in der .env setzen (scripts/deploy.sh erzeugt sie). Fuer lokale "
                "Entwicklung/Tests stattdessen ENVIRONMENT=development setzen "
                "(siehe .env.example, docs/DEPLOYMENT.md, Abschnitt Sicherheit)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
