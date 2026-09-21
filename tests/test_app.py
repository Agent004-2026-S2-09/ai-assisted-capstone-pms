from types import SimpleNamespace
import random

import pytest
from openpyxl import Workbook

import app


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@pytest.fixture
def isolated_knowledge_base(tmp_path, monkeypatch):
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_index = tmp_path / "knowledge_index"
    knowledge_base.mkdir()
    knowledge_index.mkdir()

    monkeypatch.setattr(app, "KB_DIR", knowledge_base)
    monkeypatch.setattr(app, "INDEX_DIR", knowledge_index)
    monkeypatch.setattr(app, "INDEX_FILE", knowledge_index / "index.json")
    return knowledge_base


def test_llm_plans_natural_search_without_requiring_capstone_keyword(monkeypatch):
    calls = []

    def fake_agentaus(messages):
        calls.append(messages)
        return {
            "choices": [{"message": {"content": (
                '{"action":"search","queries":["Phoenix protocol coordinator"]}'
            )}}]
        }

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)
    plan = app.plan_information_search(
        "Who coordinates the Phoenix protocol?",
        [{"source": "new_guidance.txt", "text": "Phoenix protocol"}],
        history=[],
    )

    assert plan == {
        "action": "search",
        "queries": ["Phoenix protocol coordinator"],
    }
    assert 'does not need to say "Capstone"' in calls[0][0]["content"]


def test_llm_search_planner_receives_history_for_follow_up(monkeypatch):
    calls = []

    def fake_agentaus(messages):
        calls.append(messages)
        return {
            "choices": [{"message": {"content": (
                '{"action":"search","queries":["deadline for the second project"]}'
            )}}]
        }

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)
    history = [
        {"role": "user", "content": "Show me suitable cybersecurity options"},
        {"role": "assistant", "content": "Here are three options."},
    ]
    plan = app.plan_information_search("When is the second one due?", [], history)

    assert plan["queries"] == ["deadline for the second project"]
    assert calls[0][1:] == [
        *history,
        {"role": "user", "content": "When is the second one due?"},
    ]


def test_api_messages_include_current_question_once():
    question = "UNIQUE_CURRENT_QUESTION"
    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": question},
    ]

    messages = app.build_api_messages("System instructions", question, history, 8)

    assert sum(message["content"].count(question) for message in messages) == 1
    assert messages[-1] == {"role": "user", "content": question}


def test_deleted_document_invalidates_index(isolated_knowledge_base, monkeypatch):
    document = isolated_knowledge_base / "guide.txt"
    document.write_text("Capstone milestone guidance", encoding="utf-8")
    indexed, errors = app.rebuild_index()
    assert indexed
    assert not errors

    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=SessionState()))
    document.unlink()

    assert app.ensure_index_is_current() == []
    documents, signature = app._load_index_payload()
    assert documents == []
    assert signature == app.calculate_kb_signature()


def test_unreadable_upload_does_not_replace_existing_document(
    isolated_knowledge_base,
):
    document = isolated_knowledge_base / "guide.txt"
    original = b"Original approved Capstone guidance"
    document.write_bytes(original)
    app.rebuild_index()

    with pytest.raises(ValueError, match="could not be processed"):
        app.install_uploaded_files([("guide.txt", b"")])

    assert document.read_bytes() == original


def test_upload_rolls_back_files_and_index_when_rebuild_fails(
    isolated_knowledge_base,
    monkeypatch,
):
    document = isolated_knowledge_base / "guide.txt"
    original = b"Original approved Capstone guidance"
    document.write_bytes(original)
    app.rebuild_index()
    original_index = app.INDEX_FILE.read_bytes()

    def fail_rebuild():
        raise OSError("simulated index failure")

    monkeypatch.setattr(app, "rebuild_index", fail_rebuild)

    with pytest.raises(OSError, match="simulated index failure"):
        app.install_uploaded_files([("guide.txt", b"Readable replacement guidance")])

    assert document.read_bytes() == original
    assert app.INDEX_FILE.read_bytes() == original_index


