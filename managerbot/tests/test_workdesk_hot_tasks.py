import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from app.bot.keyboards import hub_keyboard
from app.models import HotTaskBucket, HotTaskBucketKey, HotTaskItem
from app.repositories.sql import SqlQueueRepository
from app.state.manager_session import ManagerSessionState
from tests.test_sql_repositories_integration import _make_session_factory


def _item(display: int) -> HotTaskItem:
    now = datetime.now(timezone.utc)
    return HotTaskItem(
        case_id=uuid4(),
        case_display_number=display,
        customer_label="ACME",
        reason="reason",
        priority="high",
        escalation_level="none",
        waiting_state="waiting_manager",
        sla_due_at=now,
        last_customer_message_at=now,
        last_event_at=now,
    )


def test_hub_keyboard_exposes_hot_task_case_open_and_open_queue() -> None:
    buckets = [
        HotTaskBucket(HotTaskBucketKey.NEEDS_REPLY_NOW, "Needs reply now", "waiting_me", [_item(501)]),
        HotTaskBucket(HotTaskBucketKey.SLA_AT_RISK, "SLA at risk", "sla_risk", [_item(502)]),
        HotTaskBucket(HotTaskBucketKey.URGENT_ESCALATED, "Urgent / VIP / escalated", "urgent_escalated", [_item(503)]),
        HotTaskBucket(HotTaskBucketKey.FAILED_DELIVERY, "Failed delivery", "failed_delivery", [_item(504)]),
    ]
    kb = hub_keyboard(buckets, {"waiting_me": 7, "sla_risk": 5, "urgent_escalated": 4, "failed_delivery": 2})
    packed = [button.callback_data for row in kb.inline_keyboard for button in row]
    assert any(":queue:waiting_me" in data for data in packed)
    assert any(":queue:sla_risk" in data for data in packed)
    assert any(":queue:urgent_escalated" in data for data in packed)
    assert any(":queue:failed_delivery" in data for data in packed)
    labels = [button.text for row in kb.inline_keyboard for button in row]
    assert "Open Needs reply now (7)" in labels


def test_navigation_state_stays_clean_for_home_refresh() -> None:
    state = ManagerSessionState(panel_key="case:detail", queue_key="waiting_me", queue_offset=5)
    state.panel_key = "hub:home"
    state.queue_offset = 0
    assert state.panel_key == "hub:home"
    assert state.queue_offset == 0


def test_hub_button_uses_truthful_queue_count_not_preview_size() -> None:
    buckets = [
        HotTaskBucket(
            HotTaskBucketKey.NEW_BUSINESS,
            "New incoming",
            "new_incoming",
            [_item(601), _item(602), _item(603)],
        )
    ]
    kb = hub_keyboard(buckets, {"new_incoming": 5})
    labels = [button.text for row in kb.inline_keyboard for button in row]
    assert "Open New incoming (5)" in labels


def test_sql_hot_task_bucket_membership_and_ordering() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        repo = SqlQueueRepository(sf)

        # Enrich seed with deterministic hot-task signals.
        async with sf() as session:
            now = datetime.now(timezone.utc)
            overdue = (now - timedelta(minutes=5)).isoformat()
            near = (now + timedelta(minutes=10)).isoformat()
            fresh = now.isoformat()
            old = (now - timedelta(minutes=30)).isoformat()
            await session.execute(
                text(
                    "update ops.quote_case_ops_states set waiting_state='waiting_manager', assigned_manager_actor_id='m1', priority='vip', sla_due_at=:near, last_customer_message_at=:old where quote_case_id='c2'"
                ),
                {"near": near, "old": old},
            )
            await session.execute(
                text(
                    "update ops.quote_case_ops_states set status='new', waiting_state='none', priority='normal', assigned_manager_actor_id=null, updated_at=:fresh where quote_case_id='c1'"
                ),
                {"fresh": fresh},
            )
            await session.execute(
                text("update core.quote_cases set customer_label=null, customer_actor_id=null, customer_telegram_chat_id=null where id='c1'")
            )
            await session.execute(
                text("delete from ops.quote_case_thread_entries where quote_case_id='c1' and direction='inbound'")
            )
            await session.execute(
                text(
                    "update ops.quote_case_ops_states set waiting_state='waiting_manager', assigned_manager_actor_id='m1', priority='urgent', escalation_level='manager_attention', sla_due_at=:overdue, last_customer_message_at=:fresh where quote_case_id='c3'"
                ),
                {"overdue": overdue, "fresh": fresh},
            )
            await session.execute(
                text(
                    """
                    insert into ops.reply_delivery_attempts(id, thread_entry_id, quote_case_id, target_telegram_chat_id, attempt_number, transport, status, telegram_message_id, error_message, attempted_at, completed_at, created_at, updated_at)
                    values ('fd1', 't2', 'c2', 40002, 1, 'telegram_bot_api', 'failed', null, 'network', :fresh, :fresh, :fresh, :fresh)
                    """
                ),
                {"fresh": fresh},
            )
            await session.commit()

        buckets = await repo.hot_task_buckets("m1", item_limit=3)
        by_key = {b.key.value: b for b in buckets}

        assert by_key["needs_reply_now"].items
        assert by_key["new_business"].items == []
        assert by_key["sla_at_risk"].items
        assert by_key["urgent_escalated"].items
        assert by_key["failed_delivery"].items

        # SLA ordering: overdue (case 103) before near breach (case 102).
        sla_cases = [i.case_display_number for i in by_key["sla_at_risk"].items]
        assert sla_cases[:2] == [103, 102]

        # Urgent/VIP/escalated lane includes VIP and keeps urgent+escalated case first.
        urgent_cases = [i.case_display_number for i in by_key["urgent_escalated"].items]
        assert urgent_cases[:2] == [103, 102]

        # Failed delivery picks case with failed attempt.
        failed_cases = [i.case_display_number for i in by_key["failed_delivery"].items]
        assert failed_cases[0] == 102

        # Bucket-level open actions now route to truthful list keys.
        assert by_key["sla_at_risk"].queue_key == "sla_risk"
        assert by_key["urgent_escalated"].queue_key == "urgent_escalated"
        assert by_key["failed_delivery"].queue_key == "failed_delivery"

        # Queue list views are aligned and deterministic for bucket semantics.
        incoming_list = await repo.list_queue("new_incoming", "m1", 0, 10)
        assert incoming_list == []

        sla_list = await repo.list_queue("sla_risk", "m1", 0, 10)
        assert [item.case_display_number for item in sla_list[:2]] == [103, 102]

        failed_list = await repo.list_queue("failed_delivery", "m1", 0, 10)
        assert [item.case_display_number for item in failed_list] == [102]

        urgent_list = await repo.list_queue("urgent_escalated", "m1", 0, 10)
        assert urgent_list
        assert [item.case_display_number for item in urgent_list[:2]] == [103, 102]

    asyncio.run(run())


def test_new_incoming_bucket_includes_real_inbound_cases() -> None:
    async def run() -> None:
        sf = await _make_session_factory()
        repo = SqlQueueRepository(sf)

        buckets = await repo.hot_task_buckets("m1", item_limit=3)
        by_key = {b.key.value: b for b in buckets}
        incoming = by_key["new_business"]
        assert incoming.title == "New incoming"
        assert [item.case_display_number for item in incoming.items] == [101]

        counts = await repo.summary_counts("m1")
        assert counts["new"] == 1
        assert counts["new_incoming"] == 1

        queue_items = await repo.list_queue("new_incoming", "m1", 0, 10)
        assert [item.case_display_number for item in queue_items] == [101]

    asyncio.run(run())
