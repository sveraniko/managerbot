import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.sql import SqlActorRepository, SqlCaseRepository, SqlPresenceRepository, SqlQueueRepository
from app.services.access import AccessService


async def _make_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.execute(text("ATTACH DATABASE ':memory:' AS ops"))
        await conn.execute(text("ATTACH DATABASE ':memory:' AS read"))

        await conn.execute(text("create table core.actors(id text primary key, display_name text not null)"))
        await conn.execute(text("create table core.actor_telegram_bindings(actor_id text not null, telegram_user_id integer not null)"))
        await conn.execute(text("create table core.actor_roles(actor_id text not null, role text not null)"))
        await conn.execute(text("create table core.quote_cases(id text primary key, display_number integer not null, status text not null, customer_label text)"))
        await conn.execute(text("create table core.orders(id text primary key, source_quote_case_id text not null, display_number integer not null)"))

        await conn.execute(
            text(
                """
                create table ops.manager_presence_states(
                    id text primary key,
                    actor_id text not null unique,
                    presence_status text not null,
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                create table ops.quote_case_ops_states(
                    id text primary key,
                    quote_case_id text not null unique,
                    status text not null,
                    waiting_state text not null,
                    priority text not null,
                    assigned_manager_actor_id text,
                    assigned_by_actor_id text,
                    assigned_at text,
                    escalation_level integer not null,
                    last_customer_message_at text,
                    updated_at text not null
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                create table ops.quote_case_thread_entries(
                    id text primary key,
                    quote_case_id text not null,
                    direction text not null,
                    body_text text not null,
                    created_at text not null
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                create table ops.quote_case_assignment_events(
                    id text primary key,
                    quote_case_id text not null,
                    event_seq integer not null,
                    event_kind text not null,
                    from_manager_actor_id text,
                    to_manager_actor_id text,
                    triggered_by_actor_id text,
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
        )

        await conn.execute(text("insert into core.actors(id, display_name) values ('m1', 'Manager One'), ('m2', 'Manager Two'), ('cust', 'Customer')"))
        await conn.execute(text("insert into core.actor_telegram_bindings(actor_id, telegram_user_id) values ('m1', 1001), ('cust', 7777)"))
        await conn.execute(text("insert into core.actor_roles(actor_id, role) values ('m1', 'MANAGER'), ('cust', 'CUSTOMER')"))

        await conn.execute(
            text(
                """
                insert into core.quote_cases(id, display_number, status, customer_label) values
                ('c1', 101, 'open', 'Acme'),
                ('c2', 102, 'open', 'Beta'),
                ('c3', 103, 'open', 'Gamma')
                """
            )
        )
        await conn.execute(text("insert into core.orders(id, source_quote_case_id, display_number) values ('o1', 'c1', 9001)"))

        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            text(
                """
                insert into ops.quote_case_ops_states(
                    id, quote_case_id, status, waiting_state, priority,
                    assigned_manager_actor_id, assigned_by_actor_id, assigned_at,
                    escalation_level, last_customer_message_at, updated_at
                ) values
                ('s1', 'c1', 'new', 'none', 'high', null, null, null, 0, :now, :now),
                ('s2', 'c2', 'active', 'waiting_manager', 'urgent', 'm1', 'm1', :now, 0, :now, :now),
                ('s3', 'c3', 'active', 'waiting_customer', 'normal', 'm1', 'm1', :now, 1, :now, :now)
                """
            ),
            {"now": now},
        )
        await conn.execute(
            text(
                """
                insert into ops.quote_case_thread_entries(id, quote_case_id, direction, body_text, created_at) values
                ('t1', 'c1', 'inbound', 'Need update', :now),
                ('t2', 'c1', 'outbound', 'Working on it', :now)
                """
            ),
            {"now": now},
        )

    return async_sessionmaker(engine, expire_on_commit=False)


def test_actor_lookup_and_access_contract() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        access = AccessService(SqlActorRepository(sf))

        allowed = await access.resolve_authorized_actor(1001)
        assert allowed is not None
        assert allowed.actor_id == "m1"

        denied = await access.resolve_authorized_actor(7777)
        assert denied is None

        missing = await access.resolve_authorized_actor(9999)
        assert missing is None

    asyncio.run(run())


def test_presence_repository_roundtrip_and_default() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        repo = SqlPresenceRepository(sf)

        assert (await repo.get_status("m1")).value == "online"

        from app.models import PresenceStatus

        await repo.set_status("m1", PresenceStatus.BUSY)
        assert (await repo.get_status("m1")).value == "busy"

    asyncio.run(run())


def test_queue_repository_summary_filters_and_order() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        repo = SqlQueueRepository(sf)

        counts = await repo.summary_counts("m1")
        assert counts["new"] == 1
        assert counts["waiting_me"] == 1
        assert counts["waiting_customer"] == 1

        urgent = await repo.list_queue("urgent", "m1", 0, 10)
        assert [item.case_display_number for item in urgent] == [102]

        waiting_customer = await repo.list_queue("waiting_customer", "m1", 0, 10)
        assert [item.case_display_number for item in waiting_customer] == [103]

    asyncio.run(run())


def test_case_detail_and_claim_persist_canonical_assignment_event() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        cases = SqlCaseRepository(sf)

        detail = await cases.get_detail("c1", "m1")
        assert detail is not None
        assert detail.linked_quote_display_number == 101
        assert detail.linked_order_display_number == 9001
        assert [entry.body for entry in detail.thread_entries] == ["Need update", "Working on it"]

        claimed = await cases.claim_case("c1", "m1")
        assert claimed is True

        async with sf() as session:
            state = (
                await session.execute(
                    text(
                        "select assigned_manager_actor_id, status, waiting_state from ops.quote_case_ops_states where quote_case_id='c1'"
                    )
                )
            ).first()
            assert state.assigned_manager_actor_id == "m1"
            assert state.status == "active"
            assert state.waiting_state == "waiting_manager"

            event = (
                await session.execute(
                    text(
                        """
                        select event_kind, from_manager_actor_id, to_manager_actor_id, triggered_by_actor_id
                        from ops.quote_case_assignment_events where quote_case_id='c1'
                        """
                    )
                )
            ).first()
            assert event.event_kind == "claimed"
            assert event.from_manager_actor_id is None
            assert event.to_manager_actor_id == "m1"
            assert event.triggered_by_actor_id == "m1"

    asyncio.run(run())
