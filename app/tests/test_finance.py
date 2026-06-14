from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import select

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry, FinanceTransferEntry
from app.models.user import User
from app.services.finance import (
    BILLS_CATEGORY,
    build_expenses_context,
    build_income_context,
    build_investments_context,
    build_summary_context,
    build_transfers_context,
    format_finance_source,
    migrate_pro_labore_lucro_to_pj,
    upsert_investment_entry,
    validate_transfer_accounts,
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


def test_normalize_vendor_key_strips_installment_suffix():
    from app.services.finance import normalize_vendor_key

    assert normalize_vendor_key("Samsung 7/12") == "samsung"
    assert normalize_vendor_key("Pura Vida 6/6") == "pura vida"
    assert normalize_vendor_key("Centauro Ce64 6/8") == "centauro ce64"
    assert normalize_vendor_key("Merchant (3/10)") == "merchant"
    assert normalize_vendor_key("Netshoes Boston 13") == "netshoes example 13"


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


def test_summary_bills_from_expense_entries(session, client):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=1,
            category=BILLS_CATEGORY,
            vendor="Aluguel",
            payment_account="Nuconta",
            amount=Decimal("-1500.00"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=1)
    bills_card = next(card for card in context["summary_cards"] if card["id"] == "bills")
    assert bills_card["total_amount"] == Decimal("-1500.00")
    assert bills_card["lines"][0]["paid"] is True


def test_summary_bills_lines_always_paid(session):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category=BILLS_CATEGORY,
            vendor="Aluguel",
            payment_account="Nuconta",
            amount=Decimal("-2500"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=2)
    bills_card = next(card for card in context["summary_cards"] if card["id"] == "bills")
    assert all(line["paid"] for line in bills_card["lines"])


def test_summary_day_to_day_unpaid_without_transfer(session):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Transporte",
            vendor="Uber",
            payment_account="Nubank",
            amount=Decimal("-50"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=3)
    day_to_day_card = next(
        card for card in context["summary_cards"] if card["id"] == "day-to-day"
    )
    nubank_line = next(line for line in day_to_day_card["lines"] if line["label"] == "Nubank")
    assert nubank_line["paid"] is False


def test_summary_day_to_day_nuconta_always_paid(session):
    user = _test_user(session)
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
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=3)
    day_to_day_card = next(
        card for card in context["summary_cards"] if card["id"] == "day-to-day"
    )
    nuconta_line = next(line for line in day_to_day_card["lines"] if line["label"] == "Nuconta")
    assert nuconta_line["paid"] is True


def test_summary_day_to_day_paid_with_matching_transfer(session):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Transporte",
            vendor="Uber",
            payment_account="Nubank",
            amount=Decimal("-50"),
        )
    )
    session.add(
        FinanceTransferEntry(
            user_id=user.id,
            year=2026,
            month=3,
            from_account="Nuconta",
            to_account="Nubank",
            amount=Decimal("50"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=3)
    day_to_day_card = next(
        card for card in context["summary_cards"] if card["id"] == "day-to-day"
    )
    nubank_line = next(line for line in day_to_day_card["lines"] if line["label"] == "Nubank")
    assert nubank_line["paid"] is True


def test_summary_day_to_day_unpaid_when_transfer_amount_differs(session):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Transporte",
            vendor="Uber",
            payment_account="Nubank",
            amount=Decimal("-50"),
        )
    )
    session.add(
        FinanceTransferEntry(
            user_id=user.id,
            year=2026,
            month=3,
            from_account="Nuconta",
            to_account="Nubank",
            amount=Decimal("49.99"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=3)
    day_to_day_card = next(
        card for card in context["summary_cards"] if card["id"] == "day-to-day"
    )
    nubank_line = next(line for line in day_to_day_card["lines"] if line["label"] == "Nubank")
    assert nubank_line["paid"] is False


def test_income_category_pj_and_outros(session, client):
    user = _test_user(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=1,
            category="PJ",
            description="Pro labore",
            amount=Decimal("500"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=1,
            category="Outros",
            description="Reimbursement",
            amount=Decimal("50"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=1)
    income_card = next(card for card in context["summary_cards"] if card["id"] == "income")
    assert income_card["total_amount"] == Decimal("550")
    labels = {line["label"] for line in income_card["lines"]}
    assert "PJ" in labels
    assert "Outros" in labels


def test_migrate_pro_labore_lucro_to_pj_noop_without_summary_table(session):
    merged = migrate_pro_labore_lucro_to_pj(session)
    assert merged == 0


def test_summary_page_has_read_only_cards(client):
    response = client.get("/finance/summary?year=2026&month=1")
    assert response.status_code == 200
    assert "finance-summary-card" in response.text
    assert "btn-edit-section" not in response.text


def test_investments_annual_target(session):
    user = _test_user(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=1,
            category="PJ",
            description="Salary",
            amount=Decimal("10000"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category="PJ",
            description="Salary",
            amount=Decimal("10000"),
        )
    )
    upsert_investment_entry(
        session, user.id, 2026, 1, "xp", Decimal("1000")
    )
    upsert_investment_entry(
        session, user.id, 2026, 2, "nubank", Decimal("500")
    )

    context = build_investments_context(session, user.id, 2026, selected_month=2)
    assert context["annual_target"] == Decimal("6000.00")
    assert context["ytd_invested"] == Decimal("1500.00")


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


def test_summary_monthly_chart_payload():
    from app.services.finance import build_summary_monthly_chart

    chart = build_summary_monthly_chart(
        {3: Decimal("1400")},
        {3: Decimal("-50"), 6: Decimal("-100")},
        {3: Decimal("1350"), 6: Decimal("-100")},
        year=2026,
        selected_month=3,
        link_base="/finance/summary",
        aria_label="Income, expenses, and balance by month",
    )
    assert chart["variant"] == "summary"
    assert len(chart["points"]) == 12
    assert chart["points"][2] == {
        "month": 3,
        "label": "Mar",
        "income": 1400.0,
        "expense": -50.0,
        "balance": 1350.0,
    }
    assert chart["points"][5]["expense"] == -100.0
    assert chart["selectedMonth"] == 3


def test_summary_totals_vary_by_month(session):
    user = _test_user(session)

    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Outros",
            description="Client payment",
            amount=Decimal("1000"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=6,
            category="Outros",
            description="Bonus",
            amount=Decimal("200"),
        )
    )
    session.commit()

    march = build_summary_context(session, user.id, 2026, selected_month=3)
    june = build_summary_context(session, user.id, 2026, selected_month=6)

    assert march["month_income"] == Decimal("1000")
    assert june["month_income"] == Decimal("200")
    assert march["year_income"] == Decimal("1200")


def test_summary_aggregates_income_and_day_to_day(session):
    user = _test_user(session)

    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="Outros",
            description="Client payment",
            amount=Decimal("1000"),
        )
    )
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            category="PJ",
            description="Salary",
            amount=Decimal("400"),
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
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=3)
    income_card = next(card for card in context["summary_cards"] if card["id"] == "income")
    day_to_day_card = next(
        card for card in context["summary_cards"] if card["id"] == "day-to-day"
    )

    assert income_card["total_amount"] == Decimal("1400")
    assert day_to_day_card["total_amount"] == Decimal("-50")
    assert context["month_balance"] == Decimal("1350")


