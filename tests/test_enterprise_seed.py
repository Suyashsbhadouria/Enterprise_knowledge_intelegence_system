from ekcip_api.services.dev_seed import build_sample_queries
from ekcip_graph.enterprise_seed import _confluence_rows, _jira_rows


def test_jira_rows_from_real_documents():
    rows = _jira_rows(
        [
            {
                "source_id": "SCRUM-2",
                "title": "Task 2",
                "metadata": {
                    "project": "SCRUM",
                    "status": "In Progress",
                    "assignee": "Alex",
                    "assignee_account_id": "acc-1",
                    "assignee_email": "alex@company.com",
                },
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["issue_key"] == "SCRUM-2"
    assert rows[0]["assignee_id"] == "acc-1"


def test_build_sample_queries_uses_real_keys():
    queries = build_sample_queries(
        project_keys=["SCRUM"],
        issue_keys=["SCRUM-2", "SCRUM-1"],
        issue_titles=["Task 2", "Task 1"],
        confluence_pages=[
            {"page_id": "123", "title": "Architecture", "space_key": "ENG"},
        ],
    )
    assert any("SCRUM-2" in q for q in queries)
    assert any("Architecture" in q for q in queries)
    assert not any("Feature Y" in q for q in queries)
    assert not any("Project X" in q for q in queries)
