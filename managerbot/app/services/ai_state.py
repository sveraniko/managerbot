from __future__ import annotations

from uuid import UUID

from app.services.ai_reader import AIReaderAnalysis
from app.state.manager_session import ManagerSessionState


def clear_ai_snapshot(state: ManagerSessionState) -> None:
    state.ai_case_id = None
    state.ai_analysis = None
    state.ai_error = None


def bind_ai_result(state: ManagerSessionState, case_id: UUID, analysis: AIReaderAnalysis | None, error: str | None) -> None:
    state.ai_case_id = case_id
    state.ai_analysis = analysis.model_dump() if analysis else None
    state.ai_error = error


def analysis_for_case(state: ManagerSessionState, case_id: UUID) -> tuple[AIReaderAnalysis | None, str | None]:
    if not state.ai_case_id or state.ai_case_id != case_id:
        return None, None
    analysis = AIReaderAnalysis.model_validate(state.ai_analysis) if state.ai_analysis else None
    return analysis, state.ai_error
