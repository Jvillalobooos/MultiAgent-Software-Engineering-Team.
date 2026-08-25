"""Execute SC-01..SC-05 and persist reproducible local evidence."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engineering_team.config import Settings
from engineering_team.mcp.quality import QualityMCP
from engineering_team.observability.evaluation import EvaluationHarness
from engineering_team.observability.metrics import aggregate
from engineering_team.rag import build_retriever


def main() -> None:
    settings = Settings()
    records = EvaluationHarness(
        retriever=build_retriever(settings, reindex=True),
        quality_mcp=QualityMCP(Path.cwd()),
        test_paths=["tests/integration/test_sample_app.py"],
    ).run_all()
    destination = EvaluationHarness.write(records, "evaluation/reports/scenarios.json")
    raw = [item.model_dump(mode="json", by_alias=True) for item in records]
    aggregate_path = Path("evaluation/reports/aggregate.json")
    aggregate_path.write_text(json.dumps(aggregate(raw), indent=2), encoding="utf-8")
    print(destination)
    print(aggregate_path)


if __name__ == "__main__":
    main()
