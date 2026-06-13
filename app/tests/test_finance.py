from datetime import date
from decimal import Decimal

from sqlmodel import select

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry, FinanceSummaryAmount
from app.models.user import User
from app.services.finance import (
    build_expenses_context,
    build_income_context,
    build_summary_context,
    format_finance_source,
    migrate_pro_labore_lucro_to_pj,
    upsert_summary_amount,
)


def test_format_finance_source():
    assert format_finance_source("manual") == "Manual"
    assert format_finance_source("open_finance") == "Open Finance"
    assert format_finance_source(None) == "Manual"


def test_suggest_expense_category_maps_vendors():
    from app.services.finance import expense_category_slug, suggest_expense_category

    assert expense_category_slug("Supermercado") == "grocery"
    assert suggest_expense_category("Example Grocery", "Supermercado + online") == "Supermercado"
    assert suggest_expense_category("Example Cafe", "Outros") == "Supermercado"
    assert suggest_expense_category("Example Gym", "Fixos") == "Academia e treino"
    assert suggest_expense_category("RD", "Fixos") == "Assinaturas digitais"
    assert suggest_expense_category("EON", "Fixos") == "Corrida"
    assert suggest_expense_category("Coco", "Outros") == "Bar e lazer"
    assert suggest_expense_category("Capa celular", "Outros") == "Compras online"
    assert suggest_expense_category("Netshoes Boston 13", "Outros") == "Corrida"
    assert suggest_expense_category("UBER *TRIP", "") == "Transporte"
    assert suggest_expense_category("Random merchant", "Outros") == "Outros"


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
            "category": "Alimentação fora",
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
            "category": "Transporte",
            "vendor": "Uber",
            "payment_account": "Nubank",
            "amount": "-42.50",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.amount == Decimal("-42.50")


def test_expense_optional_transaction_date(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "2",
            "category": "Transporte",
            "vendor": "Metro",
            "payment_account": "Nubank",
            "amount": "5.50",
            "transaction_date": "2026-02-10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.transaction_date == date(2026, 2, 10)


def test_expense_without_date_defaults_to_none(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "2",
            "category": "Transporte",
            "vendor": "Metro",
            "payment_account": "Nubank",
            "amount": "5.50",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.transaction_date is None


def test_expenses_page_shows_dash_without_date(session, client):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category="Transporte",
            vendor="Metro",
            payment_account="Nubank",
            amount=Decimal("-5.50"),
        )
    )
    session.commit()

    response = client.get("/finance/expenses?year=2026&month=2")
    assert response.status_code == 200
    assert "Metro" in response.text
    assert "—" in response.text


