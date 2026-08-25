"""Execute SC-01..SC-05 in deterministic or real local-model mode."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engineering_team.config import Settings
from engineering_team.llm.runtime import LocalModelRuntime
from engineering_team.mcp.client import MCPQualityClient
from engineering_team.observability.evaluation import EvaluationHarness
from engineering_team.observability.langfuse import LangfuseTracer
from engineering_team.observability.metrics import aggregate
from engineering_team.rag import build_retriever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-models", action="store_true",
        help="invoke the real local ModelRouter/LocalModelRuntime for all five scenarios",
    )
    args = parser.parse_args()
    settings = Settings(cloud_enabled=False)
    tracer = LangfuseTracer(
        public_key=settings.langfuse_public_key,
        secret_key=(
            settings.langfuse_secret_key.get_secret_value()
            if settings.langfuse_secret_key else None
        ),
        base_url=settings.langfuse_base_url,
        offline_directory="evaluation/reports/traces",
    )
    records = EvaluationHarness(
        retriever=build_retriever(settings, reindex=True),
        quality_mcp=MCPQualityClient(Path.cwd()),
        test_paths=["tests/integration/test_sample_app.py"],
        tracer=tracer,
        model_runtime_factory=(
            (lambda trace: LocalModelRuntime(settings, trace=trace))
            if args.live_models else None
        ),
    ).run_all()
    suffix = "-live" if args.live_models else ""
    destination = EvaluationHarness.write(
        records, f"evaluation/reports/scenarios{suffix}.json"
    )
    raw = [item.model_dump(mode="json", by_alias=True) for item in records]
    aggregate_path = Path(f"evaluation/reports/aggregate{suffix}.json")
    aggregate_path.write_text(json.dumps(aggregate(raw), indent=2), encoding="utf-8")
    print(destination)
    print(aggregate_path)


if __name__ == "__main__":
    main()
