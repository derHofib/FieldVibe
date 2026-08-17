import httpx

from app.core.config import get_settings
from app.schemas.version import VersionInfo


async def get_version_info() -> VersionInfo:
    """Rein informativ -- fragt den neuesten Commit auf dem konfigurierten
    GitHub-Branch ab und vergleicht ihn mit dem beim Docker-Build gesetzten
    GIT_COMMIT. Fuehrt selbst keine Aktualisierung aus (siehe Kommentar in
    app/core/config.py); ein RCE-artiges "Update"-Feature, das dem Backend-
    Container Zugriff auf den Docker-Socket/Host gaebe, ist hier bewusst
    nicht umgesetzt."""
    settings = get_settings()
    deployed = settings.git_commit

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{settings.github_repo}/commits/{settings.github_branch}",
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()

        latest_sha: str = data["sha"]
        latest_message = data["commit"]["message"].split("\n", 1)[0]
        latest_date = data["commit"]["committer"]["date"]
        latest_url = data["html_url"]
        update_available = deployed != "unknown" and not latest_sha.startswith(deployed)

        return VersionInfo(
            deployed_commit=deployed,
            branch=settings.github_branch,
            latest_commit_sha=latest_sha[:7],
            latest_commit_message=latest_message,
            latest_commit_date=latest_date,
            latest_commit_url=latest_url,
            update_available=update_available if deployed != "unknown" else None,
            fehler=None,
        )
    except Exception:
        return VersionInfo(
            deployed_commit=deployed,
            branch=settings.github_branch,
            latest_commit_sha=None,
            latest_commit_message=None,
            latest_commit_date=None,
            latest_commit_url=None,
            update_available=None,
            fehler="GitHub konnte nicht erreicht werden",
        )
