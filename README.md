# text-to-garmin-workout

CLI tool that converts natural language workout descriptions into structured Garmin Connect workouts, powered by GitHub Copilot.

## How it works

1. **You describe a workout** in plain English (e.g., *"W/u, 20min easy, 4x 2min hills @ 10k effort, c/d"*)
2. **Copilot (LLM) parses it** into a structured workout — and asks clarifying questions if anything is ambiguous (e.g., "How much rest between intervals?")
3. **Preview** the workout structure before uploading
4. **Upload** directly to Garmin Connect

## Prerequisites

- **Python 3.10+**
- **GitHub Copilot CLI** installed and authenticated (`copilot auth login`)
- **Garmin Connect** account

## Installation

```bash
git clone <this-repo>
cd text-to-garmin-workout
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e .
```

## Usage

### Basic (with upload)
```bash
text-to-garmin "W/u, 20min easy, 4x 2min hills @ 10k effort, 4x 1min hills @ 5k effort, 20min easy, c/d"
```

### With a workout name
```bash
text-to-garmin "5x 1km @ 5k pace with 90s rest" -n "5x1km VO2max"
```

### Interactive mode (no arguments)
```bash
text-to-garmin
# Will prompt you for the workout description
```

### Preview only (no upload)
```bash
text-to-garmin --no-upload "10x 400m @ mile pace, 200m jog rest"
```

### Rest until lap button
```bash
text-to-garmin --no-upload "6x 2min @ 10k pace, rest until lap button"
```

### Output Garmin JSON only
```bash
text-to-garmin --json-only "3x 2km @ threshold, 2min rest"
```

### Save JSON to file
```bash
text-to-garmin --save workout.json "8x 800m @ 10k effort, 90s rest"
```

## Garmin Authentication

On first use, you'll be prompted for your Garmin Connect email and password. Successful logins are cached in `~/.garminconnect/garmin_tokens.json` so future runs can reuse and refresh the session automatically.

If Garmin requires MFA, the CLI will prompt for the one-time code during login.

You can also set credentials via environment variables:
```bash
export GARMIN_EMAIL="you@example.com"
export GARMIN_PASSWORD="your-password"
```

## What it understands

The LLM parser handles common running workout notation:

| Notation | Meaning |
|----------|---------|
| `W/u`, `WU` | Warmup |
| `C/d`, `CD` | Cooldown |
| `easy`, `E` | Easy effort |
| `tempo`, `T` | Tempo effort |
| `threshold`, `LT` | Lactate threshold |
| `10k`, `5k`, `mile` | Race pace efforts |
| `4x 2min` | 4 repetitions of 2 minutes |
| `hills` | Hill intervals |
| `strides` | Short fast accelerations |
| `strength` | Strength/conditioning work |
| `R`, `rest` | Recovery between intervals |
| `rest until lap button` | Recovery until you press lap |

### Smart clarifications

If your workout description is ambiguous, Copilot will ask follow-up questions:

```
> text-to-garmin "4x 800m @ 5k pace"

Copilot: How much rest/recovery would you like between the 800m intervals?

Your answer: 2 minutes jog
```

## Example output

```
🏃 Hill Repeats (running)
  1. 🔥 Warmup (until lap button)
  2. 🏃 Run 20:00 @ easy
  3. 🔄 Repeat 4x:
     a. ⚡ Interval 2:00 @ 10k
     b. 😴 Rest 1:00
  4. 🔄 Repeat 4x:
     a. ⚡ Interval 1:00 @ 5k
     b. 😴 Rest 1:00
  5. 🏃 Run 20:00 @ easy
  6. ❄️ Cooldown (until lap button)
```

Lap-button recovery steps are previewed as:
`😴 Rest (until lap button)`

## Architecture

```
Natural language input
    → GitHub Copilot SDK (LLM parsing + Q&A)
    → Pydantic workout models (validation)
    → Garmin Connect JSON builder
    → Upload via garminconnect library (native token-based auth)
```

