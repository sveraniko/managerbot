from datetime import datetime, timezone
from uuid import uuid4

from app.bot.handlers import _cycle_filter, _reset_filters
from app.models import QueueFilters, QueueItem, SearchResultItem
from app.services.navigation import NavigationService
from app.services.rendering import render_filters, render_queue, render_search_results
from app.state.manager_session import ManagerSessionState


def test_filter_cycle_and_reset_do_not_touch_compose_state() -> None:
    state = ManagerSessionState(compose_mode="reply", compose_draft_text="draft")
    _cycle_filter(state, "assignment")
    _cycle_filter(state, "priority")
    assert state.compose_mode == "reply"
    assert state.compose_draft_text == "draft"
    assert state.filter_assignment_scope == "mine"
    assert state.filter_priority_scope == "high_or_urgent"

    _reset_filters(state)
    assert state.filter_assignment_scope == "any"
    assert state.filter_priority_scope == "any"
    assert state.compose_mode == "reply"


def test_search_results_render_no_results_and_rows() -> None:
    empty = render_search_results("missing", [], QueueFilters(lifecycle_scope="all"))
    assert "No cases found." in empty

    rows = render_search_results(
        "q-501",
        [
            SearchResultItem(
                case_id=uuid4(),
                case_display_number=501,
                linked_order_display_number=9901,
                customer_label="ACME",
                operational_status="active",
                waiting_state="waiting_manager",
                priority="vip",
                escalation_level="manager_attention",
                is_archived=False,
            )
        ],
        QueueFilters(priority_scope="vip", lifecycle_scope="all"),
    )
    assert "#501" in rows
    assert "O#9901" in rows
    assert "p:vip" in rows
    assert "priority=vip" in rows


def test_queue_render_shows_filter_state_and_archive_marker() -> None:
    rendered = render_queue(
        "archive",
        [
            QueueItem(
                case_id=uuid4(),
                case_display_number=711,
                customer_label="History Co",
                operational_status="closed",
                waiting_state="waiting_customer",
                assigned_manager_actor_id=None,
                priority="normal",
                escalation_level="none",
                last_customer_message_at=datetime.now(timezone.utc),
                is_archived=True,
            )
        ],
        0,
        QueueFilters(lifecycle_scope="archive"),
    )
    assert "Filters:" in rendered
    assert "[ARCHIVE]" in rendered


def test_navigation_home_clears_search_mode() -> None:
    nav = NavigationService()
    state = ManagerSessionState(panel_key="search:input", search_mode=True, search_query="acme")
    nav.go_home(state)
    assert state.search_mode is False
    assert state.search_query is None
    assert state.panel_key == "hub:home"
    assert "lifecycle=active" in render_filters(QueueFilters())
