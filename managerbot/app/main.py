from __future__ import annotations

import asyncio
from contextlib import suppress

import structlog
from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from redis.asyncio import Redis

from app.bot.handlers import build_router
from app.bot.panel_manager import PanelManager
from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.logging import configure_logging
from app.repositories.sql import SqlActorRepository, SqlCaseRepository, SqlNotificationRepository, SqlPresenceRepository, SqlQueueRepository
from app.services.access import AccessService
from app.services.delivery import TelegramCustomerDeliveryGateway
from app.services.manager_surface import ManagerSurfaceService
from app.services.navigation import NavigationService
from app.services.notifications import (
    ManagerBotNotificationSink,
    ManagerNotificationService,
    NotificationPolicy,
    RedisNotificationDedupeStore,
    run_notification_loop,
)
from app.state.manager_session import RedisManagerSessionStore

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="ManagerBot")

    engine = build_engine(settings.postgres_dsn)
    session_factory = build_session_factory(engine)
    redis = Redis.from_url(settings.redis_dsn, decode_responses=True)

    bot = Bot(token=settings.bot_token)
    customer_bot = Bot(token=settings.customer_bot_token)
    dp = Dispatcher()

    actor_repo = SqlActorRepository(session_factory)
    queue_repo = SqlQueueRepository(session_factory)
    case_repo = SqlCaseRepository(session_factory)
    presence_repo = SqlPresenceRepository(session_factory)
    session_store = RedisManagerSessionStore(redis)

    router = build_router(
        access_service=AccessService(actor_repo),
        session_store=session_store,
        surface_service=ManagerSurfaceService(
            queue_repo,
            case_repo,
            presence_repo,
            delivery_gateway=TelegramCustomerDeliveryGateway(customer_bot),
            page_size=settings.queue_page_size,
        ),
        navigation_service=NavigationService(),
        panel_manager=PanelManager(),
    )
    dp.include_router(router)

    app.state.bot = bot
    app.state.dispatcher = dp
    app.state.customer_bot = customer_bot
    app.state.redis = redis
    app.state.engine = engine
    app.state.polling_task = None
    app.state.notification_task = None
    app.state.notification_stop_event = asyncio.Event()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("managerbot_startup")
        app.state.polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        notification_service = ManagerNotificationService(
            events_repo=SqlNotificationRepository(session_factory),
            recipients=actor_repo,
            sink=ManagerBotNotificationSink(bot),
            dedupe=RedisNotificationDedupeStore(redis),
            policy=NotificationPolicy(dedupe_ttl_seconds=settings.notification_dedupe_ttl_seconds),
        )
        app.state.notification_task = asyncio.create_task(
            run_notification_loop(notification_service, settings.notification_poll_seconds, app.state.notification_stop_event)
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("managerbot_shutdown")
        task = app.state.polling_task
        app.state.notification_stop_event.set()
        notify_task = app.state.notification_task
        if notify_task:
            with suppress(asyncio.CancelledError):
                await notify_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await dp.storage.close()
        await bot.session.close()
        await customer_bot.session.close()
        await redis.close()
        await engine.dispose()

    return app


app = create_app()
