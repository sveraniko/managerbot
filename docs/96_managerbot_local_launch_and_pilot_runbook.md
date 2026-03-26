# ManagerBot Local Launch and Pilot Runbook (OPS1)

## 1) What this repo is

This repository is the standalone **ManagerBot operator surface** for TradeFlow V1.
It contains manager-facing runtime code (FastAPI app + Telegram polling loop + notification loop), not a full TradeFlow monorepo deployment stack.

## 2) Integration model with TradeFlow backbone (fixed for V1)

ManagerBot connects **directly** to the existing TradeFlow backbone over shared infrastructure:

- `MANAGERBOT_POSTGRES_DSN` -> shared TradeFlow Postgres (read/write manager-domain truth)
- `MANAGERBOT_REDIS_DSN` -> shared TradeFlow Redis (session state + notification dedupe)
- `MANAGERBOT_BOT_TOKEN` -> internal manager-facing Telegram bot
- `MANAGERBOT_CUSTOMER_BOT_TOKEN` -> outbound customer delivery Telegram bot

Important architecture notes:

- ManagerBot does **not** currently integrate with TradeFlow through an HTTP API.
- ManagerBot does **not** own an isolated local schema bootstrap in this repo.
- ManagerBot runtime expects existing shared backbone state to be reachable.

## 3) Repo structure and working directory

Repository root contains docs + packaging assets.
Application Python package lives under `managerbot/`.

Use these working-directory rules:

- **Local Python launch/tests:** run commands from `managerbot/`.
- **Docker Compose launch:** run commands from repo root (where `docker-compose.yml` and `.env` live).

## 4) Environment contract

1. Copy `.env.example` to `.env` in repo root.
2. Fill required values at minimum:
   - `MANAGERBOT_BOT_TOKEN`
   - `MANAGERBOT_CUSTOMER_BOT_TOKEN`
   - `MANAGERBOT_POSTGRES_DSN`
   - `MANAGERBOT_REDIS_DSN`
3. Optional values:
   - AI flags/config (`MANAGERBOT_AI_*`)
   - handoff chat IDs (`MANAGERBOT_HANDOFF_*`)
   - tuning values (`MANAGERBOT_QUEUE_PAGE_SIZE`, `MANAGERBOT_NOTIFICATION_POLL_SECONDS`, etc.)

## 5) Launch modes

### A. Local Python mode (developer/local pilot precheck)

From `managerbot/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
set -a; source ../.env; set +a
python -m app
```

App endpoint:
- `GET http://localhost:8080/healthz`

### B. Docker Compose mode (pilot-friendly default)

From repo root:

```bash
docker compose up --build -d
```

Inspect status/logs:

```bash
docker compose ps
docker compose logs -f managerbot
```

Stop:

```bash
docker compose down
```

## 6) Startup verification checklist

After boot, verify all of the following:

1. **App process starts** and container/service remains up.
2. **Health endpoint responds**:
   - `curl http://localhost:8080/healthz` returns `{\"status\":\"ok\"}`.
3. **Bot polling loop starts**:
   - startup logs include `managerbot_startup` and no polling crash.
4. **Notification loop starts**:
   - no immediate notification task failure in logs.
5. **DB/Redis connectivity is valid**:
   - no repeated connection errors in logs.
6. **Manager access gate works**:
   - unauthorized Telegram actor receives access denial.
7. **Manager workflow opens**:
   - `/start` shows workdesk/home panel.
8. **Real TradeFlow data visibility**:
   - queue/case view returns real shared backbone records (not local fake seed requirement).

## 7) Pilot-ready definition for OPS1

ManagerBot is pilot-ready (launch packaging level) when:

- `.env` contract is filled and coherent;
- service starts from Docker Compose in integration mode;
- health endpoint is reachable;
- polling + notification loops run;
- manager can open workdesk and operate against real TradeFlow Postgres/Redis data.

## 8) Intentionally out of scope for this repo/runbook

- TradeFlow backbone provisioning/migrations.
- Local bootstrap SQL/schema ownership.
- New product features (MB8, new ergonomics wave, AI scope expansion).
- Monorepo-wide deployment orchestration.
