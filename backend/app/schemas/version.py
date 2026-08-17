from pydantic import BaseModel


class VersionInfo(BaseModel):
    deployed_commit: str
    branch: str
    latest_commit_sha: str | None
    latest_commit_message: str | None
    latest_commit_date: str | None
    latest_commit_url: str | None
    # None, wenn nicht ermittelbar (deployed_commit unbekannt oder GitHub
    # nicht erreichbar) statt fälschlich False -- sonst würde ein frisches
    # Deployment ohne GIT_COMMIT-Build-Arg immer "kein Update verfügbar"
    # anzeigen, obwohl das schlicht nicht geprüft werden konnte.
    update_available: bool | None
    fehler: str | None