def test_duplicate_upload_names_are_rejected(isolated_knowledge_base):
    with pytest.raises(ValueError, match="duplicate filenames"):
        app.install_uploaded_files(
            [("guide.txt", b"First"), ("guide.txt", b"Second")]
        )


def test_new_upload_is_found_through_llm_search_without_capstone_keyword(
    isolated_knowledge_base,
    monkeypatch,
):
    app.install_uploaded_files(
        [
            (
                "new_guidance.txt",
                b"The Phoenix protocol coordinator is Zelda Quokka. "
                b"The emergency code is ORCHID-731.",
            )
        ]
    )
    documents = app.load_index()

    def fake_agentaus(messages):
        return {
            "choices": [{"message": {"content": (
                '{"action":"search","queries":["Phoenix protocol coordinator"]}'
            )}}]
        }

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)
    plan = app.plan_information_search(
        "Who coordinates the Phoenix protocol?",
        documents,
        history=[],
    )
    results = app.execute_search_plan(plan, documents)

    assert results
    assert results[0]["source"] == "new_guidance.txt"
    assert "Zelda Quokka" in results[0]["text"]


def test_exact_project_id_bypasses_ambiguous_page_number():
    documents = [
        {
            "text": "Unrelated content on page 47 for the 2026 S2 project list",
            "source": "catalogue.pdf",
            "location": "Page 47",
            "record_type": "document_chunk",
        },
        {
            "text": "Project ID: 2026-S2-47\nProject title: PII Scrubber",
            "source": "catalogue.pdf",
            "location": "Page 30",
            "record_type": "project",
            "project_id": "2026-S2-47",
            "title": "PII Scrubber",
        },
    ]

    results = app.retrieve_information("What is project 2026-S2-47?", documents)

    assert len(results) == 1
    assert results[0]["project_id"] == "2026-S2-47"
    assert results[0]["retrieval_reason"] == "exact project ID"


def test_exhaustive_catalogue_request_is_not_limited_by_top_k():
    documents = [
        {
            "text": f"Project ID: 2026-S2-{number:02d}\nProject title: Title {number}",
            "source": "catalogue.pdf",
            "location": f"Page {number}",
            "record_type": "project",
            "project_id": f"2026-S2-{number:02d}",
            "title": f"Title {number}",
        }
        for number in range(1, 16)
    ]

    results = app.retrieve_information(
        "List all projects for semester 2 2026", documents, top_k=2
    )

    assert len(results) == 15
    assert all(result["exhaustive"] for result in results)


def test_long_catalogue_is_parsed_into_complete_project_records():
    catalogue = app.KB_DIR / "List of project S2 2026 V.1.pdf"
    if not catalogue.exists():
        pytest.skip("The catalogue integration fixture is not available")

    records = [
        item for item in app.process_document(catalogue)
        if item.get("record_type") == "project"
    ]
    pii = [item for item in records if item.get("project_id") == "2026-S2-47"]

    assert len({item["project_id"] for item in records}) == 68
    assert len(pii) == 1
    assert "PII Scrubber" in pii[0]["title"]
    assert "Personally Identifiable" in pii[0]["text"]
    assert pii[0]["location"] == "Page 30"


def test_csv_rows_and_headers_are_indexed_and_searchable(tmp_path):
    csv_file = tmp_path / "project_risks.csv"
    csv_file.write_text(
        "Risk owner,Description,Rating\n"
        "Alice,Vendor delivery delay,High\n"
        "Bob,Testing environment unavailable,Medium\n",
        encoding="utf-8",
    )

    documents = app.process_document(csv_file)
    results = app.retrieve_information(
        "Who owns the vendor delivery delay in project risks?", documents
    )

    assert ".csv" in app.SUPPORTED_EXTENSIONS
    assert documents[0]["record_type"] == "table_block"
    assert "Risk owner=Alice" in documents[0]["text"]
    assert results
    assert "Vendor delivery delay" in results[0]["text"]