def test_summary_outros_includes_reimbursements_from_income_tab(session):
    user = _test_user(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=6,
            category="Outros",
            description="Travel reimbursement",
            amount=Decimal("50"),
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=6)
    income_card = next(card for card in context["summary_cards"] if card["id"] == "income")

    assert income_card["total_amount"] == Decimal("50")
    assert any(line["label"] == "Outros" for line in income_card["lines"])


def test_summary_page_loads(client):
    response = client.get("/finance/summary")
    assert response.status_code == 200
    assert "Balance" in response.text
    assert "finance-stats" in response.text
    assert "Monthly trend" in response.text
    assert 'class="finance-echart"' in response.text
    assert "echarts.min.js" in response.text
    assert "finance-summary-cards" in response.text


def test_income_create_with_category(session, client):
    response = client.post(
        "/finance/income",
        data={
            "year": "2026",
            "month": "3",
            "category": "PJ",
            "description": "Pro labore",
            "amount": "5000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceIncomeEntry)).one()
    assert entry.category == "PJ"


def test_investments_page_loads(client):
    response = client.get("/finance/investments")
    assert response.status_code == 200
    assert "Annual target" in response.text


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


def test_effective_expense_amount_subcategories():
    from app.services.finance import (
        BILLS_SUBCATEGORY_ALUGUEL,
        BILLS_SUBCATEGORY_OUTRAS_CONTAS,
        effective_expense_amount,
        effective_expense_amount_for,
    )

    entry = FinanceExpenseEntry(
        category=BILLS_CATEGORY,
        amount=Decimal("-1000.00"),
        subcategory=BILLS_SUBCATEGORY_ALUGUEL,
    )
    assert effective_expense_amount(entry) == Decimal("-614.00")
    assert effective_expense_amount_for(
        Decimal("-1000.00"), BILLS_SUBCATEGORY_OUTRAS_CONTAS
    ) == Decimal("-500.00")

    reversal = FinanceExpenseEntry(
        category=BILLS_CATEGORY,
        amount=Decimal("1000.00"),
        subcategory=BILLS_SUBCATEGORY_ALUGUEL,
    )
    assert effective_expense_amount(reversal) == Decimal("614.00")


def test_normalize_expense_subcategory():
    from app.services.finance import (
        BILLS_SUBCATEGORY_ALUGUEL,
        normalize_expense_subcategory,
    )

    assert (
        normalize_expense_subcategory(BILLS_CATEGORY, BILLS_SUBCATEGORY_ALUGUEL)
        == BILLS_SUBCATEGORY_ALUGUEL
    )
    assert normalize_expense_subcategory(BILLS_CATEGORY, "") is None
    assert normalize_expense_subcategory("Outros", None) is None

    import pytest

    with pytest.raises(ValueError):
        normalize_expense_subcategory("Outros", BILLS_SUBCATEGORY_ALUGUEL)
    with pytest.raises(ValueError):
        normalize_expense_subcategory(BILLS_CATEGORY, "Invalid")


def test_summary_uses_effective_bills_amount(session):
    user = _test_user(session)
    from app.services.finance import BILLS_SUBCATEGORY_ALUGUEL

    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=1,
            category=BILLS_CATEGORY,
            vendor="Aluguel",
            payment_account="Nuconta",
            amount=Decimal("-1000.00"),
            subcategory=BILLS_SUBCATEGORY_ALUGUEL,
        )
    )
    session.commit()

    context = build_summary_context(session, user.id, 2026, selected_month=1)
    bills_card = next(card for card in context["summary_cards"] if card["id"] == "bills")
    assert bills_card["total_amount"] == Decimal("-614.00")


