# OPS1 Launch / Bootstrap Packaging Report

## Scope delivered

OPS1 packaged existing ManagerBot V1 runtime for practical launch/bootstrap without adding product features.

## Files added

1. `.env.example`
2. `Dockerfile`
3. `docker-compose.yml`
4. `docs/96_managerbot_local_launch_and_pilot_runbook.md`
5. `docs/OPS1_launch_bootstrap_packaging_report.md`
6. `managerbot/tests/test_ops1_env_contract.py`

## Supported launch mode

- Primary mode: **integration-mode ManagerBot service only**.
- Docker Compose launches only `managerbot` service by default.
- Postgres/Redis are expected as external/shared dependencies provided via `.env` DSNs.

## TradeFlow connectivity model (explicit)

ManagerBot in this repo connects directly to existing TradeFlow backbone:

- shared Postgres via `MANAGERBOT_POSTGRES_DSN`
- shared Redis via `MANAGERBOT_REDIS_DSN`
- manager Telegram bot token via `MANAGERBOT_BOT_TOKEN`
- customer delivery Telegram bot token via `MANAGERBOT_CUSTOMER_BOT_TOKEN`

No HTTP API coupling to TradeFlow is introduced in OPS1.

## Compose model statement

- `docker-compose.yml` is **service-only integration mode**.
- No bundled Postgres/Redis demo stack is enabled by default.

## Migration discipline confirmation

- No migration files were created.
- No local schema/bootstrap SQL files were added.

## Remaining pilot-launch limitations

1. Runtime still depends on externally reachable TradeFlow Postgres/Redis.
2. Valid Telegram bot tokens are required for polling/delivery behavior.
3. AI behavior remains optional and disabled unless explicitly configured.
4. This repo does not provision backbone infra; it only packages ManagerBot runtime startup.
