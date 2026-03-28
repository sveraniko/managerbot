from __future__ import annotations

import re
from uuid import UUID

from app.state.manager_session import ManagerSessionState


class ComposeStateService:
    _CUSTOMER_VISIBLE_TERM_GUARDRAILS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bmoq\b", flags=re.IGNORECASE), "Use “Min order” instead of “MOQ”."),
        (re.compile(r"\bstep\b", flags=re.IGNORECASE), "Use “Increment” instead of “step”."),
    )

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

    def start_reply_from_ai(self, state: ManagerSessionState, case_id: UUID, draft_text: str) -> bool:
        if state.selected_case_id != case_id or not draft_text.strip():
            return False
        self.start_reply(state, case_id)
        state.compose_draft_text = draft_text.strip()
        return True

    def start_note_from_ai(self, state: ManagerSessionState, case_id: UUID, draft_text: str) -> bool:
        if state.selected_case_id != case_id or not draft_text.strip():
            return False
        self.start_note(state, case_id)
        state.compose_draft_text = draft_text.strip()
        return True

    def start_note_template(self, state: ManagerSessionState, case_id: UUID, template_text: str) -> bool:
        if state.selected_case_id != case_id or not template_text.strip():
            return False
        self.start_note(state, case_id)
        state.compose_draft_text = template_text.strip()
        return True

    def cancel(self, state: ManagerSessionState) -> ManagerSessionState:
        state.compose_mode = None
        state.compose_case_id = None
        state.compose_draft_text = None
        return state

    def back_to_case(self, state: ManagerSessionState) -> ManagerSessionState:
        return self.cancel(state)

    def is_stale(self, state: ManagerSessionState) -> bool:
        return bool(state.compose_mode and state.compose_case_id and state.compose_case_id != state.selected_case_id)

    def customer_visible_guardrail_issues(self, draft_text: str) -> list[str]:
        issues: list[str] = []
        for pattern, guidance in self._CUSTOMER_VISIBLE_TERM_GUARDRAILS:
            if pattern.search(draft_text):
                issues.append(guidance)
        return issues
