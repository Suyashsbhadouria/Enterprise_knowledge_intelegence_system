from ekcip_graph.intent import classify_graph_intent


def test_classify_detects_issue_and_blockers():
    intent = classify_graph_intent(
        "Who handles SCRUM-12 in project SCRUM? Any blockers?",
        issue_keys=["SCRUM-12"],
    )
    assert "SCRUM-12" in intent.issue_keys
    assert intent.wants_blockers is True
    assert intent.wants_assignee is True


def test_classify_project_overview():
    intent = classify_graph_intent("Summarize all issues in project ENG")
    assert "ENG" in intent.project_keys
    assert intent.wants_project_overview is True
