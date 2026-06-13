import os

import pytest
from sqlmodel import select

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceSummaryAmount,
)
from app.models.user import User
from app.services.finance_seed import finance_data_exists, seed_finance_data


@pytest.fixture
def seeding_enabled(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)


def test_seed_finance_data_is_idempotent(session, seeding_enabled):
    user = session.exec(select(User)).one()
    assert os.getenv("TESTING") is None

    if not finance_data_exists(session):
        assert seed_finance_data(session, user.id) is True

    income = session.exec(select(FinanceIncomeEntry)).all()
    expenses = session.exec(select(FinanceExpenseEntry)).all()
    summary = session.exec(select(FinanceSummaryAmount)).all()

    assert len(income) == 2
    assert len(expenses) == 195
    assert len(summary) == 40
    assert all(entry.user_id == user.id for entry in income)
    assert expenses[0].amount < 0
    assert seed_finance_data(session, user.id) is False
