"""Compare real Developer calls against the frozen bank; never touches the live demo.

This is a model experiment, not evidence that the seven-case demo completed.
All generated code runs only in a separate, disposable demo fixture directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from support import BASELINE, HERE, PROJECT, read_cases

from engineering_team.agents.architecture import ArchitectureAgent
from engineering_team.agents.developer import DeveloperAgent
from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import CloudModelRuntime
from engineering_team.models.context import build_context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True, help="provider:model IDs")
    parser.add_argument("--authorize-writes", action="store_true", required=True)
    args = parser.parse_args()
    output = HERE / "evidence" / ("models-" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True)
    baseline = json.loads(BASELINE.read_text())
    case = read_cases(PROJECT / "README.md")[0]
    requirement = case["message"] + "\nTest specification:\n" + case["testSpec"]
    results = []
    print(f"Evidence: {output}", flush=True)
    for index, selection in enumerate(args.models):
        provider, model = selection.split(":", 1)
        if provider == "openrouter" and not model.endswith(":free"):
            raise SystemExit("Only explicit free OpenRouter model IDs are allowed")
        root = output / (str(index) + "-" + re.sub(r"[^a-zA-Z0-9-]", "_", model))
        project = root / "banca-demo"
        for name, entry in baseline["files"].items():
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(entry["content"], encoding="utf-8")
        independent = root / "banca-demo-support" / "test_acceptance.py"
        independent.parent.mkdir(parents=True)
        independent.write_text((HERE / "test_acceptance.py").read_text(), encoding="utf-8")
        reads = [ToolResult(tool_name="read_file", allowed_role=AgentRole.DEVELOPER,
                            status=ToolStatus.SUCCESS, input_summary="path=" + name,
                            output_summary=entry["content"], duration_ms=0,
                            evidence_reference="mcp://repository/read_file")
                 for name, entry in baseline["files"].items() if name.endswith(".py")]
        state = EngineeringState(run_id="isolated-model-probe", requirement=requirement,
                                 repository_context={"apply_changes": True}, tool_results=reads)
        product = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "Product"))
        state = state.model_copy(update={"specification": product})
        architecture = ArchitectureAgent().execute(build_context(AgentRole.ARCHITECTURE, state, "Architecture"))
        state = state.model_copy(update={"architecture": architecture})
        envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
        candidate = DeveloperAgent().execute(envelope)
        settings = Settings(cloud_enabled=True, local_first=False, cloud_chain_developer=selection,
                            llm_timeout_seconds=90, cloud_role_timeout_seconds=100)
        runtime = CloudModelRuntime(settings, primary=True)
        result = {"selection": selection, "contract_passed": False,
                  "source_test_exit_code": None, "acceptance_exit_code": None}
        started = time.monotonic()
        try:
            artifact, info = runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate)
            result.update(contract_passed=True, latency_ms=info.latency_ms)
            for name, content in artifact.file_contents.items():
                if not DeveloperAgent._safe_path(name) or name not in candidate.changed_files:
                    raise ValueError("unsafe generated path")
                destination = project / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
            for label, targets in [("source", ["tests"]), ("acceptance", [str(independent)])]:
                check = subprocess.run([sys.executable, "-m", "pytest", *targets, "-q", "--tb=short"],
                    cwd=project, env={**os.environ, "BANCA_DEMO_THROUGH": "1"},
                    capture_output=True, text=True, timeout=45, check=False)
                (root / (label + ".txt")).write_text(check.stdout + check.stderr, encoding="utf-8")
                result["source_test_exit_code" if label == "source" else "acceptance_exit_code"] = check.returncode
        except Exception as error:  # noqa: BLE001 -- preserve safe evidence for any provider failure
            # Provider bodies and credentials are deliberately never printed/saved.
            result["error"] = type(error).__name__
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        result["attempts"] = [a.model_dump(mode="json", exclude={"usage"}) for a in runtime.attempts]
        results.append(result)
        (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        if index + 1 < len(args.models):
            time.sleep(10)


if __name__ == "__main__":
    main()
