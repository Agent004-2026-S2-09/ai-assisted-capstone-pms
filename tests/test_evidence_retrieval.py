from app_modules.evidence_retrieval import retrieve


def test_assessment_question_returns_complete_relevant_table_without_catalogue_noise():
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
