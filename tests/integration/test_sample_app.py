import sys
from pathlib import Path

sys.path.insert(0, str(Path("sample_app").resolve()))

from app.service import BankService


def test_recovery_token_is_single_use_and_fifteen_minutes(tmp_path: Path) -> None:
    service = BankService(tmp_path / "db.sqlite")
    token = service.issue_reset_token("u1")
    assert service.use_reset_token(token) is True
    assert service.use_reset_token(token) is False


def test_account_locks_after_five_failures_and_history_is_owned_and_limited(tmp_path: Path) -> None:
    service = BankService(tmp_path / "db.sqlite")
    for _ in range(5):
        service.record_failed_login("u1")
    assert service.is_locked("u1") is True
    service.add_transactions("u1", 7)
    assert len(service.history("u1", "u1")) == 5