## Web UI (optional)

A FastAPI backend plus a React + Vite frontend provide the same flow in a
browser. On first launch the UI shows a setup screen where you paste a
GitHub fine-grained PAT (with the **Copilot Requests** permission); the
token is persisted to `$TEXT_TO_GARMIN_STATE_DIR/config.json` (default
`~/.text-to-garmin/config.json`) or, in the deployed container, to the
`/data` volume. Garmin credentials are entered in a modal on first
upload and cached as session tokens.

### Run the backend

```bash
pip install -e '.[web]'
uvicorn text_to_garmin.webapi:app --reload --port 8000
```

Endpoints (all JSON):

| Method | Path                                | Purpose                               |
|--------|-------------------------------------|---------------------------------------|
| GET    | `/api/setup/status`                 | Check Copilot/Garmin configuration    |
| POST   | `/api/setup/copilot`                | Save & verify a Copilot PAT           |
| DELETE | `/api/setup/copilot`                | Forget the stored Copilot PAT         |
| GET    | `/api/models`                       | List available Copilot models         |
| POST   | `/api/drafts`                       | Start a new parse                     |
| POST   | `/api/drafts/{id}/reply`            | Answer a clarifying question          |
| POST   | `/api/drafts/{id}/revise`           | Send revision feedback                |
| POST   | `/api/drafts/{id}/accept`           | Upload to Garmin                      |
| DELETE | `/api/drafts/{id}`                  | Cancel/cleanup                        |
| POST   | `/api/workouts/list`                | List recent Garmin Connect workouts   |
| POST   | `/api/workouts/{id}/delete`         | Delete a workout from Garmin Connect  |
| GET    | `/api/health`                       | Liveness                              |

Streaming variants (`POST /api/drafts/stream`,
`/api/drafts/{id}/reply/stream`, `/api/drafts/{id}/revise/stream`) emit
Server-Sent Events with stage updates as the LLM works.

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://localhost:5173` and proxies `/api` to the backend on
port 8000.

## Deploy to Azure (run your own copy)

Host the web UI on **Azure Container Apps** with one command. Everything
needed to deploy lives at the repo root:

```
Dockerfile              # multi-stage: builds the frontend + Python runtime + Copilot CLI
.dockerignore
azure.yaml              # azd service manifest (points at the Dockerfile)
infra/
  main.bicep            # resource-group-scoped Bicep template
  main.parameters.json  # maps azd env vars → Bicep parameters
```

`azd up` reads `azure.yaml`, builds the image from `Dockerfile`, pushes
it to the ACR defined in `main.bicep`, then deploys a Container App with
HTTPS ingress, scale-to-zero, and a persistent `/data` Azure Files mount.

### Prerequisites

