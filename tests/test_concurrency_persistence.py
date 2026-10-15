from concurrent.futures import ThreadPoolExecutor

import app
from app_modules import auth, gantt, kanban


def _admin_session(username="admin@test.local"):
    state = {"messages": [], "suggested_project_keys": [], "api_usage": []}
    assert auth.login(state, username, "test-password-long")
    return state


def test_two_project_sessions_can_write_and_reload_independently():
    project_a = app.create_project("Concurrent Alpha")
    project_b = app.create_project("Concurrent Beta")
    state_a = _admin_session()
    state_b = _admin_session()

    def write_project(state, project_id, prefix):
        for index in range(3):
            gantt.add_task(
                state,
                project_id,
                {
                    "code": str(index + 1),
                    "name": f"{prefix} task {index + 1}",
                    "type": "Task",
                    "start": "2026-10-01",
                    "finish": "2026-10-02",
                    "progress": 0,
                    "resource": "",
                    "predecessors": [],
                    "details": "Concurrent persistence check",
                },
                sync_kanban=False,
            )
        card_id = kanban.add_card(
            state,
            project_id,
            f"{prefix} review",
            source="import",
        )
        kanban.move_card(state, project_id, card_id, "progress")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(write_project, state_a, project_a.id, "Alpha"),
            pool.submit(write_project, state_b, project_b.id, "Beta"),
        ]
        for future in futures:
            future.result()

    reloaded_a = _admin_session()
    reloaded_b = _admin_session()
    plan_a = gantt.get_plan(reloaded_a, project_a.id)
    plan_b = gantt.get_plan(reloaded_b, project_b.id)
    board_a = kanban.get_board(reloaded_a, project_a.id)
    board_b = kanban.get_board(reloaded_b, project_b.id)

    assert {task["name"] for task in plan_a["tasks"]} == {
        "Alpha task 1", "Alpha task 2", "Alpha task 3"
    }
    assert {task["name"] for task in plan_b["tasks"]} == {
        "Beta task 1", "Beta task 2", "Beta task 3"
    }
    assert any(card["title"] == "Alpha review" for card in board_a["cards"].values())
    assert any(card["title"] == "Beta review" for card in board_b["cards"].values())


def test_parallel_read_only_retrieval_does_not_cross_documents():
    documents = [
        {"scope": "general", "source": "alpha.txt", "text": "Alpha guidance"},
        {"scope": "general", "source": "beta.txt", "text": "Beta guidance"},
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda question: app.retrieve_information(question, documents, top_k=1),
            ["Alpha guidance", "Beta guidance"],
        ))

    assert results[0][0]["source"] == "alpha.txt"
    assert results[1][0]["source"] == "beta.txt"
