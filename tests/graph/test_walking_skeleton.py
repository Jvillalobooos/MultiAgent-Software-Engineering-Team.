from engineering_team.graph.stategraph import build_walking_graph


def test_walking_graph_visits_six_core_roles_in_order() -> None:
    graph = build_walking_graph()

    result = graph.invoke({"visited": []})

    assert result["visited"] == [
        "Product",
        "Architecture",
        "Developer",
        "Security",
        "Testing",
        "Reviewer",
    ]
    assert result["final_status"] == "APPROVED"
