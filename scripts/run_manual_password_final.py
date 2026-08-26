"""One manual LIVE acceptance run for the Spanish password-change requirement."""

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
            "Permitir que un usuario cambie su contraseña solamente después de "
            "confirmar correctamente su contraseña actual; si no coincide, no "
            "debe modificarse nada."
        ),
        report_path="evaluation/reports/manual-password-final-cloud-chain-live.json",
    )
    print(json.dumps({
        "status": evidence["final_status"],
        "trace_id": evidence["trace_id"],
        "workspace": evidence.get("workspace"),
    }))


if __name__ == "__main__":
    main()