def test_powerpoint_table_cells_are_extracted(tmp_path):
    presentation = app.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(2, 2, 0, 0, 5000000, 1000000).table
    table.cell(0, 0).text = "Milestone"
    table.cell(0, 1).text = "Due date"
    table.cell(1, 0).text = "Prototype review"
    table.cell(1, 1).text = "15 September"
    pptx_file = tmp_path / "schedule.pptx"
    presentation.save(pptx_file)

    documents = app.process_document(pptx_file)

    assert "Table row 2: Prototype review | 15 September" in documents[0]["text"]


def test_word_headers_body_and_tables_are_all_indexed(tmp_path):
    document = app.Document()
    document.sections[0].header.paragraphs[0].text = "Policy version 7"
    document.add_heading("Assessment", level=1)
    document.add_paragraph("Submit the approved final report.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Owner"
    table.cell(0, 1).text = "Capstone team"
    docx_file = tmp_path / "guidance.docx"
    document.save(docx_file)

    indexed = app.process_document(docx_file)
    combined = "\n".join(item["text"] for item in indexed)

    assert "Policy version 7" in combined
    assert "Submit the approved final report" in combined
    assert "Table row 1: Owner | Capstone team" in combined


def test_excel_formulas_and_values_are_preserved(tmp_path):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Budget"
    worksheet.append(["Item", "Cost", "Taxed cost"])
    worksheet.append(["Hosting", 100, "=B2*1.1"])
    xlsx_file = tmp_path / "budget.xlsx"
    workbook.save(xlsx_file)

    indexed = app.process_document(xlsx_file)
    combined = "\n".join(item["text"] for item in indexed)

    assert "A2=Hosting" in combined
    assert "C2==B2*1.1" in combined


def test_named_non_project_file_is_not_forced_into_project_catalogue_search():
    documents = [
        {
            "text": "Project ID: 2026-S2-01\nProject title: Unrelated project",
            "source": "catalogue.pdf",
            "location": "Page 1",
            "record_type": "project",
            "project_id": "2026-S2-01",
            "title": "Unrelated project",
        },
        {
            "text": "Headers: Risk | Owner\nRow 2: Risk=Delay | Owner=Alice",
            "source": "risks.csv",
            "location": "Rows 1-2",
            "record_type": "table_block",
        },
    ]

    results = app.retrieve_information("List all rows in risks.csv", documents)

    assert results
    assert all(result["source"] == "risks.csv" for result in results)


def test_requested_projects_are_random_non_repeating_batches_and_answer_uses_llm(
    monkeypatch,
):
    documents = [
        {
            "text": f"Project ID: 2026-S2-{number:02d}\nProject title: Title {number}",
            "source": "catalogue.pdf",
            "location": f"Page {number}",
            "record_type": "project",
            "project_id": f"2026-S2-{number:02d}",
            "title": f"Title {number}",
            "sponsor": f"Sponsor {number}",
            "page_number": number,
        }
        for number in range(1, 13)
    ]
    question = "please list 5 semester 2 capstone project that are avaiable this year"
    api_calls = []

    def fake_agentaus(messages):
        api_calls.append(messages)
        return {
            "choices": [
                {
                    "message": {
                        "content": "LLM-generated answer covering 2026-S2-01 through 2026-S2-05"
                    }
                }
            ]
        }

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)

    first = app.retrieve_information(question, documents, rng=random.Random(11))
    first_keys = {app.project_record_key(item) for item in first}
    second_question = "Can you suggest 5 more projects?"
    second = app.retrieve_information(
        second_question,
        documents,
        excluded_project_keys=first_keys,
        rng=random.Random(12),
    )
    answer = app.generate_response(question, first)

    assert len(first) == 5
    assert len(second) == 5
    assert first_keys.isdisjoint({app.project_record_key(item) for item in second})
    assert all(item["requested_list"] for item in first)
    assert all(item["requested_list"] for item in second)
    assert "LLM-generated answer" in answer
    assert "Sources" not in answer
    assert "catalogue.pdf" not in answer
    assert len(api_calls) == 2  # generation plus groundedness validation
    generation_prompt = api_calls[0][0]["content"]
    assert "Present all and only those selected projects" in generation_prompt
    assert all(item["project_id"] in generation_prompt for item in first)
    unselected_id = next(
        item["project_id"] for item in documents if app.project_record_key(item) not in first_keys
    )
    assert unselected_id not in generation_prompt


