from __future__ import annotations

from uuid import UUID

from app.state.manager_session import ManagerSessionState


class ComposeStateService:
    def start_reply(self, state: ManagerSessionState, case_id: UUID) -> ManagerSessionState:
        state.compose_mode = "reply"
        state.compose_case_id = case_id
        state.compose_draft_text = None
        return state

    def start_note(self, state: ManagerSessionState, case_id: UUID) -> ManagerSessionState:
        state.compose_mode = "note"
        state.compose_case_id = case_id
        state.compose_draft_text = None
        return state

    def cancel(self, state: ManagerSessionState) -> ManagerSessionState:
        state.compose_mode = None
        state.compose_case_id = None
        state.compose_draft_text = None
        return state

    def back_to_case(self, state: ManagerSessionState) -> ManagerSessionState:
        return self.cancel(state)

    def is_stale(self, state: ManagerSessionState) -> bool:
        return bool(state.compose_mode and state.compose_case_id and state.compose_case_id != state.selected_case_id)
