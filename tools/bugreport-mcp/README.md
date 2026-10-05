# FieldVibe Bugreport-MCP

MCP-Server (stdio) für den Zugriff auf die Fehlerberichte über die Service-API
(`/api/service/fehlerberichte`). Einfacher, abhängigkeitsfreier Alternativweg:
`scripts/fehlerberichte.sh`. Betrieb und Token-Einrichtung:
`docs/FEHLERBERICHTE.md`, Abarbeitung: `docs/BUGFIX_WORKFLOW.md`.

## Konfiguration (Env)

| Variable | Bedeutung |
| --- | --- |
| `FIELDVIBE_API_URL` | Basis-URL der API, z. B. `https://api.fieldvibe.de` |
| `FIELDVIBE_BUGREPORT_TOKEN` | Klartext-Service-Token (`python -m app.cli fehlerbericht-token`) |

Das Token wird nie ausgegeben oder geloggt.

## Tools

| Tool | Zweck |
| --- | --- |
| `list_bug_reports(status?, severity?, kind?, since?, limit?)` | Liste, neueste zuerst |
| `get_bug_report(id)` | Detail inkl. Kontext; Screenshots als Bild (≤ 2 MB), sonst URL |
| `get_ai_bundle(id)` | Markdown-Bundle |
| `update_bug_report(id, status, resolution_note?, fix_commit?, fix_pr_url?)` | Status/Lösung setzen |
| `find_similar(id)` | Berichte mit gleichem Fingerprint |

`status`: `neu`, `gesichtet`, `in_arbeit`, `behoben`, `abgelehnt`, `duplikat`.
`severity`: `niedrig`, `mittel`, `hoch`, `blockierend`.
`kind`: `fehler`, `idee`. Ideen dürfen nur nach Freigabe durch den Betreiber
(Status `gesichtet`) bearbeitet werden.

## Bauen und testen (Node 24)

```bash
cd tools/bugreport-mcp
npm ci
npm run build
npm test
```

## Einbindung in Claude Code

```bash
claude mcp add fieldvibe-bugreport \
  --env FIELDVIBE_API_URL=https://api.fieldvibe.de \
  --env FIELDVIBE_BUGREPORT_TOKEN=<token> \
  -- node /absoluter/pfad/zu/SocialCRM/tools/bugreport-mcp/dist/index.js
```

Oder als `.mcp.json` (bewusst nicht im Repo; z. B. im Home-Verzeichnis oder
projektlokal ungetrackt ablegen, Token per Env-Expansion statt im Klartext):

```json
{
  "mcpServers": {
    "fieldvibe-bugreport": {
      "command": "node",
      "args": ["/absoluter/pfad/zu/SocialCRM/tools/bugreport-mcp/dist/index.js"],
      "env": {
        "FIELDVIBE_API_URL": "https://api.fieldvibe.de",
        "FIELDVIBE_BUGREPORT_TOKEN": "${FIELDVIBE_BUGREPORT_TOKEN}"
      }
    }
  }
}
```
