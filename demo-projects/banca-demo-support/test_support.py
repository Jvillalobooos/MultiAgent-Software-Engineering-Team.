"""Tests of demo mechanics, deliberately outside the agents' target project."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def support():
    path = ROOT / "support.py"
    assert path.exists(), "demo support module must exist"
    spec = importlib.util.spec_from_file_location("demo_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reset_restores_bytes_removes_generated_files_and_preserves_other_project(tmp_path):
    module = support()
    project = tmp_path / "banca-demo"
    project.mkdir()
    (project / ".banca-demo").write_text("banca-demo-v1\n")
    (project / "banca").mkdir()
    (project / "banca/app.py").write_text("original\n")
    manifest = module.make_manifest(project)
    (project / "banca/app.py").write_text("modified")
    (project / "banca/new.py").write_text("added")
    (project / "banca.db").write_bytes(b"runtime")
    sibling = tmp_path / "evidence.json"
    sibling.write_text("keep")
    module.restore(project, manifest)
    assert (project / "banca/app.py").read_text() == "original\n"
    assert not (project / "banca/new.py").exists()
    assert not (project / "banca.db").exists()
    assert sibling.read_text() == "keep"
    module.restore(project, manifest)
    assert module.make_manifest(project) == manifest


def test_reset_refuses_wrong_directory_and_corrupt_manifest(tmp_path):
    module = support()
    project = tmp_path / "banca-demo"
    project.mkdir()
    with pytest.raises(ValueError):
        module.restore(project, {"files": {}})
    (project / ".banca-demo").write_text("banca-demo-v1\n")
    (project / "safe.txt").write_text("keep")
    manifest = module.make_manifest(project)
    manifest["files"]["safe.txt"]["content"] = "tampered"
    with pytest.raises(ValueError):
        module.restore(project, manifest)
    assert (project / "safe.txt").read_text() == "keep"


def test_readme_has_exactly_seven_cases_and_no_tests_for_rejections():
    cases = support().read_cases(ROOT.parent / "banca-demo/README.md")
    assert [c["id"] for c in cases] == list(range(1, 8))
    assert all(c["testSpec"] for c in cases[:5])
    assert all(c["testSpec"] is None for c in cases[5:])
    assert all(c["message"] for c in cases)


def test_outcome_does_not_count_infrastructure_failure_as_security_rejection():
    module = support()
    snapshot = {"phase": "review_required", "authorize_writes": True,
                "trace_id": "trace", "report": {"review": {"status": "REJECTED",
                "subscores": {"security": 100}, "problems": ["provider timeout"]}}}
    assert module.outcome(snapshot, negative=True) == "retry"
    snapshot["report"]["review"]["subscores"]["security"] = 0
    snapshot["report"]["review"]["problems"] = ["reset token never expires"]
    assert module.outcome(snapshot, negative=True) == "rejected"
    assert module.outcome(snapshot, negative=False) == "security_stop"


def test_positive_requires_real_apply_and_passing_source_tests():
    module = support()
    snapshot = {"phase": "approved", "authorize_writes": True, "trace_id": "trace",
                "report": {"review": {"status": "APPROVED"}}}
    assert module.outcome(snapshot, negative=False) == "retry"
    snapshot.update(phase="applied", changed_paths=["banca/auth.py"],
                    apply_result={"status": "applied", "test_exit_code": 0})
    assert module.outcome(snapshot, negative=False) == "applied"
    snapshot["apply_result"]["test_exit_code"] = 1
    assert module.outcome(snapshot, negative=False) == "retry"


def test_negative_requires_the_intended_finding_not_a_failed_scanner():
    module = support()
    snapshot = {"phase": "review_required", "authorize_writes": True,
                "trace_id": "trace", "report": {"review": {"status": "REJECTED",
                "subscores": {"security": 0},
                "problems": ["security validation tool did not pass"]}}}
    assert module.outcome(snapshot, negative=True) == "retry"
    snapshot["report"]["review"]["problems"] = ["password reset tokens must expire"]
    assert module.outcome(snapshot, negative=True,
                          expected_finding="password reset tokens must expire") == "rejected"
    assert module.outcome(snapshot, negative=True,
                          expected_finding="resource access must be ownership-authorized") == "retry"


@pytest.mark.parametrize("panes", [1, 2])
def test_presentation_keeps_five_seconds_per_section_without_duplicate_pause(panes):
    import sys
    sys.path.insert(0, str(ROOT))
    try:
        from demo import Presentation
    finally:
        sys.path.pop(0)

    class Element:
        def wait_for(self, **kwargs): pass
        def evaluate(self, expression, *args):
            return 3600 if expression == "el => el.scrollHeight - el.clientHeight" else None
        def evaluate_handle(self, expression): return Handles()
        def as_element(self): return self

    class Handles:
        def get_properties(self): return {str(i): Element() for i in range(panes)}
        def dispose(self): pass

    waits = []
    view = Presentation(None, 5, ROOT)
    view.pause = lambda seconds=None: waits.append(5 if seconds is None else seconds)
    view.show(Element(), "diff")
    assert 5 <= sum(waits) < 8
    assert view.views[0]["section"] == "diff"


def test_maximization_is_verified_not_assumed_from_a_launch_flag():
    import sys
    sys.path.insert(0, str(ROOT))
    try:
        from demo import maximize_window
    finally:
        sys.path.pop(0)

    class Session:
        state = "normal"
        def send(self, command, params=None):
            if command == "Browser.getWindowForTarget": return {"windowId": 42}
            if command == "Browser.setWindowBounds":
                assert params == {"windowId": 42, "bounds": {"windowState": "maximized"}}
                self.state = "maximized"
            return {"bounds": {"windowState": self.state, "width": 1440, "height": 900}}
        def detach(self): pass

    class Context:
        def new_cdp_session(self, page): return Session()

    class Page:
        def wait_for_timeout(self, value): pass

    assert maximize_window(Context(), Page())["windowState"] == "maximized"


def _snapshot(*, phase, status, reason="", problems=(), security=0.0):
    return {
        "authorize_writes": True,
        "trace_id": "t" * 32,
        "phase": phase,
        "report": {"review": {
            "status": status, "reason": reason,
            "problems": list(problems), "subscores": {"security": security},
        }},
    }


def test_an_infrastructure_failure_on_a_negative_case_is_retried_not_scored_as_a_reject():
    """A run that died on a timeout also lands on HUMAN_REVIEW_REQUIRED with a zero
    security subscore, because nothing ran. Reporting that as "the Security Agent
    caught it" would credit the demo for a finding that was never made.
    """
    module = support()
    snapshot = _snapshot(phase="review_required", status="HUMAN_REVIEW_REQUIRED",
                         reason="AGENT_TIMEOUT: ReadTimeout")
    assert module.outcome(snapshot, negative=True) == "retry"


def test_an_evidenced_security_finding_on_a_negative_case_is_the_expected_reject():
    module = support()
    snapshot = _snapshot(
        phase="review_required", status="HUMAN_REVIEW_REQUIRED",
        reason="security findings require code remediation",
        problems=["password reset tokens must expire"],
    )
    assert module.outcome(snapshot, negative=True) == "rejected"


@pytest.mark.parametrize("reason", [
    "AGENT_TIMEOUT: ReadTimeout",
    "LLM_AVAILABILITY_ERROR: provider unavailable",
    "CLOUD_FALLBACK_UNAVAILABLE: rate_limit (HTTP 429)",
    "MCP_ERROR: transport closed",
])
def test_every_infrastructure_marker_stays_retryable(reason):
    module = support()
    snapshot = _snapshot(phase="review_required", status="HUMAN_REVIEW_REQUIRED",
                         reason=reason, problems=["something"])
    assert module.outcome(snapshot, negative=True) == "retry"
