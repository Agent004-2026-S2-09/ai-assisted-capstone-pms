## File: tests/test_evidence_retrieval.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test evidence retrieval functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

from app_modules.evidence_retrieval import filter_current_documents, retrieve


def test_metadata_filter_removes_retired_versions_before_ranking():
    """Retired evidence must never enter lexical or semantic ranking."""
    documents = [
        {
            "source": "policy.pdf",
            "text": "Old policy says use the retired process.",
            "document_status": "superseded",
        },
        {
            "source": "policy.pdf",
            "text": "Current policy says use the approved process.",
            "document_status": "current",
        },
    ]

    eligible = filter_current_documents(documents)
    assert len(eligible) == 1
    assert "Current policy" in eligible[0]["text"]

    results = retrieve(documents, "What process is approved?", top_k=10)
    assert all("retired" not in item["text"] for item in results)


def test_legacy_documents_without_lifecycle_metadata_remain_searchable():
    """Missing migration metadata must preserve existing indexed behaviour."""
    documents = [{"source": "legacy.pdf", "text": "Legacy approved guidance."}]

    assert filter_current_documents(documents) == documents
    assert retrieve(documents, "What guidance is approved?")


def test_general_vocabulary_aliases_retrieve_matching_capstone_guidance():
    """Student terminology should match equivalent wording in guidance."""
    documents = [{
        "source": "Capstone Guide.pdf",
        "text": "Each sprint must produce an assessment deliverable for review by the supervisor.",
    }]

    results = retrieve(
        documents,
        "What deliverables are expected in each iteration from my advisor?",
    )

    assert results
    assert results[0]["source"] == "Capstone Guide.pdf"


def test_access_level_filter_is_fail_closed_when_requested():
    """An explicit caller access policy must exclude restricted candidates."""
    documents = [
        {"source": "private.pdf", "text": "Private answer.", "access_level": "mentor"},
        {"source": "public.pdf", "text": "Public answer.", "access_level": "student"},
    ]

    results = retrieve(
        documents,
        "What answer is available?",
        allowed_access_levels={"student"},
    )
    assert results
    assert all(item["access_level"] == "student" for item in results)


def test_assessment_question_returns_complete_relevant_table_without_catalogue_noise():
    """
    Function: test_assessment_question_returns_complete_relevant_table_without_catalogue_noise
    Purpose: Execute the test assessment question returns complete relevant table without catalogue noise operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "table_block",
            "source": "project_catalogue.csv",
            "location": "Rows 2-3",
            "text": (
                "Headers: Project ID | Project Title | Description\n"
                "Row 2: Project ID=1 | Project Title=AI assessment tool | Description=Artificial intelligence project\n"
                "Row 3: Project ID=2 | Project Title=Lecture helper | Description=Lecture project"
            ),
        },
        {
            "record_type": "table_block",
            "source": "assessments.csv",
            "location": "Rows 2-4",
            "text": (
                "Headers: Assessment | Due Date | Points Possible\n"
                "Row 2: Assessment=Poster | Due Date=30/10/2026 | Points Possible=10\n"
                "Row 3: Assessment=Report | Due Date=1/11/2026 | Points Possible=100\n"
                "Row 4: Assessment=Presentation | Due Date=6/11/2026 | Points Possible=15"
            ),
        },
    ]

    results = retrieve(documents, "What are the assessments between now and the end of the semester?")

    assert results[0]["source"] == "assessments.csv"
    assert results[0]["retrieval_complete"] is True
    assert "Row 2" in results[0]["text"] and "Row 4" in results[0]["text"]


def test_ethics_question_prefers_source_title_over_incidental_lecture_word():
    """
    Function: test_ethics_question_prefers_source_title_over_incidental_lecture_word
    Purpose: Execute the test ethics question prefers source title over incidental lecture word operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Reflection Rubric.docx",
            "location": "Document",
            "text": "Describe an aspect of the course or lecture in your reflection.",
        },
        {
            "record_type": "document_chunk",
            "source": "Professionalism and Ethics Guest Lecture.pdf",
            "location": "Page 6",
            "text": "The lecture covered professional ethics and the public interest.",
        },
    ]

    results = retrieve(documents, "What was covered in the ethics lecture?")

    assert results[0]["source"] == "Professionalism and Ethics Guest Lecture.pdf"


def test_genai_acknowledgement_question_prefers_relevant_template():
    """
    Function: test_genai_acknowledgement_question_prefers_relevant_template
    Purpose: Execute the test genai acknowledgement question prefers relevant template operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Week 10 Assessment Tutorial.pdf",
            "location": "Page 12",
            "text": "Do not use Gen AI to produce the poster.",
        },
        {
            "record_type": "document_chunk",
            "source": "Student_Template_for_GenAI_Acknowledgement.pdf",
            "location": "Page 1",
            "text": "You must properly acknowledge generative artificial intelligence used in an assessment.",
        },
    ]

    results = retrieve(documents, "How do I reference AI in an assessment?")

    assert results[0]["source"] == "Student_Template_for_GenAI_Acknowledgement.pdf"


def test_week_question_prefers_exact_week_evidence():
    """
    Function: test_week_question_prefers_exact_week_evidence
    Purpose: Execute the test week question prefers exact week evidence operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Week 1 Lecture.pdf",
            "location": "Page 1",
            "text": "Week 1 introduction.",
        },
        {
            "record_type": "document_chunk",
            "source": "Teaching Weeks.docx",
            "location": "Document",
            "text": "Week 7 | 21 Sep - 27 Sep 2026 | Completed",
        },
    ]

    results = retrieve(documents, "What were the Week 7 lectures?")

    assert results[0]["source"] == "Teaching Weeks.docx"