def test_expenses_context_uses_effective_amounts(session):
    user = _test_user(session)
    from app.services.finance import BILLS_SUBCATEGORY_OUTRAS_CONTAS

    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category=BILLS_CATEGORY,
            vendor="Internet",
            payment_account="Nuconta",
            amount=Decimal("-200.00"),
            subcategory=BILLS_SUBCATEGORY_OUTRAS_CONTAS,
        )
    )
    session.commit()

    context = build_expenses_context(session, user.id, 2026)
    assert context["month_totals"][2] == Decimal("-100.00")
    assert context["category_year_totals"][BILLS_CATEGORY] == Decimal("-100.00")


def test_create_bills_expense_with_subcategory(session, client):
    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "3",
            "category": BILLS_CATEGORY,
            "vendor": "Aluguel",
            "payment_account": "Nuconta",
            "amount": "1000.00",
            "subcategory": "Aluguel (/2+114)",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(
        select(FinanceExpenseEntry).where(FinanceExpenseEntry.vendor == "Aluguel")
    ).one()
    assert entry.subcategory == "Aluguel (/2+114)"
    assert entry.amount == Decimal("-1000.00")


def test_vendor_subcategory_auto_assignment_on_create(session, client):
    from app.services.finance import BILLS_SUBCATEGORY_ALUGUEL, save_vendor_category

    user = _test_user(session)
    save_vendor_category(
        session,
        user.id,
        "Aluguel",
        BILLS_CATEGORY,
        subcategory=BILLS_SUBCATEGORY_ALUGUEL,
    )
    session.commit()

    response = client.post(
        "/finance/expenses",
        data={
            "year": "2026",
            "month": "4",
            "category": BILLS_CATEGORY,
            "vendor": "Aluguel",
            "payment_account": "Nuconta",
            "amount": "800.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.vendor == "Aluguel",
            FinanceExpenseEntry.month == 4,
        )
    ).one()
    assert entry.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_validate_transfer_accounts():
    assert validate_transfer_accounts("Nuconta", "Nubank") == ("Nuconta", "Nubank")

    with pytest.raises(ValueError, match="different"):
        validate_transfer_accounts("Nubank", "Nubank")

    with pytest.raises(ValueError, match="Invalid account"):
        validate_transfer_accounts("Manual", "Nubank")


def test_transfer_entry_totals(session, client):
    user = _test_user(session)

    session.add(
        FinanceTransferEntry(
            user_id=user.id,
            year=2026,
            month=3,
            from_account="Nuconta",
            to_account="Nubank",
            amount=Decimal("500"),
            description="Monthly top-up",
        )
    )
    session.add(
        FinanceTransferEntry(
            user_id=user.id,
            year=2026,
            month=6,
            from_account="Nubank",
            to_account="Wise",
            amount=Decimal("200"),
        )
    )
    session.commit()

    context = build_transfers_context(session, user.id, 2026)
    assert context["month_totals"][3] == Decimal("500")
    assert context["year_total"] == Decimal("700")

    response = client.get("/finance/transfers?year=2026")
    assert response.status_code == 200
    assert "Nuconta" in response.text
    assert "Monthly top-up" in response.text


def test_create_transfer_entry(session, client):
    response = client.post(
        "/finance/transfers",
        data={
            "year": "2026",
            "month": "2",
            "from_account": "Nuconta",
            "to_account": "Nubank",
            "amount": "1500.00",
            "description": "Pay credit card",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = session.exec(select(FinanceTransferEntry)).one()
    assert entry.from_account == "Nuconta"
    assert entry.to_account == "Nubank"
    assert entry.amount == Decimal("1500.00")
    assert entry.description == "Pay credit card"


def test_create_transfer_rejects_same_account(client):
    response = client.post(
        "/finance/transfers",
        data={
            "year": "2026",
            "month": "2",
            "from_account": "Nubank",
            "to_account": "Nubank",
            "amount": "100",
        },
        follow_redirects=False,
    )
    assert response.status_code == 422
