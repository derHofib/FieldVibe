from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

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

    # --- Mandant-Integrationen (Abschnitt 7.4, Phase-1-Slot) -------------
    # Verschluesselt secret_ref app-seitig (Fernet) statt im Klartext zu
    # speichern -- kein Ersatz fuer echtes Vault/KMS, aber besser als
    # Klartext-Secrets in der DB, solange keine echte Integration eine
    # produktive Vault-Anbindung braucht. In Produktion unbedingt einen
    # eigenen, von JWT_SECRET verschiedenen Wert setzen.
    integration_secret_key: str | None = None

    # --- Kundenportal Passwort-Reset (Phase-8-Nacharbeit) ----------------
    # Basis-URL des Frontends fuer den Reset-Link in der Mail; produktiv
    # https://<DOMAIN_APP> (siehe docs/DEPLOYMENT.md).
    frontend_base_url: str = "http://localhost:5173"
    kundenportal_reset_token_expire_minutes: int = 30
    partner_reset_token_expire_minutes: int = 30

    # --- Mahnwesen (Nacharbeit): Tage nach Faelligkeit bis zur jeweiligen
    # Mahnstufe. Drei Stufen statt eines konfigurierbaren Katalogs -- fuer
    # den abgedeckten Anwendungsfall (Handwerksbetrieb, keine komplexen
    # Inkasso-Prozesse) ausreichend, ohne eine eigene Konfigurations-UI zu
    # brauchen.
    mahnstufe_1_tage: int = 14
    mahnstufe_2_tage: int = 28
    mahnstufe_3_tage: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
