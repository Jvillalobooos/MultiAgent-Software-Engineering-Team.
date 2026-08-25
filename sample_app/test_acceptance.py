from datetime import UTC, datetime, timedelta

import pytest

try:
    from app.service import BankService
except ModuleNotFoundError:  # Collected from the repository root.
    from sample_app.app.service import BankService


def test_password_recovery_is_exactly_fifteen_minutes_and_single_use(tmp_path):
    service = BankService(tmp_path / "bank.sqlite")
    before = datetime.now(UTC)
    token = service.issue_reset_token("owner")
    expires = service.connection.execute(
        "SELECT expires FROM reset_tokens WHERE token = ?", (token,)
    ).fetchone()[0]
    delta = datetime.fromisoformat(expires) - before
    assert timedelta(minutes=15) <= delta < timedelta(minutes=15, seconds=2)
    assert service.use_reset_token(token) is True
    assert service.use_reset_token(token) is False


def test_lockout_ownership_and_transaction_limit(tmp_path):
    service = BankService(tmp_path / "bank.sqlite")
    for attempt in range(1, 6):
        service.record_failed_login("owner")
        assert service.is_locked("owner") is (attempt == 5)
    service.add_transactions("owner", 8)
    assert len(service.history("owner", "owner")) == 5
    with pytest.raises(PermissionError):
        service.history("attacker", "owner")