- An Azure subscription you can create resources in
- [Azure Developer CLI](https://aka.ms/azd-install) (`azd`) ≥ 1.10
- Docker (or Podman) — `azd` runs `docker build` locally

### 1. Authenticate and pick a tenant / subscription

```bash
# Sign in (pass --tenant-id if you belong to more than one tenant)
azd auth login --tenant-id <TENANT_GUID>

# OPTIONAL: pre-select the subscription so azd doesn't prompt
azd env new my-t2g                       # creates the azd environment
azd env set AZURE_SUBSCRIPTION_ID <SUBSCRIPTION_GUID>
azd env set AZURE_LOCATION               westeurope
```

If you skip the `env set` calls, `azd up` will prompt interactively for
all three on first run.

### 2. (Optional) customise resource names

By default every resource is named `<abbr><hash>` where `<hash>` is a
12-char string derived from the subscription id, resource group, and
environment name (so names are stable per-environment and unique
globally). Override any of them before running `azd up`:

| Resource                       | azd env var                             | Bicep parameter                 | Constraints |
|--------------------------------|-----------------------------------------|---------------------------------|-------------|
| Resource Group                 | `AZURE_RESOURCE_GROUP`                  | *(azd-managed, not in Bicep)*   | Defaults to `rg-<envName>` |
| Container Registry             | `AZURE_CONTAINER_REGISTRY_NAME`         | `containerRegistryName`         | 5–50 alphanumerics, globally unique |
| Container App                  | `AZURE_CONTAINER_APP_NAME`              | `containerAppName`              | 2–32 chars, lowercase + hyphens |
| Container Apps Environment     | `AZURE_CONTAINER_APPS_ENVIRONMENT_NAME` | `containerAppsEnvironmentName`  | 2–32 chars |
| Log Analytics Workspace        | `AZURE_LOG_ANALYTICS_NAME`              | `logAnalyticsWorkspaceName`     | 4–63 chars |
| Managed Identity               | `AZURE_MANAGED_IDENTITY_NAME`           | `managedIdentityName`           | 3–128 chars |
| Storage Account                | `AZURE_STORAGE_ACCOUNT_NAME`            | `storageAccountName`            | 3–24 lowercase alphanumerics, globally unique |
| Azure Files share (at `/data`) | `AZURE_FILE_SHARE_NAME`                 | `fileShareName`                 | Defaults to `data` |
| Container CPU                  | `CONTAINER_CPU`                         | `containerCpu`                  | e.g. `0.25`, `0.5`, `1.0` |
| Container memory               | `CONTAINER_MEMORY`                      | `containerMemory`               | e.g. `0.5Gi`, `1Gi`, `2Gi` |
| Min / max replicas             | `CONTAINER_MIN_REPLICAS` / `CONTAINER_MAX_REPLICAS` | `minReplicas` / `maxReplicas` | `0..10` / `1..30` |
| GitHub Copilot PAT             | `COPILOT_GITHUB_TOKEN`                  | `copilotGithubToken` (secure)   | Optional; can also be set via UI later |
| App password                   | `APP_PASSWORD`                          | `appPassword` (secure)          | Empty ⇒ sign-in disabled (app is open to anyone with the URL) |
| Session cookie secret          | `APP_SESSION_SECRET`                    | `appSessionSecret` (secure)     | Optional; auto-derived if empty |

Example — fully pinned names in the `contoso` resource group:

```bash
azd env new t2g-prod
azd env set AZURE_SUBSCRIPTION_ID       00000000-0000-0000-0000-000000000000
azd env set AZURE_LOCATION              westeurope
azd env set AZURE_RESOURCE_GROUP        rg-text-to-garmin
azd env set AZURE_CONTAINER_REGISTRY_NAME   contosot2gacr
azd env set AZURE_CONTAINER_APP_NAME        contoso-t2g
azd env set AZURE_STORAGE_ACCOUNT_NAME      contosot2gstate
azd env set COPILOT_GITHUB_TOKEN        github_pat_xxx   # optional
azd env set APP_PASSWORD                '<choose-a-password>'
```

Setting `APP_PASSWORD` turns on a built-in password gate: the deployed
URL shows a password prompt and every `/api/*` call without a valid
session returns 401. It's a single shared password — everyone who uses
the app types the same one and shares the Copilot PAT and cached Garmin
session behind it. This is intentional; the app is designed for a small
circle of trusted users, not multi-tenant. Leave `APP_PASSWORD` empty
and the app is open to anyone with the URL — only do that behind an IP
restriction or private ingress. To rotate, `azd env set APP_PASSWORD
'<new>'` then `azd provision`; to force existing sessions out at the
same time, also rotate `APP_SESSION_SECRET`.

All `azd env set` values are stored in `.azure/<envName>/.env` (gitignored)
and substituted into `infra/main.parameters.json` at deploy time via
the `${VAR=default}` placeholders. You can also edit
`infra/main.parameters.json` directly if you prefer a checked-in config.

### 3. Provision and deploy

```bash
azd up
```

This runs three steps: **provision** (Bicep → Azure), **package**
(Docker build), and **deploy** (push image + update the Container App
revision). When it finishes, `azd` prints the endpoint, something like
`https://contoso-t2g.<region>.azurecontainerapps.io`.

### 4. Configure GitHub Copilot access

> ⚠️ **Security warning — if this URL is public, other people will use
> your PAT.**
> The Copilot PAT you save (via the UI or `COPILOT_GITHUB_TOKEN`) is
> stored on the server and used for **every** request from **every**
> visitor — their prompts are sent to GitHub Copilot as *you*, count
> against your Copilot quota, and are attributed to your GitHub account.
>
> Azure Container Apps gives the Container App a public
> `*.azurecontainerapps.io` FQDN by default. Before pasting a token,
> either:
>
> - Enable the built-in **password gate** by setting `APP_PASSWORD`
>   (see the table in step 2), **or**
> - Keep the URL private (don't share it, treat it like a secret), **or**
> - Put another auth layer in front of it — e.g.
>   [Container Apps authentication](https://learn.microsoft.com/azure/container-apps/authentication)
>   (Entra ID / Google), restrict ingress to a VNet, or sit it
>   behind an Application Gateway / Front Door with WAF + IP allow-list.
>
> The same applies to the cached Garmin tokens on `/data` — anyone who
> can hit the URL can upload or delete workouts on your Garmin Connect
> account.

The app talks to GitHub Copilot via the
[`@github/copilot`](https://www.npmjs.com/package/@github/copilot) CLI,
which needs a token. Two options:

1. **In the UI (recommended)** — open the deployed URL, paste a
   **fine-grained personal access token** on the setup screen and save.
   The token is persisted to the `/data` Azure Files share so it
   survives restarts. Create one at
   <https://github.com/settings/personal-access-tokens/new> with:

   - **Repository access**: *Public Repositories (read-only)* —
     this permission isn't used by the app, but GitHub requires you to
     pick something. Keep it as narrow as possible.
   - **Repository permissions**: leave all at *No access*.
   - **Account permissions → Copilot Requests**: *Read and write*.
     This is the only permission the app actually needs.

   Classic `ghp_…` tokens are **not** supported.
2. **Pre-seed via env var** — set `COPILOT_GITHUB_TOKEN` before `azd up`
   (see the table above). It will be stored as a Container App secret
   and exposed to the container as an env var of the same name.

### Garmin Connect login

Garmin credentials are entered in the UI on first upload and the
resulting session tokens are cached to `/data/garmin_tokens.json` on the
Azure Files volume, so subsequent uploads don't need the password.

### Day-2 operations

```bash
azd deploy            # rebuild + push image and roll the Container App
azd provision         # re-apply infra only (e.g. after editing main.bicep)
azd env get-values    # show the current environment's vars + outputs
azd down --purge      # tear down every resource in the resource group
```

### What gets created

- Resource Group (`rg-<envName>` by default, or your `AZURE_RESOURCE_GROUP`)
- Log Analytics workspace (30-day retention)
- Azure Container Apps environment + Container App
  - HTTPS ingress on port 8080
  - `minReplicas`/`maxReplicas` (defaults 0 / 1 — scales to zero when idle)
  - Mounts `/data` from the Azure Files share
- Azure Container Registry (Basic SKU) with AcrPull granted to a
  user-assigned managed identity used by the Container App
- Storage Account (Standard_LRS) + Azure Files share for persistent state

### Troubleshooting

- **Name conflicts** (`The storage account named … is already taken`):
  the default names include a hash seeded by the subscription + RG, so
  collisions are rare, but globally-unique names (ACR, storage) can still
  clash. Override via the env vars in the table above.
- **Quota errors on `azd up`**: Container Apps and Log Analytics have
  per-region quotas. Pick a different `AZURE_LOCATION`.
- **Image pull failures**: check `Container Registry → Access control`
  — the managed identity listed under `AZURE_PRINCIPAL_ID` output must
  have the `AcrPull` role. The Bicep assigns this automatically; if you
  reuse an existing ACR you may need to grant it manually.

## License

MIT