def test_expense_update_transaction_date(session, client):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category="Transporte",
            vendor="Metro",
            payment_account="Nubank",
            amount=Decimal("-5.50"),
        )
    )
    session.commit()
    entry = session.exec(select(FinanceExpenseEntry)).one()

    response = client.post(
        f"/finance/expenses/{entry.id}",
        data={
            "month": "2",
            "category": "Transporte",
            "vendor": "Metro",
            "payment_account": "Nubank",
            "amount": "5.50",
            "transaction_date": "2026-02-14",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    session.refresh(entry)
    assert entry.transaction_date == date(2026, 2, 14)


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


def test_summary_section_save_returns_partial(client):
    response = client.post(
        "/finance/summary/section",
        data={
            "year": "2026",
            "month": "1",
            "section_id": "income",
            "line_key": ["pj"],
            "amount": ["500.00"],
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'id="summary-section-income"' in response.text
    assert "btn-save-section" in response.text
    assert "btn-edit-section" in response.text
    assert 'aria-label="Confirm' not in response.text


def test_migrate_pro_labore_lucro_to_pj(session):
    user = _test_user(session)
    session.add(
        FinanceSummaryAmount(
            user_id=user.id,
            year=2026,
            month=1,
            line_key="pro_labore",
            amount=Decimal("100"),
        )
    )
    session.add(
        FinanceSummaryAmount(
            user_id=user.id,
            year=2026,
            month=1,
            line_key="lucro",
            amount=Decimal("250"),
        )
    )
    session.commit()

    merged = migrate_pro_labore_lucro_to_pj(session)
    assert merged == 1

    rows = session.exec(
        select(FinanceSummaryAmount).where(FinanceSummaryAmount.user_id == user.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].line_key == "pj"
    assert rows[0].amount == Decimal("350")


def test_summary_section_save_persists_values(session, client):
    response = client.post(
        "/finance/summary/section",
        data={
            "year": "2026",
            "month": "1",
            "section_id": "income",
            "line_key": ["pj"],
            "amount": ["500.00"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    pj = session.exec(
        select(FinanceSummaryAmount).where(FinanceSummaryAmount.line_key == "pj")
    ).one()
    assert pj.amount == Decimal("500.00")


def test_summary_page_has_section_edit_buttons(client):
    response = client.get("/finance/summary?year=2026&month=1")
    assert response.status_code == 200
    assert "btn-edit-section" in response.text
    assert 'aria-label="Edit Income"' in response.text


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
            category="Transporte",
            vendor="Uber",
            payment_account="Nuconta",
            amount=Decimal("-50"),
        )
    )
    upsert_summary_amount(
        session, user.id, 2026, 3, "pj", Decimal("400")
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026)
    rows = {row.key: row for row in context["rows"]}

    assert rows["outros"].amounts.get(3) == Decimal("1000")
    assert rows["debito"].amounts.get(3) == Decimal("-50")
    assert rows["balance"].amounts.get(3) == (
        rows["income_total"].amounts.get(3) + rows["expenses_total"].amounts.get(3)
    )


def test_summary_outros_includes_reimbursements_from_income_tab(session):
    user = _test_user(session)
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

    context = build_summary_context(session, user.id, 2026)
    rows = {row.key: row for row in context["rows"]}

    assert rows["outros"].amounts.get(6) == Decimal("50")


def test_summary_page_loads(client):
    response = client.get("/finance/summary")
    assert response.status_code == 200
    assert "Balance this month" in response.text
    assert "Monthly trend" in response.text
    assert 'class="finance-echart"' in response.text
    assert "echarts.min.js" in response.text
    assert "Full year table" in response.text


def test_link_expense_reversal_unifies_amounts(session):
    from uuid import uuid4

    from app.services.finance import link_expense_reversal

    user = _test_user(session)
    charge = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("-142.50"),
    )
    reversal = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("28.90"),
        external_id=str(uuid4()),
    )
    session.add(charge)
    session.add(reversal)
    session.commit()

    updated = link_expense_reversal(
        session,
        user_id=user.id,
        reversal_id=reversal.id,
        target_id=charge.id,
    )
    session.commit()

    assert updated.amount == Decimal("-113.60")
    assert session.get(FinanceExpenseEntry, reversal.id) is None


def test_link_expense_reversal_route(client, session):
    from uuid import uuid4

    user = _test_user(session)
    charge = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("-142.50"),
    )
    reversal = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("28.90"),
        external_id=str(uuid4()),
    )
    session.add(charge)
    session.add(reversal)
    session.commit()

    response = client.post(
        f"/finance/expenses/{reversal.id}/link",
        data={"target_id": str(charge.id)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "hx-swap-oob" in response.text
    assert "-113,60" in response.text or "-113.60" in response.text

    session.refresh(charge)
    assert charge.amount == Decimal("-113.60")
    assert session.get(FinanceExpenseEntry, reversal.id) is None


def test_expenses_page_shows_reversal_link_controls(client, session):
    user = _test_user(session)
    charge = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("-142.50"),
    )
    reversal = FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=5,
        category="Alimentação fora",
        vendor="RESTAURANTE OUTBACK",
        payment_account="Nubank",
        amount=Decimal("28.90"),
    )
    session.add(charge)
    session.add(reversal)
    session.commit()

    response = client.get("/finance/expenses?year=2026&month=5")
    assert response.status_code == 200
    assert "Reversal" in response.text
    assert "Unify" in response.text
    assert "RESTAURANTE OUTBACK" in response.text
