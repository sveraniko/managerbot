from uuid import uuid4

from app.services.compose import ComposeStateService
from app.state.manager_session import ManagerSessionState


def test_start_reply_and_note_set_distinct_compose_modes() -> None:
    service = ComposeStateService()
    case_id = uuid4()
    state = ManagerSessionState(selected_case_id=case_id)

    service.start_reply(state, case_id)
    assert state.compose_mode == "reply"
    assert state.compose_case_id == case_id

    service.start_note(state, case_id)
    assert state.compose_mode == "note"
    assert state.compose_case_id == case_id


def test_cancel_and_stale_detection_are_safe() -> None:
    service = ComposeStateService()
    selected_case_id = uuid4()
    stale_case_id = uuid4()
    state = ManagerSessionState(selected_case_id=selected_case_id)
    service.start_reply(state, stale_case_id)

    assert service.is_stale(state) is True

    service.cancel(state)
    assert state.compose_mode is None
    assert state.compose_case_id is None
    assert state.compose_draft_text is None


def test_back_to_case_clears_compose_context() -> None:
    service = ComposeStateService()
    case_id = uuid4()
    state = ManagerSessionState(selected_case_id=case_id)
    service.start_reply(state, case_id)
    state.compose_draft_text = "draft"

    service.back_to_case(state)

    assert state.compose_mode is None
    assert state.compose_case_id is None
    assert state.compose_draft_text is None


def test_ai_draft_adoption_is_case_bound_and_non_autonomous() -> None:
    service = ComposeStateService()
    case_id = uuid4()
    other_case_id = uuid4()
    state = ManagerSessionState(selected_case_id=case_id)

    ok_reply = service.start_reply_from_ai(state, case_id, "Draft reply text")
    assert ok_reply is True
    assert state.compose_mode == "reply"
    assert state.compose_draft_text == "Draft reply text"

    service.cancel(state)
    ok_note = service.start_note_from_ai(state, case_id, "Draft note text")
    assert ok_note is True
    assert state.compose_mode == "note"
    assert state.compose_draft_text == "Draft note text"

    service.cancel(state)
    rejected = service.start_reply_from_ai(state, other_case_id, "Wrong case draft")
    assert rejected is False
    assert state.compose_mode is None
