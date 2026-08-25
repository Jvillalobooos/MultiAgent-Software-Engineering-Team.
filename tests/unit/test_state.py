from engineering_team.contracts.state import EngineeringState, append_items


def test_state_keeps_required_fields_and_append_reducer() -> None:
    state = EngineeringState(run_id="r1", requirement="build feature")

    assert state.iteration == 0
    assert append_items(["one"], ["two"]) == ["one", "two"]
    assert state.final_status is None
