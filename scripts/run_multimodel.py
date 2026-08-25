"""Run the real local 4B/9B acceptance workflow and write its evidence."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engineering_team.config import Settings
from engineering_team.observability.evaluation import run_multimodel_acceptance


def main() -> None:
    evidence = run_multimodel_acceptance(
        Settings(),
        requirement=(
            "Provide a password-recovery link that expires after 15 minutes "
            "and can be used only once."
        ),
        report_path="evaluation/reports/multimodel-live.json",
    )
    print(json.dumps({"status": evidence["final_status"], "trace_id": evidence["trace_id"],
                      "bonus_pass": evidence["bonus_pass"]}))


if __name__ == "__main__":
    main()