def test_source_sections_are_removed_from_assistant_output():
    answer = (
        "Here are five suitable projects.\n\n"
        "**Sources**\n\n"
        "- *List of project S2 2026 V.1.pdf* — pages 8–9"
    )

    assert app.remove_source_section(answer) == "Here are five suitable projects."


def test_no_retrieval_results_still_use_llm_api(monkeypatch):
    api_calls = []

    def fake_agentaus(messages):
        api_calls.append(messages)
        return {"choices": [{"message": {"content": "LLM handled missing context"}}]}

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)

    answer = app.generate_response("Unknown Capstone question", [])

    assert "LLM handled missing context" in answer
    assert len(api_calls) == 2


def test_non_capstone_response_uses_llm_api(monkeypatch):
    api_calls = []

    def fake_agentaus(messages):
        api_calls.append(messages)
        return {"choices": [{"message": {"content": "LLM scope response"}}]}

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)

    answer = app.generate_non_capstone_response("What is the weather?")

    assert answer == "LLM scope response"
    assert len(api_calls) == 1


def test_private_context_reports_items_omitted_by_token_budget():
    results = [
        {
            "text": "Detailed milestone guidance " * 12,
            "source": f"guide-{number}.pdf",
            "location": f"Page {number}",
        }
        for number in range(1, 6)
    ]

    context, metadata = app.build_private_context(
        results,
        "What are the milestones?",
        token_budget=150,
        return_metadata=True,
    )

    assert context
    assert metadata["estimated_tokens"] <= 150
    assert metadata["included_items"] < metadata["total_items"]
    assert metadata["truncated"] is True


def test_conversation_history_is_limited_by_token_budget(monkeypatch):
    monkeypatch.setattr(app, "MAX_CONVERSATION_HISTORY_TOKENS", 12)
    history = [
        {"role": "user", "content": "old " * 30},
        {"role": "assistant", "content": "recent reply"},
    ]

    messages = app.build_api_messages("System", "Current question", history, 8)

    assert messages == [
        {"role": "system", "content": "System"},
        {"role": "assistant", "content": "recent reply"},
        {"role": "user", "content": "Current question"},
    ]


def test_agentaus_sse_stream_is_parsed_and_usage_recorded(monkeypatch):
    class FakeResponse:
        headers = {"Content-Type": "text/event-stream; charset=utf-8"}

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter([
                'data: {"choices":[{"delta":{"content":"Hello "}}]}',
                'data: {"choices":[{"delta":{"content":"there"}}]}',
                'data: {"choices":[],"usage":{"input_tokens":12,"output_tokens":2}}',
                "data: [DONE]",
            ])

        def close(self):
            return None

    request_details = {}

    def fake_post(*args, **kwargs):
        request_details.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")
    monkeypatch.setattr(app, "API_ENDPOINT", "https://example.invalid/chat")
    monkeypatch.setattr(app.requests, "post", fake_post)
    app.st.session_state.api_usage = []

    chunks = list(app.call_agentaus_stream([], stage="test"))

    assert "".join(chunks) == "Hello there"
    assert request_details["json"]["stream"] is True
    assert request_details["stream"] is True
    assert app.st.session_state.api_usage[-1]["total_tokens"] == 14


def test_api_service_error_message_explains_unreachable_endpoint():
    error = app.requests.exceptions.ConnectionError("DNS lookup failed")

    message = app.api_service_error_message(error)

    assert "could not be reached" in message
    assert "public HTTPS URL" in message


