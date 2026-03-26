from uuid import uuid4

from app.services.navigation import NavigationService
from app.state.manager_session import ManagerSessionState


def test_home_queue_back_refresh_state_determinism() -> None:
    nav = NavigationService()
    state = ManagerSessionState()

    nav.open_panel(state, "queue:new")
    state.queue_key = "new"
    case_id = uuid4()

    nav.open_panel(state, "case:detail")
    state.selected_case_id = case_id
    assert state.panel_key == "case:detail"

    nav.back(state)
    assert state.panel_key == "queue:new"
    assert state.back_panel_key is None
    assert state.queue_key == "new"

    nav.go_home(state)
    assert state.panel_key == "hub:home"
    assert state.queue_key is None
    assert state.selected_case_id is None
    assert state.compose_mode is None
