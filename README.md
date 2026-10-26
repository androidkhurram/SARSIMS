# KSA SIM MCP Server

MCP server that ranks and compares **currently available** Saudi Arabia (KSA) tourist/visitor SIM packages for international travellers (voice and/or data). Plan facts come **only from official operator websites**: STC, Mobily, Zain, Lebara, and Virgin Mobile. Aggregators and search APIs are not used. Discontinued packages are filtered out.

The product is the MCP server. The web agent is only a test client of those tools.

## Scope

- Rank/compare active KSA SIM packages for travellers by voice/data price plans
- Restrict sources to official KSA operator websites
- Exclude discontinued / expired packages
- Ask clarifying follow-ups (service type, trip days, budget) and keep session continuity
- Off-topic asks return: `This specific information is not provided by any service provider.`
- **Accuracy caveat (in scope):** results include `accuracy_notice` — prices/promos are tied to the latest official-site check and are **not** a guarantee of real-time promo accuracy without a fresh refresh/source check at purchase time
- Clients must not invent prices; they call MCP tools

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

No API key is required. The server fetches official operator pages directly.

## Web agent (browser test)

This UI calls the MCP server over stdio (`compare_sim_packages` or `refuse_off_topic`).

```bash
source .venv/bin/activate
python local_ui.py
```

Open [http://127.0.0.1:8768/](http://127.0.0.1:8768/).

## MCP server (Cursor)

Project config is in `.cursor/mcp.json`. Example:

```json
{
  "mcpServers": {
    "ksa-sim": {
      "command": "python",
      "args": ["mcp_server.py"]
    }
  }
}
```

### Tools

| Tool | Purpose |
|------|---------|
| `compare_sim_packages` | Clarify → official operator check → rank current packages |
| `list_active_sim_packages` | List current packages with defaults (both / 7 days / any budget) |
| `get_package_details` | Fresh official-site check for one package/provider name |
| `refuse_off_topic` | Fixed refusal for irrelevant questions |

Pass `previous_filters` (JSON string of `session_filters` from the last success) for follow-ups.

Every successful search includes `accuracy_notice` and `source_checked_at` on each package.

## Azure Function App + GitHub deploy

`function_app.py` hosts:

- Chat UI: `GET /`
- Compare API: `POST /api/compare`
- MCP webhook for AI Foundry: `/runtime/webhooks/mcp/sse`

Push to `main` deploys to Function App `sarsims-fa` via `.github/workflows/deploy-azure-function.yml`.

1. In Azure Portal open **sarsims-fa** → **Get publish profile** and download the file.
2. In GitHub: **SARSIMS → Settings → Secrets and variables → Actions → New repository secret**.
3. Name: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`. Paste the full publish-profile XML.
4. Push to `main` (or run **Actions → Deploy to Azure Function App → Run workflow**).

Chat UI after deploy: `https://sarsims-fa-b5bwceamapeva8cm.eastus2-01.azurewebsites.net/`

### AI Foundry agent

1. After a successful deploy, Azure Portal → **sarsims-fa** → **App keys** → copy the **mcp_extension** (or system) key.
2. In AI Foundry, add an **MCP** tool to the agent.
3. Server URL:

```
https://sarsims-fa-b5bwceamapeva8cm.eastus2-01.azurewebsites.net/runtime/webhooks/mcp/sse
```

4. Authenticate with header `x-functions-key: <mcp_extension key>` (or `code=` query).
5. Tools the agent should use: `compare_sim_packages`, `list_active_sim_packages`, `get_package_details`, `refuse_off_topic`.

Do not make the MCP webhook anonymous. Official-site lookups can take about a minute; the host timeout is 10 minutes.

## Tests

```bash
python3 -m unittest discover -s tests
```
