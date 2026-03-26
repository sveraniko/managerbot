from __future__ import annotations

from uuid import UUID

from app.services.ai_reader import AIReaderAnalysis
from app.services.ai_recommender import AIRecommendation
from app.state.manager_session import ManagerSessionState


def clear_ai_snapshot(state: ManagerSessionState) -> None:
    state.ai_case_id = None
    state.ai_analysis = None
    state.ai_error = None
    state.ai_recommendation = None
    state.ai_recommendation_error = None


def bind_ai_result(state: ManagerSessionState, case_id: UUID, analysis: AIReaderAnalysis | None, error: str | None) -> None:
    state.ai_case_id = case_id
    state.ai_analysis = analysis.model_dump() if analysis else None
    state.ai_error = error


def bind_ai_recommendation(
    state: ManagerSessionState,
    case_id: UUID,
    recommendation: AIRecommendation | None,
    error: str | None,
) -> None:
    state.ai_case_id = case_id
    state.ai_recommendation = recommendation.model_dump(mode="json") if recommendation else None
    state.ai_recommendation_error = error


def analysis_for_case(state: ManagerSessionState, case_id: UUID) -> tuple[AIReaderAnalysis | None, str | None]:
    if not state.ai_case_id or state.ai_case_id != case_id:
        return None, None
    try:
        analysis = AIReaderAnalysis.model_validate(state.ai_analysis) if state.ai_analysis else None
        return analysis, state.ai_error
    except Exception:
        return None, "Stored AI analysis became invalid. Re-run AI."


def recommendation_for_case(state: ManagerSessionState, case_id: UUID) -> tuple[AIRecommendation | None, str | None]:
    if not state.ai_case_id or state.ai_case_id != case_id:
        return None, None
    try:
        recommendation = AIRecommendation.model_validate(state.ai_recommendation) if state.ai_recommendation else None
        return recommendation, state.ai_recommendation_error
    except Exception:
        return None, "Stored AI recommendation became invalid. Re-run AI."
