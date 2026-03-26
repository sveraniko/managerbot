from app.state.manager_session import ManagerSessionState


class NavigationService:
    def open_panel(self, state: ManagerSessionState, panel_key: str) -> ManagerSessionState:
        state.back_panel_key = state.panel_key
        state.panel_key = panel_key
        return state

    def go_home(self, state: ManagerSessionState) -> ManagerSessionState:
        state.back_panel_key = state.panel_key
        state.panel_key = "hub:home"
        state.queue_key = None
        state.selected_case_id = None
        state.queue_offset = 0
        state.compose_mode = None
        state.compose_case_id = None
        state.compose_draft_text = None
        state.ai_case_id = None
        state.ai_analysis = None
        state.ai_error = None
        state.ai_analysis_meta = None
        state.ai_recommendation = None
        state.ai_recommendation_error = None
        state.ai_recommendation_meta = None
        state.search_mode = False
        state.search_query = None
        return state

    def back(self, state: ManagerSessionState) -> ManagerSessionState:
        if state.back_panel_key:
            state.panel_key = state.back_panel_key
            state.back_panel_key = None
        else:
            state.panel_key = "hub:home"
        return state