def test_api_service_error_message_includes_provider_http_status():
    response = SimpleNamespace(status_code=401)
    error = app.requests.exceptions.HTTPError(response=response)

    assert app.api_service_error_message(error) == (
        "The AI service rejected the request (HTTP 401)."
    )


def test_stream_filter_removes_sources_without_hiding_long_answer():
    visible = "A" * 120
    chunks = list(app._without_source_section([visible, "\nSources\nprivate.pdf"]))

    assert len(chunks) > 1
    assert "".join(chunks).rstrip() == visible


def test_grounded_stream_shows_validation_instead_of_draft(monkeypatch):
    calls = []

    def fake_agentaus(messages):
        calls.append(messages)
        return {"choices": [{"message": {"content": "Unvalidated draft"}}]}

    def fake_stream(messages, stage="answer"):
        assert stage == "answer_validation"
        assert "strict factual editor" in messages[0]["content"]
        yield "Checked "
        yield "answer"

    monkeypatch.setattr(app, "call_agentaus", fake_agentaus)
    monkeypatch.setattr(app, "call_agentaus_stream", fake_stream)
    monkeypatch.setenv("ENABLE_ANSWER_VALIDATION", "true")

    answer = "".join(app.generate_response_stream("Question", []))

    assert answer == "Checked answer"
    assert "Unvalidated draft" not in answer
    assert len(calls) == 1


class UploadedFile:
    def __init__(self, name, content=b"content"):
        self.name = name
        self.size = len(content)
        self._content = content

    def getbuffer(self):
        return self._content


@pytest.fixture
def isolated_project_storage(tmp_path, monkeypatch):
    project_data = tmp_path / "project_data"
    project_knowledge = tmp_path / "project_knowledge"
    project_data.mkdir()
    project_knowledge.mkdir()

    monkeypatch.setattr(app, "PROJECT_DATA_DIR", project_data)
    monkeypatch.setattr(app, "PROJECT_KNOWLEDGE_DIR", project_knowledge)
    monkeypatch.setattr(app, "PROJECTS_FILE", project_data / "projects.json")
    return project_data, project_knowledge


def test_project_id_rejects_path_traversal():
    for value in ("../secret", "project/other", "Project Name", ""):
        with pytest.raises(ValueError):
            app.validate_project_id(value)


def test_project_lifecycle_uses_revisions_and_removes_folders(isolated_project_storage):
    project_data, project_knowledge = isolated_project_storage

    created = app.create_project("AI Assisted Capstone")
    first = app.get_project(created.id)
    second = app.get_project(created.id)

    first.description = "First update"
    app.update_project(first)

    second.description = "Stale update"
    with pytest.raises(ValueError, match="another session"):
        app.update_project(second)

    app.delete_project(created.id)

    assert app.get_project(created.id) is None
    assert not (project_data / created.id).exists()
    assert not (project_knowledge / created.id).exists()


def test_project_access_is_limited_to_assigned_students_and_mentors(isolated_project_storage):
    alpha = app.create_project("Alpha Project", mentor="Dr Mentor")
    beta = app.create_project("Beta Project", mentor="Other Mentor")
    alpha.team = [
        {"id": "1", "name": "Prachi Sherkar", "role": "Student"},
        {"id": "2", "name": "Dr Helper", "role": "Mentor"},
    ]
    app.update_project(alpha)

    assert app.can_access_project(alpha, "Student", "Prachi Sherkar")
    assert not app.can_access_project(beta, "Student", "Prachi Sherkar")
    assert app.can_access_project(alpha, "Mentor", "Dr Mentor")
    assert app.can_access_project(alpha, "Mentor", "Dr Helper")
    assert not app.can_access_project(beta, "Mentor", "Dr Mentor")
    assert not app.can_access_project(alpha, "Convenor", "Dr Mentor")
    alpha.team.append({"id": "3", "name": "Dr Convenor", "role": "Course Convenor"})
    app.update_project(alpha)
    alpha = app.get_project(alpha.id)
    assert app.can_access_project(alpha, "Convenor", "Dr Convenor")
    assert not app.can_access_project(alpha, "Convenor", "Prachi Sherkar")
    assert {project.id for project in app.get_accessible_projects("Student", "Prachi Sherkar")} == {
        alpha.id
    }