def test_hybrid_retrieval_can_promote_semantic_paraphrase():
    """
    Function: test_hybrid_retrieval_can_promote_semantic_paraphrase
    Purpose: Execute the test hybrid retrieval can promote semantic paraphrase operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "team-guide.pdf",
            "location": "Page 1",
            "text": "The team should meet with the sponsor before each major milestone.",
        },
        {
            "record_type": "document_chunk",
            "source": "unrelated.pdf",
            "location": "Page 1",
            "text": "The final report uses the required submission template.",
        },
    ]

    def semantic_scores(question, items):
        """
        Function: semantic_scores
        Purpose: Execute the semantic scores operation.
        Inputs:
                question (value): Caller-provided input.
                items (value): Caller-provided input.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
        assert question == "How often should we meet the client?"
        return [0.94, 0.05]

    results = retrieve(
        documents,
        "How often should we meet the client?",
        semantic_scorer=semantic_scores,
        semantic_backend="test-model",
    )

    assert results[0]["source"] == "team-guide.pdf"
    assert results[0]["retrieval_mode"] in {"semantic", "hybrid"}
    assert results[0]["semantic_score"] == 0.94
    assert results[0]["semantic_backend"] == "test-model"


def test_hybrid_retrieval_keeps_exact_lexical_match_ahead_of_weak_semantics():
    """
    Function: test_hybrid_retrieval_keeps_exact_lexical_match_ahead_of_weak_semantics
    Purpose: Execute the test hybrid retrieval keeps exact lexical match ahead of weak semantics operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "assessment-schedule.csv",
            "location": "Rows 2-3",
            "text": "Headers: Assessment | Due Date\nRow 2: Assessment=Poster | Due Date=30/10/2026",
        },
        {
            "record_type": "document_chunk",
            "source": "general-guide.pdf",
            "location": "Page 1",
            "text": "General guidance about project planning and meetings.",
        },
    ]

    results = retrieve(
        documents,
        "When is the poster assessment due?",
        semantic_scores=[0.99, 0.99],
        semantic_backend="test-model",
    )

    assert results[0]["source"] == "assessment-schedule.csv"
    assert results[0]["lexical_score"] > 0


def test_assessment_schedule_pdf_beats_weekly_assessment_guidance():
    """
    Function: test_assessment_schedule_pdf_beats_weekly_assessment_guidance
    Purpose: Execute the test assessment schedule pdf beats weekly assessment guidance operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Week 10 Tutorial - Assessment Details.pdf",
            "location": "Page 1",
            "text": "Assessment details and guidance for completing the final report.",
        },
        {
            "record_type": "document_chunk",
            "source": "Assessments_S2_2026.pdf",
            "location": "Page 1",
            "text": (
                "Assessments S2 2026\n"
                "Assessment Submission Type Assignment URL Due Date and Time Available Until Points Possible\n"
                "Poster Group https://example.test/poster 30/10/2026 23:59 2/11/2026 23:59 10"
            ),
        },
    ]

    results = retrieve(documents, "What are the remaining assessments and their due dates?")

    assert results[0]["source"] == "Assessments_S2_2026.pdf"


def test_proposal_question_does_not_promote_reflection_rubric():
    """
    Function: test_proposal_question_does_not_promote_reflection_rubric
    Purpose: Execute the test proposal question does not promote reflection rubric operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Reflection Rubric.docx",
            "location": "Document",
            "text": "Reflect on the project plan and proposal in your weekly journal.",
        },
        {
            "record_type": "document_chunk",
            "source": "Tutorial Slides week 2.pdf",
            "location": "Page 8",
            "text": "Project Proposal and Plan Report: problem definition, background study, and requirements analysis.",
        },
    ]

    results = retrieve(documents, "What should be included in the Project Proposal and Plan Report?")

    assert results[0]["source"] == "Tutorial Slides week 2.pdf"


def test_project_assessment_schedule_prefers_complete_table_for_schedule_question():
    """
    Function: test_project_assessment_schedule_prefers_complete_table_for_schedule_question
    Purpose: Execute the test project assessment schedule prefers complete table for schedule question operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "document_chunk",
            "source": "Project Proposal and Plan Report.docx",
            "location": "Document",
            "text": "The project plan includes assessment milestones and deliverables.",
        },
        {
            "record_type": "table_block",
            "source": "Assessments_S2_2026.csv",
            "location": "Rows 1-3",
            "text": (
                "Headers: Assessment | Due Date and Time | Available Until\n"
                "Row 2: Assessment=Poster | Due Date and Time=30/10/2026 23:59 | "
                "Available Until=02/11/2026 23:59"
            ),
        },
    ]

    results = retrieve(documents, "What assessment schedule information is stored?")

    assert results
    assert results[0]["source"] == "Assessments_S2_2026.csv"
    assert results[0]["record_type"] == "table_block"


def test_risk_question_can_retrieve_risk_tables_without_table_keyword():
    """
    Function: test_risk_question_can_retrieve_risk_tables_without_table_keyword
    Purpose: Execute the test risk question can retrieve risk tables without table keyword operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "record_type": "table_block",
            "source": "Risk Management Framework Template.xlsx",
            "location": "Sheet1 rows 1-3",
            "text": (
                "Headers: Risk Type | Risk | Likelihood | Impact / Consequence | Action | Planning / Control\n"
                "Row 2: Risk Type=Schedule | Risk=Timeline may cause delays | Likelihood=5 | "
                "Impact / Consequence=3 | Action=Mitigate | Planning / Control=Monitor velocity and descope low priority items"
            ),
        },
    ]

    results = retrieve(documents, "How do the risk-management documents and project planning guidance support risk control?")

    assert results
    assert results[0]["source"] == "Risk Management Framework Template.xlsx"
