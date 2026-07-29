from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = (
        "postgresql+asyncpg://socialcrm:socialcrm@localhost:5432/socialcrm"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://socialcrm:socialcrm@localhost:5432/socialcrm"
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
    s3_access_key: str = "socialcrm"
    s3_secret_key: str = "changeme"
    s3_region: str = "us-east-1"
    s3_bucket_fotos: str = "socialcrm-fotos"

    # --- Dispo (Abschnitt 4.5): Fahrzeit-Heuristik per Luftlinie ---------
    # Kein Routendienst -- eine grobe Schaetzung (Haversine-Distanz durch
    # eine angenommene Durchschnittsgeschwindigkeit) reicht, um Techniker
    # vor offensichtlich zu knapp geplanten Terminen zu warnen (Warnung,
    # kein Hard-Block).
    dispo_puffer_minuten: int = 30
    dispo_geschwindigkeit_kmh: float = 40.0

    # --- Pruefzyklen-Scheduler (Abschnitt 4.5/12, Phase 5) ---------------
    pruefzyklus_vorlauf_tage: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