def test_project_retrieval_stays_inside_selected_project(isolated_project_storage):
    alpha = app.create_project("Alpha Project")
    beta = app.create_project("Beta Project")

    alpha_docs = [
        {
            "text": "Alpha requires a mobile application.",
            "source": "alpha.txt",
            "location": "Document",
            "scope": "project",
            "project_id": alpha.id,
        }
    ]
    beta_docs = [
        {
            "text": "Beta requires a satellite dashboard.",
            "source": "beta.txt",
            "location": "Document",
            "scope": "project",
            "project_id": beta.id,
        }
    ]

    results = app.retrieve_project_information(
        "What does the mobile application require?",
        alpha_docs + beta_docs,
        alpha.id,
    )

    assert results
    assert all(result["project_id"] == alpha.id for result in results)
    assert "satellite dashboard" not in "\n".join(result["text"] for result in results)


def test_project_upload_rolls_back_files_and_index_when_rebuild_fails(
    isolated_project_storage,
    monkeypatch,
):
    project = app.create_project("Rollback Project")
    project_dir = app.get_project_knowledge_dir(project.id)
    original = project_dir / "guide.txt"
    original.write_text("Original approved project guidance", encoding="utf-8")
    app.rebuild_project_index(project.id)
    original_index = app.get_project_index_file(project.id).read_bytes()

    def fail_rebuild(project_id):
        raise OSError("simulated project index failure")

    monkeypatch.setattr(app, "rebuild_project_index", fail_rebuild)

    with pytest.raises(OSError, match="simulated project index failure"):
        app.install_project_uploaded_files(
            project.id,
            [("guide.txt", b"Readable replacement guidance")],
        )

    assert original.read_text(encoding="utf-8") == "Original approved project guidance"
    assert app.get_project_index_file(project.id).read_bytes() == original_index


def test_project_document_upload_and_stale_index_reload(isolated_project_storage):
    project = app.create_project("Document Project")

    count = app.save_project_documents(
        project.id,
        [UploadedFile("requirements.txt", b"The sponsor requires offline mode.")],
    )
    documents = app.load_project_index(project.id)

    assert count == 1
    assert documents
    assert all(document["scope"] == "project" for document in documents)
    assert all(document["project_id"] == project.id for document in documents)

    project_file = app.get_project_knowledge_dir(project.id) / "requirements.txt"
    project_file.write_text("The sponsor requires audit logging.", encoding="utf-8")

    reloaded = app.load_project_index(project.id)

    assert any("audit logging" in document["text"] for document in reloaded)


def test_question_analytics_are_recorded_and_summarised(isolated_project_storage):
    app.record_question_analytics(
        "How do we handle stakeholder feedback for our prototype?",
        project_id="alpha-project",
        user_role="Student",
    )

    records = app.load_question_analytics()
    summary = app.summarise_question_analytics(records)

    assert records[0]["project_id"] == "alpha-project"
    assert records[0]["role"] == "Student"
    assert "stakeholder" in records[0]["keywords"]
    assert summary["total"] == 1
    assert summary["by_project"] == [("alpha-project", 1)]


def test_pptx_extracts_shape_alt_text(tmp_path):
    path = tmp_path / "slides.pptx"
    presentation = app.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(0, 0, 100, 100)
    shape.text = "Architecture overview"
    shape.element.xpath(".//p:cNvPr")[0].set(
        "descr",
        "Diagram showing the retrieval and compression process.",
    )
    presentation.save(path)

    chunks = app.extract_pptx(path)

    assert chunks
    assert "retrieval and compression process" in chunks[0]["text"]
