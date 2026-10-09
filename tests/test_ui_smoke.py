from datetime import date

from streamlit.testing.v1 import AppTest

import app
from app_modules import gantt
from app_modules import monitoring


def test_administrator_routes_render_without_exceptions():
    project = app.create_project("UI Smoke Project", code="UI-SMOKE")
    gantt.add_task(
        app.st.session_state,
        project.id,
        {
            "code": "1",
            "name": "Smoke-test task",
            "type": "Task",
            "start": date.today().isoformat(),
            "finish": date.today().isoformat(),
            "progress": 25,
            "resource": "",
            "predecessors": [],
            "details": "",
            "milestone": False,
        },
    )
    app.st.session_state.selected_project_id = project.id
    monitoring.log_interaction(
        user=app.st.session_state,
        project_id=None,
        assistant_mode="general",
        prompt_name="general_assistant",
        prompt_version=1,
        question="How should retrieval quality be evaluated?",
        response_text="Use authorised sources and evaluate the retrieved evidence.",
        latency_ms=120,
    )

    at = AppTest.from_string("import app\napp.main()", default_timeout=20).run()
    assert not at.exception
    assert any(
        "Project-specific assistant mode" in widget.value
        for widget in at.markdown
    )
    navigation = next(widget for widget in at.radio if widget.label == "Go to")
    for page in navigation.options:
        navigation.set_value(page).run()
        assert not at.exception, f"Route failed: {page}"
