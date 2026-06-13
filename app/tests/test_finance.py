from decimal import Decimal

from sqlmodel import select

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry
from app.models.user import User
from app.services.finance import (
    build_expenses_context,
    build_income_context,
    build_summary_context,
    upsert_summary_amount,
)


def _test_user(session) -> User:
    return session.exec(select(User)).one()


def test_income_entry_totals(session, client):
    user = _test_user(session)

    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            description="Client payment",
            amount=Decimal("5000.00"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=6,
            description="Travel reimbursement",
            amount=Decimal("50"),
        )
    )
    session.commit()

    context = build_income_context(session, user.id, 2026)
    assert context["month_totals"][3] == Decimal("5000.00")
    assert context["year_total"] == Decimal("5050.00")

    response = client.get("/finance/income?year=2026")
    assert response.status_code == 200
    assert "MH" in response.text


def test_expense_entry_stored_negative(session, client):
    user = _test_user(session)

    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "2",
            "category": "Restaurante + entrega",
            "vendor": "Example Cafe",
            "payment_account": "Nubank",
            "amount": "50.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.amount == Decimal("-50.00")

    context = build_expenses_context(session, user.id, 2026)
    assert context["month_totals"][2] == Decimal("-50.00")


def test_expense_entry_negative_input_normalized(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "2",
            "category": "Uber",
            "vendor": "Uber",
            "payment_account": "Nubank",
            "amount": "-42.50",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.amount == Decimal("-42.50")


def test_expense_installments_create_monthly_entries(session, client):
    user = _test_user(session)

    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "3",
            "category": "Outros",
            "vendor": "Notebook",
            "payment_account": "Nubank",
            "amount": "300.00",
            "installments": "3",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entries = session.exec(
        select(FinanceExpenseEntry)
        .where(FinanceExpenseEntry.user_id == user.id)
        .order_by(FinanceExpenseEntry.month)
    ).all()
    assert len(entries) == 3
    assert [(entry.month, entry.amount, entry.vendor) for entry in entries] == [
        (3, Decimal("-100.00"), "Notebook (1/3)"),
        (4, Decimal("-100.00"), "Notebook (2/3)"),
        (5, Decimal("-100.00"), "Notebook (3/3)"),
    ]

    context = build_expenses_context(session, user.id, 2026)
    assert context["month_totals"][3] == Decimal("-100.00")
    assert context["month_totals"][4] == Decimal("-100.00")
    assert context["month_totals"][5] == Decimal("-100.00")


def test_expense_installments_split_remainder_on_last(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "1",
            "category": "Outros",
            "vendor": "Phone",
            "payment_account": "Nubank",
            "amount": "100.00",
            "installments": "3",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entries = session.exec(
        select(FinanceExpenseEntry).order_by(FinanceExpenseEntry.month)
    ).all()
    assert [entry.amount for entry in entries] == [
        Decimal("-33.33"),
        Decimal("-33.33"),
        Decimal("-33.34"),
    ]


def test_expense_installments_span_into_next_year(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "11",
            "category": "Outros",
            "vendor": "Sofa",
            "payment_account": "XP Crédito",
            "amount": "400.00",
            "installments": "4",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entries = session.exec(
        select(FinanceExpenseEntry).order_by(
            FinanceExpenseEntry.year, FinanceExpenseEntry.month
        )
    ).all()
    assert [(entry.year, entry.month, entry.amount) for entry in entries] == [
        (2026, 11, Decimal("-100.00")),
        (2026, 12, Decimal("-100.00")),
        (2027, 1, Decimal("-100.00")),
        (2027, 2, Decimal("-100.00")),
    ]


def test_summary_bill_stored_negative(session, client):
    response = client.post(
        "/finance/summary/cell",
        data={
            "year": "2026",
            "month": "1",
            "line_key": "aluguel",
            "amount": "1500.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from app.models.finance import FinanceSummaryAmount

    entry = session.exec(
        select(FinanceSummaryAmount).where(FinanceSummaryAmount.line_key == "aluguel")
    ).one()
    assert entry.amount == Decimal("-1500.00")


def test_summary_cell_returns_partial_for_htmx(client):
    response = client.post(
        "/finance/summary/cell",
        data={
            "year": "2026",
            "month": "1",
            "line_key": "pro_labore",
            "amount": "500.00",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'id="summary-pro_labore"' in response.text
    assert "btn-edit" in response.text
    assert "finance-line-input" in response.text


def test_monthly_chart_payload_has_twelve_points():
    from app.services.finance import MONTH_LABELS, build_monthly_chart

    chart = build_monthly_chart(
        {3: Decimal("-4850.51"), 5: Decimal("-5904.44")},
        year=2026,
        selected_month=5,
        link_base="/finance/expenses",
        variant="expense",
        aria_label="Expenses by month",
    )
    assert len(chart["points"]) == 12
    assert chart["points"][2]["value"] == -4850.51
    assert chart["points"][4]["value"] == -5904.44
    assert chart["selectedMonth"] == 5
    assert chart["points"][0]["label"] == MONTH_LABELS[0][:3]


def test_summary_tab_totals_vary_by_month(session):
    user = _test_user(session)

    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            description="Client payment",
            amount=Decimal("1000"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=6,
            description="Bonus",
            amount=Decimal("200"),
        )
    )
    session.commit()

    march = build_summary_context(session, user.id, 2026, selected_month=3)
    june = build_summary_context(session, user.id, 2026, selected_month=6)

    assert march["income_tab_total"] == Decimal("1000")
    assert june["income_tab_total"] == Decimal("200")
    assert march["income_tab_year_total"] == Decimal("1200")


def test_summary_computes_outros_and_debit(session):
    user = _test_user(session)

    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            description="Client payment",
            amount=Decimal("1000"),
        )
    )
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Uber",
            vendor="Uber",
            payment_account="Nuconta",
            amount=Decimal("-50"),
        )
    )
    upsert_summary_amount(
        session, user.id, 2026, 3, "pro_labore", Decimal("400")
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026)
    rows = {row.key: row for row in context["rows"]}

    assert rows["outros"].amounts.get(3) == Decimal("1000")
    assert rows["debito"].amounts.get(3) == Decimal("-50")
    assert rows["balance"].amounts.get(3) == (
        rows["income_total"].amounts.get(3) + rows["expenses_total"].amounts.get(3)
    )


def test_summary_page_loads(client):
    response = client.get("/finance/summary")
    assert response.status_code == 200
    assert "Balance this month" in response.text
    assert "Monthly trend" in response.text
    assert 'class="finance-echart"' in response.text
    assert "echarts.min.js" in response.text
    assert "Full year table" in response.text
